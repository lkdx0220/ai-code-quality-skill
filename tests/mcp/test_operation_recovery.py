"""Recover operation reservations only under a verified clean project lease."""

import asyncio
import json
import os
import signal
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from ai_code_quality import scan
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.config import Config
from ai_code_quality.mcp.contracts import ServiceError
from ai_code_quality.mcp.locking import ProjectLock, group_members, process_identity
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings
from ai_code_quality.mcp.store import RESERVATION, Store
from ai_code_quality.schema import AdapterResult


@pytest.fixture
def service(tmp_path):
    if os.name == "nt":
        pytest.importorskip("win32api")
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    return Service(Settings(project, tmp_path / "state", tool_python=sys.executable))


def reservations(store):
    with closing(sqlite3.connect(store.path)) as db:
        return dict(db.execute("SELECT id,bytes FROM reservations ORDER BY id"))


def orphan(store, identity="op-legacy"):
    # Legacy rows have no new metadata and must work without a schema migration.
    with store.transaction() as db:
        store.reserve(db, identity)


def runs(service, monkeypatch):
    class Quiet(Adapter):
        name = "ruff-check"

        def run(self, ctx):
            return AdapterResult(name=self.name, tool="ruff", status="ok", version="fixture")

    monkeypatch.setattr(scan, "get_adapters", lambda _: [Quiet()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    for identity in ("base", "target"):
        scan.run_scan(service.settings.project, cfg=Config(), run_id=identity)


@pytest.mark.parametrize("operation", ["cq_doctor", "cq_scan_start"])
def test_new_job_reclaims_old_operations_before_quota_check(service, operation):
    service.store.capacity = 27 * 1024 * 1024
    orphan(service.store)
    assert reservations(service.store) == {"op-legacy": RESERVATION}
    args = {"request_key": "after-crash"}
    if operation == "cq_scan_start":
        args["adapters"] = ["ruff-check"]
    _, (job, lease) = service._submit(operation, args)
    try:
        assert reservations(service.store) == {job["job_id"]: RESERVATION}
        assert job["state"] == "queued"
        service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("operation", ["cq_gate", "cq_diff"])
def test_quality_reclaims_before_quota_and_preserves_evidence(service, monkeypatch, operation):
    runs(service, monkeypatch)
    old = service.store.artifact("report", "immutable old evidence", {})
    cursor = service.store.cursor("old-binding", 4)
    orphan(service.store)
    service.store.capacity = 27 * 1024 * 1024
    saved = {p: p.read_bytes() for p in service.settings.project.rglob("*") if p.is_file()}
    args = {"run_id": "target", "base_run_id": "base", "verify_current": False}
    response = asyncio.run(service.call(operation, args))
    assert response["ok"], response
    assert reservations(service.store) == {}
    assert service.store.read_artifact(old["artifact_id"])[1] == "immutable old evidence"
    assert service.store.read_cursor(cursor, "old-binding") == ("old-binding", 4)
    assert saved == {p: p.read_bytes() for p in saved}


@pytest.mark.parametrize("bad_lease", ["released", "unsafe", "wrong_project"])
def test_recovery_requires_matching_held_clean_lease(service, tmp_path, bad_lease):
    orphan(service.store)
    lease = ProjectLock(
        service.settings.project_identity if bad_lease != "wrong_project" else str(tmp_path)
    ).acquire()
    try:
        if bad_lease == "released":
            lease.release(clean=True)
        elif bad_lease == "unsafe":
            lease.safe = False
        with pytest.raises(ServiceError) as error, service.store.transaction() as db:
            service.store.recover_operations(db, lease)
        assert error.value.code == "CLEANUP_FAILED"
        assert reservations(service.store) == {"op-legacy": RESERVATION}
    finally:
        lease.release(clean=True)


def test_job_reservations_and_other_state_are_never_reclaimed(service, tmp_path):
    orphan(service.store)
    with service.store.transaction() as db:
        service.store.reserve(db, "j-unfinished", 1234)
        service.store.reserve(db, "a-other", 5678)
        # Defensive: even an op-like identity associated with a job is preserved.
        service.store.reserve(db, "op-job", 111)
        db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?)", ("op-job", "key", "digest", "queued", "{}")
        )
    other = Store(tmp_path / "other-state", service.settings.project_identity)
    orphan(other, "op-other-state")
    lease = ProjectLock(service.settings.project_identity).acquire()
    try:
        with service.store.transaction() as db:
            service.store.recover_operations(db, lease)
        assert reservations(service.store) == {"j-unfinished": 1234, "a-other": 5678, "op-job": 111}
        assert reservations(other) == {"op-other-state": RESERVATION}
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("entry", ["job", "quality"])
def test_recovery_does_not_run_while_another_operation_holds_lock(service, entry):
    orphan(service.store)
    lease = ProjectLock(service.settings.project_identity).acquire()
    before = reservations(service.store)
    try:
        operation, args = (
            ("cq_doctor", {"request_key": "blocked"})
            if entry == "job"
            else ("cq_gate", {"run_id": "missing"})
        )
        response = asyncio.run(service.call(operation, args))
        assert response["error"]["code"] == "PROJECT_BUSY", response
        assert reservations(service.store) == before
    finally:
        lease.release(clean=True)


@pytest.mark.parametrize("entry", ["job", "quality"])
def test_recovery_and_new_reservation_roll_back_together(service, monkeypatch, entry):
    orphan(service.store)
    original = service.store.reserve

    def fail(db, identity, *args, **kwargs):
        assert "op-legacy" not in dict(db.execute("SELECT id,bytes FROM reservations"))
        original(db, identity, *args, **kwargs)
        raise ServiceError("IO_ERROR", "injected after recovery and reserve")

    with monkeypatch.context() as patch:
        patch.setattr(service.store, "reserve", fail)
        operation, args = (
            ("cq_doctor", {"request_key": "retry"})
            if entry == "job"
            else ("cq_gate", {"run_id": "missing"})
        )
        response = asyncio.run(service.call(operation, args))
    assert response["error"]["code"] == "IO_ERROR", response
    assert reservations(service.store) == {"op-legacy": RESERVATION}
    _, (job, lease) = service._submit("cq_doctor", {"request_key": "retry"})
    try:
        assert reservations(service.store) == {job["job_id"]: RESERVATION}
        service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    finally:
        lease.release(clean=True)


def test_duplicate_key_does_not_take_lock_or_clean_operations(service):
    accepted, (job, lease) = service._submit("cq_doctor", {"request_key": "same-key"})
    service.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    lease.release(clean=True)
    orphan(service.store)
    blocker = ProjectLock(service.settings.project_identity).acquire()
    try:
        reused, worker = service._submit("cq_doctor", {"request_key": "same-key"})
        assert worker is None and reused["reused"] and reused["job_id"] == accepted["job_id"]
        assert reservations(service.store) == {"op-legacy": RESERVATION}
    finally:
        blocker.release(clean=True)


@pytest.mark.parametrize("intent", ["creating", "damaged"])
@pytest.mark.parametrize("entry", ["job", "quality"])
def test_unknown_execution_intent_cannot_release_reservations(service, intent, entry):
    orphan(service.store)
    lease = ProjectLock(service.settings.project_identity).acquire()
    clean = lease.owner_path.read_bytes()
    lease.owner_path.write_text(
        "not JSON"
        if intent == "damaged"
        else json.dumps(
            {
                "phase": "creating",
                "owner_pid": os.getpid(),
                "owner_birth": process_identity(os.getpid()),
            }
        ),
        encoding="utf-8",
    )
    lease.release(clean=False)
    try:
        operation, args = (
            ("cq_doctor", {"request_key": "uncertain"})
            if entry == "job"
            else ("cq_gate", {"run_id": "missing"})
        )
        response = asyncio.run(service.call(operation, args))
        assert response["error"]["code"] == "CLEANUP_FAILED", response
        assert reservations(service.store) == {"op-legacy": RESERVATION}
    finally:
        # Only restore this test's positively owned isolated intent file.
        lease.owner_path.write_bytes(clean)


def test_cross_state_activity_blocks_recovery_and_cleaning_remains_local(service, tmp_path):
    other = Service(
        Settings(service.settings.project, tmp_path / "other-state", tool_python=sys.executable)
    )
    orphan(service.store)
    orphan(other.store, "op-other-state")
    lease = ProjectLock(service.settings.project_identity).acquire()
    try:
        response = asyncio.run(other.call("cq_doctor", {"request_key": "blocked"}))
        assert response["error"]["code"] == "PROJECT_BUSY", response
        assert reservations(service.store) == {"op-legacy": RESERVATION}
        assert reservations(other.store) == {"op-other-state": RESERVATION}
    finally:
        lease.release(clean=True)
    _, (job, following) = other._submit("cq_doctor", {"request_key": "after-release"})
    try:
        assert reservations(other.store) == {job["job_id"]: RESERVATION}
        assert reservations(service.store) == {"op-legacy": RESERVATION}
        other.store.finish(job["job_id"], state="cancelled", cleanup="confirmed")
    finally:
        following.release(clean=True)


def read_marker(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


async def until(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.02)
    raise AssertionError("Operation crash fixture timed out")


def payload(response):
    value = json.loads(response.content[0].text)
    assert value == response.structured_content
    assert response.is_error == (not value["ok"])
    return value


@pytest.mark.parametrize("operation", ["cq_gate", "cq_diff"])
@pytest.mark.parametrize("phase", ["reserved", "active", "snapshot"])
@pytest.mark.parametrize("trigger", ["quality", "scan"])
def test_real_stdio_crash_recovers_operations_without_losing_evidence(
    service, tmp_path, monkeypatch, operation, phase, trigger, record_property
):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters, stdio_client
    from mcp.shared.exceptions import MCPError

    runs(service, monkeypatch)
    old = service.store.artifact("report", "old immutable evidence", {})
    saved = {p: p.read_bytes() for p in service.settings.project.rglob("*") if p.is_file()}
    marker = tmp_path / "barrier.json"
    fixture = Path(__file__).parent / "fixtures/op_stdio_server.py"
    runtime = os.environ.get("CQ_MCP_FAULT_SERVER_PYTHON", sys.executable)
    settings = service.settings
    lock = ProjectLock(settings.project_identity)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    ordinary = [
        "-m",
        "ai_code_quality.mcp",
        "--project",
        str(settings.project),
        "--state-dir",
        str(settings.state),
        "--tool-python",
        os.environ.get("CQ_MCP_TEST_TOOL_PYTHON", runtime),
    ]
    arguments = {"run_id": "target", "base_run_id": "base", "verify_current": False}
    record = {
        "operation": operation,
        "phase": phase,
        "trigger": trigger,
        "directory": str(tmp_path),
    }
    owner, birth, tree = None, None, None

    def params(args):
        return StdioServerParameters(command=runtime, args=args, env=env)

    async def run():
        nonlocal owner, birth, tree
        first = [str(fixture), phase, str(marker), str(settings.project), str(settings.state)]
        with (tmp_path / "first-stderr.log").open("w", encoding="utf-8") as stderr:
            async with (
                stdio_client(params(first), errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=20) as session,
            ):
                await session.initialize()
                pending = asyncio.create_task(session.call_tool(operation, arguments))
                boundary = await until(lambda: read_marker(marker))
                intent = read_marker(lock.owner_path)
                owner = boundary.get("owner", intent.get("owner_pid"))
                birth = process_identity(owner)
                tree = boundary if phase == "active" else None
                before = reservations(service.store)
                assert len(before) == 1 and next(iter(before)).startswith("op-")
                if phase == "reserved":
                    assert sum(before.values()) == RESERVATION
                record.update(owner=owner, owner_birth=birth, before=before, boundary=boundary)
                if phase == "reserved" and trigger == "quality":
                    # A second OS process must not reclaim a live server's reservation.
                    with (tmp_path / "contender-stderr.log").open("w", encoding="utf-8") as err:
                        async with (
                            stdio_client(params(ordinary), errlog=err) as (r2, w2),
                            ClientSession(r2, w2) as contender,
                        ):
                            await contender.initialize()
                            busy = payload(await contender.call_tool(operation, arguments))
                            assert busy["error"]["code"] == "PROJECT_BUSY", busy
                            assert reservations(service.store) == before
                os.kill(owner, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
                with pytest.raises(MCPError):
                    await pending
                await until(lambda: process_identity(owner) != birth)

        with (tmp_path / "recovery-stderr.log").open("w", encoding="utf-8") as stderr:
            async with (
                stdio_client(params(ordinary), errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=20) as session,
            ):
                await session.initialize()
                # initialize/read never perform unverified cleanup.
                old_read = payload(
                    await session.call_tool("cq_artifact_get", {"artifact_id": old["artifact_id"]})
                )
                assert old_read["ok"] and old_read["data"]["text"] == "old immutable evidence"
                assert reservations(service.store) == before
                if tree and os.name != "nt":
                    assert process_identity(tree["pid"]) == tree["birth"]
                    assert process_identity(tree["child"]) == tree["child_birth"]
                    for op, args in (
                        (operation, arguments),
                        ("cq_scan_start", {"request_key": "orphaned", "adapters": ["ruff-check"]}),
                    ):
                        blocked = payload(await session.call_tool(op, args))
                        assert blocked["error"]["code"] == "CLEANUP_FAILED", blocked
                        assert reservations(service.store) == before
                    record["live_orphan_blocked"] = True
                    os.killpg(tree["group"], signal.SIGKILL)
                    await until(lambda: not group_members(tree["group"]))
                elif tree:
                    await until(lambda: process_identity(tree["pid"]) != tree["birth"])
                    await until(lambda: process_identity(tree["child"]) != tree["child_birth"])
                    record["job_object_reaped_tree"] = True
                if trigger == "quality":
                    recovered = payload(await session.call_tool(operation, arguments))
                    assert recovered["ok"], recovered
                else:
                    accepted = payload(
                        await session.call_tool(
                            "cq_scan_start",
                            {"request_key": "after-crash", "adapters": ["ruff-check"]},
                        )
                    )
                    assert accepted["ok"] and not accepted["data"]["reused"], accepted
                    for _ in range(200):
                        recovered = payload(
                            await session.call_tool(
                                "cq_job_get", {"job_id": accepted["data"]["job_id"]}
                            )
                        )
                        assert recovered["ok"], recovered
                        if recovered["data"]["state"] in (
                            "completed",
                            "failed",
                            "cancelled",
                            "timed_out",
                        ):
                            break
                        await asyncio.sleep(0.02)
                    assert recovered["data"]["state"] == "completed", recovered
                assert reservations(service.store) == {}
                assert saved == {p: p.read_bytes() for p in saved}
                if phase == "snapshot":
                    snapshot = boundary["artifact"]
                    read_back = payload(
                        await session.call_tool(
                            "cq_artifact_get", {"artifact_id": snapshot["artifact_id"]}
                        )
                    )
                    assert read_back["ok"] and read_back["data"]["sha256"] == snapshot["sha256"]
                    record["committed_snapshot_preserved"] = True
                record.update(after=reservations(service.store), old_evidence_preserved=True)

    try:
        asyncio.run(run())
    finally:
        if owner and process_identity(owner) == birth:
            os.kill(owner, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
        if tree and os.name != "nt" and process_identity(tree["pid"]) == tree["birth"]:
            os.killpg(tree["group"], signal.SIGKILL)
    (tmp_path / "proof.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    record_property("operation_crash", json.dumps(record))
