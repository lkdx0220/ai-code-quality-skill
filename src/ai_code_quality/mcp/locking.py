"""Stable per-user project locks with persistent execution intent."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import weakref
from contextlib import contextmanager
from pathlib import Path

from ..evidence import atomic_json
from .contracts import ServiceError

_AUDIT_GUARD = threading.Lock()
_AUDIT_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


@contextmanager
def audit_lock(path):
    """Serialize log rotation across threads/processes, waiting at most 50ms for the lock."""
    deadline = time.monotonic() + 0.05
    key = os.path.normcase(str(path.resolve()))
    with _AUDIT_GUARD:
        mutex = _AUDIT_LOCKS.get(key)
        if mutex is None:
            mutex = threading.Lock()
            _AUDIT_LOCKS[key] = mutex
    if not mutex.acquire(timeout=max(0, deadline - time.monotonic())):
        raise OSError("Audit thread lock is busy")
    try:
        with _audit_file_lock(path, deadline):
            yield
    finally:
        mutex.release()


@contextmanager
def _audit_file_lock(path, deadline):
    if path.is_symlink():
        raise OSError("Audit lock cannot be a symlink")
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.005)
        yield
    finally:
        os.close(fd)


def process_identity(pid):
    if os.name == "nt":
        import pywintypes
        import win32api
        import win32process

        try:
            handle = win32api.OpenProcess(0x1000, False, pid)
        except pywintypes.error as exc:
            if getattr(exc, "winerror", None) in (87, 1168):
                return None
            raise ServiceError("CLEANUP_FAILED", "Cannot verify process identity") from exc
        try:
            if win32process.GetExitCodeProcess(handle) != 259:
                return None
            return str(win32process.GetProcessTimes(handle)["CreationTime"])
        finally:
            handle.Close()
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() + ":" + fields[19]
    except FileNotFoundError:
        return None


def group_members(group):
    members = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group and fields[0] != "Z":
                members.append(int(path.name))
        except FileNotFoundError:
            continue
    return members


def domain_empty(owner):
    if owner.get("phase") != "active":
        return False
    if os.name != "nt":
        return not group_members(owner["child_pid"])
    import pywintypes
    import win32job

    try:
        job = win32job.OpenJobObject(4, False, owner["domain"])
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) == 2:
            return process_identity(owner["child_pid"]) != owner["child_birth"]
        raise ServiceError("CLEANUP_FAILED", "Cannot inspect the previous Windows job") from exc
    try:
        return (
            win32job.QueryInformationJobObject(job, win32job.JobObjectBasicAccountingInformation)[
                "ActiveProcesses"
            ]
            == 0
        )
    finally:
        job.Close()


class ProjectLock:
    def __init__(self, project_identity):
        self.project_identity = project_identity
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        else:
            root = Path.home() / ".cache"
        directory = root / "cq-mcp/locks"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700 if os.name != "nt" else 0o777)
        key = hashlib.sha256(project_identity.encode("utf-8")).hexdigest()
        self.path, self.owner_path = directory / (key + ".lock"), directory / (key + ".owner.json")
        self.fd = None

    def acquire(self):
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            fresh = True
        except FileExistsError:
            fd, fresh = os.open(self.path, os.O_RDWR), False
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ServiceError(
                    "PROJECT_BUSY", "Another operation holds this project lock"
                ) from exc
            self.fd = fd
            self._recover(fresh)
            self.safe = True
            return self
        except BaseException:
            os.close(fd)
            self.fd = None
            raise

    def _recover(self, fresh):
        if fresh and not self.owner_path.exists():
            atomic_json(self.owner_path, {"phase": "clean"})
        try:
            owner = json.loads(self.owner_path.read_text(encoding="utf-8"))
            if owner.get("phase") == "clean":
                return
            if process_identity(owner["owner_pid"]) == owner["owner_birth"] or not domain_empty(
                owner
            ):
                raise ServiceError(
                    "CLEANUP_FAILED",
                    "Prior execution is not proven clean; inspect the saved owner record before recovery",
                )
            atomic_json(self.owner_path, {"phase": "clean", "recovered": True})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ServiceError(
                "CLEANUP_FAILED",
                "Missing or damaged execution intent; cannot assume the project is idle",
            ) from exc

    def prepare(self, domain, state):
        self.safe = False
        self.owner = {
            "phase": "creating",
            "owner_pid": os.getpid(),
            "owner_birth": process_identity(os.getpid()),
            "domain": domain,
            "state": str(state),
        }
        atomic_json(self.owner_path, self.owner)

    def started(self, pid):
        self.owner.update(phase="active", child_pid=pid, child_birth=process_identity(pid))
        atomic_json(self.owner_path, self.owner)

    def release(self, *, clean):
        try:
            if clean:
                atomic_json(self.owner_path, {"phase": "clean"})
        finally:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
