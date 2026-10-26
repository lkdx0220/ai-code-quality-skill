"""Control responses, process cleanup and pending facts survive storage contention."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from ai_code_quality.mcp.contracts import ServiceError
from ai_code_quality.mcp.control import ControlPlane
from ai_code_quality.mcp.locking import audit_lock, process_identity
from ai_code_quality.mcp.processes import execute
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings


@pytest.fixture
def service(tmp_path):
    if os.name == "nt":
        pytest.importorskip("win32api")
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    return Service(Settings(project, tmp_path / "state", tool_python=sys.executable))


@contextmanager
def writer(store, root, mode="lock"):
    ready, release = root / "ready.json", root / "release"
    owner = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).parent / "fixtures/sqlite_fault_owner.py"),
            str(store.path),
            str(ready),
            str(release),
            mode,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        yield
    finally:
        release.touch()
        stdout, stderr = owner.communicate(timeout=10)
        assert owner.returncode == 0 and not stdout and not stderr


def submit(service, key="known"):
    _, (job, lease) = service._submit("cq_doctor", {"request_key": key})
    return job, lease


@pytest.mark.parametrize("mode", ["lock", "exclusive"])
def test_control_reads_and_argument_errors_have_bounded_lock_wait(
    service, tmp_path, mode, record_property
):
    job, lease = submit(service)
    service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    lease.release(clean=True)
    old = service.store.artifact("report", "old immutable evidence", {})

    async def scenario():
        times = []
        with writer(service.store, tmp_path, mode):
            for operation, args in (
                ("cq_job_get", {"job_id": job["job_id"]}),
                ("cq_artifact_get", {"artifact_id": old["artifact_id"]}),
                ("cq_job_get", {"job_id": None}),
            ):
                started = time.monotonic()
                response = await service.call(operation, args)
                times.append(time.monotonic() - started)
                assert times[-1] < 1, response
                assert not response["warnings"]
                if args.get("job_id", "valid") is None:
                    assert response["error"]["code"] == "INVALID_ARGUMENT"
                elif mode == "exclusive":
                    assert response["error"]["code"] == "STATE_BUSY"
                else:
                    assert response["ok"], response
            started = time.monotonic()
            response = await service.call("cq_job_cancel", {"job_id": job["job_id"]})
            assert time.monotonic() - started < 1
            assert response["error"]["code"] == "STATE_BUSY"
        record_property("control_waits", json.dumps({"lock": mode, "seconds": times}))
        await service.close()

    asyncio.run(scenario())


def test_independent_audit_lock_failure_warns_without_waiting_for_database(service):
    with audit_lock(service.store.root / "calls.lock"):
        started = time.monotonic()
        response = asyncio.run(service.call("cq_job_get", {"job_id": None}))
        assert time.monotonic() - started < 1
    assert response["error"]["code"] == "INVALID_ARGUMENT" and response["warnings"]


@pytest.mark.parametrize("mode", ["lock", "exclusive"])
def test_owned_cancel_cleans_real_tree_before_database_recovers(
    service, tmp_path, mode, record_property
):
    marker = tmp_path / "tree.json"
    service._job_command = lambda job: [
        sys.executable,
        str(Path(__file__).parent / "fixtures/fault_stdio_server.py"),
        "tree",
        str(marker),
    ]

    async def scenario():
        try:
            accepted = await service.call("cq_doctor", {"request_key": "live"})
            identity = accepted["data"]["job_id"]
            deadline = time.monotonic() + 10
            while not marker.exists():
                assert time.monotonic() < deadline
                await asyncio.sleep(0.02)
            tree = json.loads(marker.read_text())
            with writer(service.store, tmp_path, mode):
                started = time.monotonic()
                cancelled = await service.call("cq_job_cancel", {"job_id": identity})
                elapsed = time.monotonic() - started
                assert elapsed < 1 and cancelled["ok"], cancelled
                assert cancelled["data"]["cancellation_requested"]
                assert not cancelled["data"]["cancellation_persisted"]
                assert cancelled["data"]["persistence_error"]["code"] == "STATE_BUSY"
                while True:
                    found = await service.call("cq_job_get", {"job_id": identity})
                    assert found["ok"], found
                    if found["data"]["state"] == "cancelled":
                        break
                    assert time.monotonic() < deadline
                    await asyncio.sleep(0.02)
                assert found["warnings"] and not found["data"]["state_persisted"]
                assert found["data"]["cleanup"] == "confirmed"
                assert process_identity(tree["pid"]) != tree["birth"]
                assert process_identity(tree["child"]) != tree["child_birth"]
            recovered = await service.call("cq_job_get", {"job_id": identity})
            assert recovered["ok"] and recovered["data"]["state_persisted"]
            assert recovered["data"]["state"] == "cancelled"
            assert service.store.capacity_status()["reserved_bytes"] == 0
            again = await service.call("cq_doctor", {"request_key": "live"})
            assert again["data"]["reused"] and again["data"]["terminal_state"] == "cancelled"
            record_property("owned_cancel", json.dumps({"lock": mode, "seconds": elapsed}))
        finally:
            await service.close()

    asyncio.run(scenario())


def test_foreign_instance_cancellation_uses_durable_flag(service, tmp_path):
    service._job_command = lambda job: [sys.executable, "-c", "import time; time.sleep(40)"]
    other = Service(service.settings)

    async def scenario():
        try:
            accepted = await service.call("cq_doctor", {"request_key": "foreign"})
            identity = accepted["data"]["job_id"]
            await asyncio.sleep(0.2)
            with writer(service.store, tmp_path):
                started = time.monotonic()
                denied = await other.call("cq_job_cancel", {"job_id": identity})
                assert time.monotonic() - started < 1
                assert denied["error"]["code"] == "STATE_BUSY"
            assert not service.store.job(identity)["cancellation_requested"]
            response = await other.call("cq_job_cancel", {"job_id": identity})
            assert response["ok"] and response["data"]["cancellation_persisted"]
            for _ in range(150):
                polled = await service.call("cq_job_get", {"job_id": identity})
                if polled["data"]["state"] == "cancelled":
                    break
                await asyncio.sleep(0.02)
            assert (
                polled["data"]["state"] == "cancelled" and polled["data"]["cleanup"] == "confirmed"
            )
        finally:
            await service.close()
            await other.close()

    asyncio.run(scenario())


def test_deadline_ignores_exclusive_database_lock(service, tmp_path):
    job, lease = submit(service)
    try:
        with writer(service.store, tmp_path, "exclusive"):
            started = time.monotonic()
            captured = execute(
                [sys.executable, "-c", "import time; time.sleep(40)"],
                service.settings,
                lease,
                threading.Event(),
                0.2,
                cancelled=lambda: service.control.cancelled(job["job_id"]),
            )
            assert time.monotonic() - started < 1
            assert captured["outcome"] == "timed_out" and lease.safe
    finally:
        service.store.finish(job["job_id"], state="timed_out", cleanup="confirmed")
        lease.release(clean=lease.safe)


@pytest.mark.parametrize("first", ["cancel", "finish"])
def test_terminal_selection_serializes_cancel_and_pending_commit(service, monkeypatch, first):
    job, lease = submit(service)
    identity = job["job_id"]
    event = threading.Event()
    service.control.track(job, event)

    def fail(*args, **kwargs):
        raise ServiceError("IO_ERROR", "injected terminal write failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(service.store, "finish", fail)
            if first == "cancel":
                assert service.control.cancel(identity)[0]
            service.control.finish(
                identity, state="completed", cleanup="confirmed", result={"value": 1}
            )
            late, body = service.control.cancel(identity)
            assert not late and not body["state_persisted"]
            assert body["state"] == ("cancelled" if first == "cancel" else "completed")
        recovered = service.control.get(identity)
        assert recovered["state_persisted"]
        assert recovered["state"] == ("cancelled" if first == "cancel" else "completed")
        assert service.store.capacity_status()["reserved_bytes"] == 0
        assert not service.control.jobs
    finally:
        lease.release(clean=True)


def test_pending_terminal_reconciles_on_next_submission(service, monkeypatch):
    job, lease = submit(service)
    service.control.track(job, threading.Event())
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                service.store,
                "finish",
                lambda *a, **k: (_ for _ in ()).throw(ServiceError("IO_ERROR", "full")),
            )
            service.control.finish(job["job_id"], state="cancelled", cleanup="confirmed")
            assert service.store.job(job["job_id"])["state"] == "queued"
        lease.release(clean=True)
        following, following_lease = submit(service, "after-freeing")
        try:
            assert service.store.job(job["job_id"])["state"] == "cancelled"
            assert service.store.capacity_status()["reserved_bytes"] == 9 * 1024 * 1024
            service.store.finish(following["job_id"], state="cancelled", cleanup="confirmed")
        finally:
            following_lease.release(clean=True)
    finally:
        lease.release(clean=True)


def test_pre_cancelled_execution_never_spawns(service):
    job, lease = submit(service)
    event = threading.Event()
    event.set()
    try:
        result = execute(["nonexistent-must-not-spawn"], service.settings, lease, event, 1)
        assert result["outcome"] == "cancelled" and result["pid"] is None and lease.safe
    finally:
        service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
        lease.release(clean=True)


def test_simultaneous_finish_and_cancel_agree_on_selected_terminal(service):
    from concurrent.futures import ThreadPoolExecutor

    job, lease = submit(service)
    identity = job["job_id"]
    service.control.track(job, threading.Event())
    barrier = threading.Barrier(2)

    def finish():
        barrier.wait(timeout=5)
        return service.control.finish(identity, state="completed", cleanup="confirmed", result={})

    def cancel():
        barrier.wait(timeout=5)
        return service.control.cancel(identity)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            finished, cancelled = pool.submit(finish), pool.submit(cancel)
            finished.result(timeout=5)
            accepted, _ = cancelled.result(timeout=5)
        body = service.control.get(identity)
        assert body["state"] == ("cancelled" if accepted else "completed")
        assert service.store.capacity_status()["reserved_bytes"] == 0
        assert not service.control.jobs
    finally:
        lease.release(clean=True)


def test_read_connections_cannot_write(service):
    with (
        service.store.transaction(readonly=True, timeout=0) as db,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        db.execute("DELETE FROM jobs")
    assert isinstance(service.control, ControlPlane)


def test_successful_pending_commit_does_not_require_another_read(service, monkeypatch):
    job, lease = submit(service)
    identity = job["job_id"]
    service.control.track(job, threading.Event())

    def fail(*args, **kwargs):
        raise ServiceError("IO_ERROR", "injected storage fault")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(service.store, "finish", fail)
            service.control.finish(identity, state="cancelled", cleanup="confirmed")
        with monkeypatch.context() as patch:
            patch.setattr(service.store, "job", fail)
            response = asyncio.run(service.call("cq_job_get", {"job_id": identity}))
        assert response["ok"] and not response["warnings"], response
        assert response["data"]["state"] == "cancelled"
        assert response["data"]["state_persisted"]
        assert response["data"]["state_source"] == "state_store"
        assert "persistence_error" not in response["data"]
        assert service.store.job(identity)["state"] == "cancelled"
        assert service.store.capacity_status()["reserved_bytes"] == 0
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("action", ["release", "hold", "cancel", "deadline", "budget"])
def test_startup_contention_is_bounded_cancellable_and_never_spawns_early(
    service, tmp_path, action, record_property
):
    # A real, separate SQLite writer blocks the durable running transition.
    job, lease = submit(service)
    if action == "deadline":
        job["timeout_seconds"] = 0.2
    elif action == "budget":
        job["timeout_seconds"] = 1
    identity = job["job_id"]
    event = threading.Event()
    service.control.track(job, event)
    marker = tmp_path / "spawned"
    service._job_command = lambda job: [
        sys.executable,
        "-c",
        "from pathlib import Path; "
        f"Path({str(marker)!r}).touch(); "
        + ("import time; time.sleep(0.85); " if action == "budget" else "")
        + 'print(\'{"all_available": true, "tools": []}\')',
    ]

    async def scenario():
        started = time.monotonic()
        with writer(service.store, tmp_path):
            task = asyncio.create_task(asyncio.to_thread(service._worker, job, lease, event))
            await asyncio.sleep(0.3 if action in ("release", "budget") else 0.05)
            if action in ("release", "budget"):
                assert not task.done(), "Transient contention prematurely failed the job"
                queried_at = time.monotonic()
                queued = await service.call("cq_job_get", {"job_id": identity})
                assert time.monotonic() - queried_at < 1
                assert queued["ok"] and queued["data"]["state"] == "queued", queued
            elif action == "cancel":
                cancelled = await service.call("cq_job_cancel", {"job_id": identity})
                assert cancelled["ok"] and cancelled["data"]["cancellation_requested"]
            if action not in ("release", "budget"):
                await asyncio.wait_for(asyncio.shield(task), timeout=3.5)
                assert time.monotonic() - started < 3.5
            assert not marker.exists(), "Command spawned without durable running state"
        await asyncio.wait_for(task, timeout=5)
        response = await service.call("cq_job_get", {"job_id": identity})
        body = response["data"]
        assert response["ok"] and body["state_persisted"], response
        assert (
            body["state"]
            == {
                "release": "completed",
                "hold": "failed",
                "cancel": "cancelled",
                "deadline": "timed_out",
                "budget": "timed_out",
            }[action]
        )
        assert marker.exists() == (action in ("release", "budget"))
        if action == "hold":
            assert body["error"]["code"] == "STATE_BUSY"
        assert body["cleanup"] == "confirmed"
        assert service.store.capacity_status()["reserved_bytes"] == 0
        record_property(
            "startup_contention",
            json.dumps({"action": action, "seconds": time.monotonic() - started}),
        )
        await service.close()

    try:
        asyncio.run(scenario())
    finally:
        event.set()
        lease.release(clean=lease.safe)


def test_startup_io_error_is_not_retried_or_executed(service, monkeypatch):
    job, lease = submit(service)
    identity = job["job_id"]
    service.control.track(job, threading.Event())
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(args)
        raise ServiceError("IO_ERROR", "storage unavailable")

    monkeypatch.setattr(service.store, "update_job", fail)
    monkeypatch.setattr(service, "_job_command", lambda job: pytest.fail("Must not spawn"))
    service._worker(job, lease, threading.Event())
    body = service.store.job(identity)
    assert len(attempts) == 1
    assert body["state"] == "failed" and body["error"]["code"] == "IO_ERROR"
    assert service.store.capacity_status()["reserved_bytes"] == 0
