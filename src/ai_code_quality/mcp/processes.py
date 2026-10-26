"""Bounded output and owned process domains; no shell and no orphaned tools."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

from .contracts import CAPTURE_LIMIT, ServiceError
from .locking import group_members

_SPAWN_LOCK = threading.Lock()


class WindowsProcess:
    def __init__(self, argv, cwd, env, domain, lease):
        import msvcrt

        import win32con
        import win32job
        import win32process

        self.job = self.process = self.thread = None
        self.stdout = self.stderr = None
        try:
            self.job = win32job.CreateJobObject(None, domain)
            info = win32job.QueryInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation
            )
            info["BasicLimitInformation"]["LimitFlags"] |= (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            win32job.SetInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation, info
            )
            with _SPAWN_LOCK:
                out_r, out_w = os.pipe()
                err_r, err_w = os.pipe()
                self.stdout, self.stderr = os.fdopen(out_r, "rb"), os.fdopen(err_r, "rb")
                try:
                    with open(os.devnull, "rb") as stdin:
                        for fd in (out_w, err_w, stdin.fileno()):
                            os.set_inheritable(fd, True)
                        startup = win32process.STARTUPINFO()
                        startup.dwFlags = win32con.STARTF_USESTDHANDLES
                        startup.hStdInput = msvcrt.get_osfhandle(stdin.fileno())
                        startup.hStdOutput = msvcrt.get_osfhandle(out_w)
                        startup.hStdError = msvcrt.get_osfhandle(err_w)
                        self.process, self.thread, self.pid, _ = win32process.CreateProcess(
                            None,
                            subprocess.list2cmdline(argv),
                            None,
                            None,
                            True,
                            win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW,
                            env,
                            str(cwd),
                            startup,
                        )
                    # No project code executes until membership and intent are durable.
                    win32job.AssignProcessToJobObject(self.job, self.process)
                    lease.started(self.pid)
                    win32process.ResumeThread(self.thread)
                finally:
                    os.close(out_w)
                    os.close(err_w)
        except BaseException:
            self._abort_spawn(lease)
            raise

    def _abort_spawn(self, lease):
        import win32event
        import win32process

        try:
            if self.process is not None:
                # A failed assignment may leave a suspended child outside the Job.
                win32process.TerminateProcess(self.process, 137)
                if win32event.WaitForSingleObject(self.process, 5000) != 0:
                    raise RuntimeError("Initial process still alive")
            if self.job is not None:
                self.terminate_tree()
                if not self.empty():
                    raise RuntimeError("Job still active")
            for stream in (self.stdout, self.stderr):
                if stream is not None:
                    stream.close()
            self.close()
        except Exception as exc:
            raise ServiceError("CLEANUP_FAILED", "Failed spawn cleanup is not confirmed") from exc
        lease.safe = True

    def poll(self):
        import win32event
        import win32process

        return (
            None
            if win32event.WaitForSingleObject(self.process, 0) != 0
            else win32process.GetExitCodeProcess(self.process)
        )

    def terminate_tree(self):
        import win32job

        win32job.TerminateJobObject(self.job, 137)

    def empty(self):
        import win32job

        return (
            win32job.QueryInformationJobObject(
                self.job, win32job.JobObjectBasicAccountingInformation
            )["ActiveProcesses"]
            == 0
        )

    def close(self):
        for handle in (self.job, self.thread, self.process):
            if handle is not None:
                handle.Close()


class PosixProcess:
    def __init__(self, argv, cwd, env, domain, lease):
        try:
            self.child = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError:
            lease.safe = True  # Popen failed before yielding a child process.
            raise
        self.pid, self.stdout, self.stderr = self.child.pid, self.child.stdout, self.child.stderr
        try:
            lease.started(self.pid)
        except BaseException:
            _cleanup(self, [], lease)
            for stream in (self.stdout, self.stderr):
                stream.close()
            raise

    def poll(self):
        return self.child.poll()

    def terminate_tree(self):
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def empty(self):
        self.child.poll()
        return not group_members(self.pid)

    def close(self):
        self.child.wait(timeout=5)


def _read(stream, limit, chunks, overflow, errors):
    size = 0
    try:
        while block := stream.read(65536):
            size += len(block)
            if size > limit:
                overflow.set()
                break
            chunks.append(block)
    except OSError:
        errors.set()
    finally:
        try:
            stream.close()
        except OSError:
            errors.set()


def _cleanup(process, threads, lease):
    try:
        process.terminate_tree()
        deadline = time.monotonic() + 5
        while not process.empty() and time.monotonic() < deadline:
            time.sleep(0.02)
        clean = process.empty()
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        process.close()
        if not clean or any(thread.is_alive() for thread in threads):
            raise RuntimeError("Process domain or readers still active")
    except Exception as exc:
        raise ServiceError(
            "CLEANUP_FAILED", "Owned process domain did not close cleanly within 5 seconds"
        ) from exc
    lease.safe = True


def execute(argv, settings, lease, cancel, timeout, *, cancelled=lambda: False):
    from .store import new_id

    if cancel.is_set() or cancelled():
        return {
            "exit_code": None,
            "outcome": "cancelled",
            "stdout": b"",
            "stderr": b"",
            "pid": None,
            "seconds": 0,
        }
    domain = new_id("cq-mcp")
    lease.prepare(domain, settings.state)
    kind = WindowsProcess if os.name == "nt" else PosixProcess
    try:
        process = kind(argv, settings.project, settings.env, domain, lease)
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError("CLI_UNAVAILABLE", "Cannot start the configured cq interpreter") from exc
    output, diagnostics, overflow, errors = [], [], threading.Event(), threading.Event()
    threads = [
        threading.Thread(target=_read, args=args, daemon=True)
        for args in (
            (process.stdout, CAPTURE_LIMIT, output, overflow, errors),
            (process.stderr, 256 * 1024, diagnostics, overflow, errors),
        )
    ]
    readers = []
    started, outcome = time.monotonic(), None
    try:
        for thread in threads:
            thread.start()
            readers.append(thread)
        while process.poll() is None:
            if time.monotonic() - started >= timeout:
                outcome = "timed_out"
                break
            if cancel.is_set() or cancelled():
                outcome = "cancelled"
                break
            if time.monotonic() - started >= timeout:
                outcome = "timed_out"
                break
            if overflow.is_set():
                outcome = "overflow"
                break
            time.sleep(0.03)
        code = process.poll()
    finally:
        # Even a normally exited CLI may have left analyzer descendants behind.
        _cleanup(process, readers, lease)
    if errors.is_set():
        raise ServiceError("IO_ERROR", "Core output capture failed")
    if overflow.is_set():
        raise ServiceError(
            "OUTPUT_TOO_LARGE",
            "Core output exceeded capture limits; use findings pagination or the CLI",
        )
    return {
        "exit_code": code,
        "outcome": outcome,
        "stdout": b"".join(output),
        "stderr": b"".join(diagnostics),
        "pid": process.pid,
        "seconds": time.monotonic() - started,
    }
