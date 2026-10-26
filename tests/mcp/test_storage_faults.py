"""Faults must not publish success or tear transactional state/evidence."""

import asyncio
import errno
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ai_code_quality import evidence, scan
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.config import Config
from ai_code_quality.mcp.contracts import ServiceError
from ai_code_quality.mcp.locking import ProjectLock
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings
from ai_code_quality.mcp.store import RESERVATION, Store
from ai_code_quality.schema import AdapterResult


@pytest.fixture
def service(tmp_path):
    if os.name == "nt":
        pytest.importorskip(
            "win32api", reason="Optional Windows process-domain dependency required"
        )
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    return Service(Settings(project, tmp_path / "state", tool_python=sys.executable))


def outcome(service, operation, **arguments):
    return asyncio.run(service.call(operation, arguments))


def intact(store):
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return {
            table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            for table in ("jobs", "reservations", "artifacts", "cursors")
        }


def inject_sql(monkeypatch, statement, *, after=False, fail_connect=False):
    original = sqlite3.connect
    fired = []

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            matched = sql.startswith(statement) and not fired
            if matched and not after:
                fired.append(sql)
                raise sqlite3.OperationalError("injected disk I/O error")
            result = super().execute(sql, parameters)
            if matched:
                fired.append(sql)
                raise sqlite3.OperationalError("injected disk I/O error")
            return result

    def connect(*args, **kwargs):
        if fail_connect and not fired:
            fired.append("connect")
            raise sqlite3.OperationalError("unable to open database file")
        kwargs["factory"] = FaultConnection
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    return fired


@pytest.mark.parametrize("failure", ["connect", "insert", "commit"])
def test_admission_io_failure_is_structured_and_rolls_back(service, monkeypatch, failure):
    before = intact(service.store)
    with monkeypatch.context() as patch:
        fired = inject_sql(
            patch,
            "INSERT INTO jobs" if failure == "insert" else "COMMIT",
            after=failure == "insert",
            fail_connect=failure == "connect",
        )
        response = outcome(service, "cq_doctor", request_key="failed-admission")
        assert fired
    assert response["ok"] is False and response["error"]["code"] == "IO_ERROR", response
    assert intact(service.store) == before
    lease = ProjectLock(service.settings.project_identity).acquire()
    lease.release(clean=True)
    accepted, (job, lease) = service._submit("cq_doctor", {"request_key": "failed-admission"})
    try:
        assert not accepted["reused"]
        service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("primary", ["locked", "io", "domain", "interrupt"])
def test_rollback_and_close_failure_preserve_primary_error(service, monkeypatch, primary):
    original = sqlite3.connect
    expected = {
        "locked": sqlite3.OperationalError("database is locked"),
        "io": sqlite3.OperationalError("injected primary I/O failure"),
        "domain": ServiceError("JOB_NOT_FOUND", "primary domain error"),
        "interrupt": KeyboardInterrupt(),
    }[primary]
    cleanup = []

    class BrokenCleanup(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if sql.startswith("SELECT body FROM jobs"):
                raise expected
            if sql == "ROLLBACK":
                cleanup.append("rollback")
                raise sqlite3.OperationalError("injected secondary rollback failure")
            return super().execute(sql, parameters)

        def close(self):
            super().close()
            cleanup.append("close")
            raise sqlite3.OperationalError("injected secondary close failure")

    def connect(*args, **kwargs):
        return original(*args, **kwargs, factory=BrokenCleanup)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        if primary == "interrupt":
            with pytest.raises(KeyboardInterrupt) as error:
                service.store.job("missing")
            assert error.value is expected
        else:
            response = outcome(service, "cq_job_get", job_id="missing")
            assert not response["ok"]
            assert (
                response["error"]["code"]
                == {"locked": "STATE_BUSY", "io": "IO_ERROR", "domain": "JOB_NOT_FOUND"}[primary]
            )
            assert "secondary" not in json.dumps(response)
    assert cleanup == ["rollback", "close"]


def test_close_failure_without_primary_error_is_structured(service, monkeypatch):
    original = sqlite3.connect

    class BrokenClose(sqlite3.Connection):
        def close(self):
            super().close()
            raise sqlite3.OperationalError("injected close failure")

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: original(*a, **k, factory=BrokenClose))
    response = outcome(service, "cq_job_get", job_id="missing")
    assert not response["ok"] and response["error"]["code"] == "IO_ERROR"


@pytest.mark.parametrize("statement", ["INSERT INTO artifacts", "COMMIT"])
def test_snapshot_failure_restores_reservation_and_previous_artifact(
    service, monkeypatch, statement
):
    store = service.store
    old = store.artifact("report", "previous evidence", {})
    with store.transaction() as db:
        store.reserve(db, "work")
    before = intact(store)
    with monkeypatch.context() as patch:
        fired = inject_sql(patch, statement, after=statement.startswith("INSERT"))
        with pytest.raises(ServiceError) as error:
            store.artifact("report", "new evidence", {}, reservation="work")
        assert error.value.code == "IO_ERROR" and fired
    assert intact(store) == before
    assert store.capacity_status()["reserved_bytes"] == RESERVATION
    assert store.read_artifact(old["artifact_id"])[1] == "previous evidence"
    saved = store.artifact("report", "new evidence", {}, reservation="work")
    store.release("work")
    assert store.read_artifact(saved["artifact_id"])[1] == "new evidence"
    assert store.capacity_status()["reserved_bytes"] == 0


def test_terminal_update_failure_cannot_release_only_half_the_transaction(service, monkeypatch):
    _, (job, lease) = service._submit("cq_doctor", {"request_key": "finish"})
    try:
        before = intact(service.store)
        with monkeypatch.context() as patch:
            fired = inject_sql(patch, "UPDATE jobs SET state", after=True)
            with pytest.raises(ServiceError) as error:
                service.store.finish(job["job_id"], state="completed", cleanup="confirmed")
            assert error.value.code == "IO_ERROR" and fired
        assert intact(service.store) == before
        service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
        assert service.store.capacity_status()["reserved_bytes"] == 0
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("mode", ["lock", "insert"])
def test_independent_sqlite_writer_timeout_or_crash_recovers(
    service, tmp_path, mode, record_property
):
    ready, release = tmp_path / "ready.json", tmp_path / "release"
    script = Path(__file__).parent / "fixtures/sqlite_fault_owner.py"
    owner = subprocess.Popen(
        [sys.executable, str(script), str(service.store.path), str(ready), str(release), mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    before = intact(service.store)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        if mode == "lock":
            started = time.monotonic()
            response = outcome(service, "cq_job_get", job_id="j-missing")
            elapsed = time.monotonic() - started
            assert response["error"]["code"] == "JOB_NOT_FOUND", response
            assert elapsed < 1, elapsed
            assert not response["warnings"]  # Reads/audit no longer compete for a SQLite writer.
            record_property("busy", json.dumps({"seconds": elapsed, "response": response}))
            release.touch()
        else:
            owner.kill()  # An uncommitted real SQLite insert, no mocked rollback.
        stdout, stderr = owner.communicate(timeout=10)
        assert not stdout and not stderr
        assert intact(service.store) == before
        assert (
            Store(service.settings.state, service.settings.project_identity).capacity_status()[
                "reserved_bytes"
            ]
            == 0
        )
        response = outcome(service, "cq_job_get", job_id="j-missing")
        assert response["error"]["code"] == "JOB_NOT_FOUND", response
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate(timeout=5)


@pytest.mark.parametrize("stage", ["write", "flush", "fsync", "replace"])
@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EACCES, errno.EIO])
def test_atomic_failure_preserves_previous_bytes_and_removes_temporary(
    tmp_path, monkeypatch, stage, error_number
):
    target = tmp_path / "evidence.json"
    target.write_bytes(b"previous immutable evidence")
    original_open = os.fdopen

    def fail(*args, **kwargs):
        raise OSError(error_number, "injected file operation failure")

    class FaultStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, value):
            self.stream.write(value[:3])  # Actually dirty the temporary file first.
            if stage == "write":
                fail()
            return self.stream.write(value[3:])

        def flush(self):
            if stage == "flush":
                fail()
            return self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    if stage in ("write", "flush"):
        monkeypatch.setattr(os, "fdopen", lambda *a, **kw: FaultStream(original_open(*a, **kw)))
    else:
        monkeypatch.setattr(os, "fsync" if stage == "fsync" else "replace", fail)
    with pytest.raises(OSError) as error:
        evidence.atomic_text(target, ["replacement evidence"])
    assert error.value.errno == error_number
    assert target.read_bytes() == b"previous immutable evidence"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("stage", ["fsync", "replace"])
@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EACCES, errno.EIO])
def test_marker_storage_failure_does_not_publish_partial_run(
    service, monkeypatch, stage, error_number
):
    class Quiet(Adapter):
        name = "ruff-check"

        def run(self, ctx):
            return AdapterResult(name=self.name, tool="ruff", status="ok", version="fixture")

    monkeypatch.setattr(scan, "get_adapters", lambda _: [Quiet()])
    old = scan.run_scan(service.settings.project, cfg=Config(), run_id="old")
    saved = {
        str(p.relative_to(old.run_dir)): p.read_bytes()
        for p in old.run_dir.rglob("*")
        if p.is_file()
    }
    if stage == "replace":
        original = os.replace

        def replace(source, destination):
            if Path(destination).name == ".complete.json":
                raise OSError(error_number, "injected marker replace failure")
            return original(source, destination)

        monkeypatch.setattr(os, "replace", replace)
    else:
        original_text = evidence.atomic_text

        def atomic_text(path, chunks):
            if path.name != ".complete.json":
                return original_text(path, chunks)
            with monkeypatch.context() as patch:

                def fsync(fd):
                    raise OSError(error_number, "injected marker fsync failure")

                patch.setattr(os, "fsync", fsync)
                return original_text(path, chunks)

        monkeypatch.setattr(evidence, "atomic_text", atomic_text)
    with pytest.raises(OSError):
        scan.run_scan(service.settings.project, cfg=Config(), run_id="partial")
    assert not (service.settings.project / "audits/partial/.complete.json").exists()
    response = outcome(service, "cq_findings_get", run_id="partial")
    assert response["error"]["code"] == "RUN_NOT_READY", response
    assert saved == {
        str(p.relative_to(old.run_dir)): p.read_bytes()
        for p in old.run_dir.rglob("*")
        if p.is_file()
    }
    assert outcome(service, "cq_findings_get", run_id="old")["ok"]
