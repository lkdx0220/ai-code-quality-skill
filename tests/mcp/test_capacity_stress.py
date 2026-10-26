"""Opt-in capacity acceptance, with real SQLite and explicit fixture boundaries.

Run with CQ_MCP_CAPACITY_STRESS=1. Small-job pressure exercises acceptance and
settlement directly; process-race and control-channel cases start actual subprocesses.
"""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_code_quality.mcp.contracts import CAPTURE_LIMIT, ServiceError, encode, wire
from ai_code_quality.mcp.locking import ProjectLock, process_identity
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings
from ai_code_quality.mcp.store import CONTROL_HEADROOM, RESERVATION, Store

pytestmark = pytest.mark.skipif(
    os.environ.get("CQ_MCP_CAPACITY_STRESS") != "1",
    reason="Opt-in disk/transaction pressure: set CQ_MCP_CAPACITY_STRESS=1",
)


@pytest.fixture
def capacity_service(tmp_path):
    if os.name == "nt":
        pytest.importorskip("win32api", reason="Real Windows process-domain dependency required")
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    return Service(Settings(project, tmp_path / "state", tool_python=sys.executable))


def record(record_property, name, value):
    record_property(name, encode(value))
    print(name + ": " + encode(value), flush=True)


def successful(response):
    assert response["ok"], response
    assert len(encode(wire(response)).encode("utf-8")) <= 65536
    return response["data"]


def settle_small_job(service, key):
    accepted, (job, lease) = service._submit("cq_doctor", {"request_key": key})
    try:
        artifact = service.store.artifact(
            "job_diagnostic", "x" * 1024, {"job_id": job["job_id"]}, reservation=job["job_id"]
        )
        service.store.finish(
            job["job_id"],
            state="completed",
            cleanup="confirmed",
            cq_exit_code=0,
            result={"artifact": artifact},
        )
        return accepted, artifact
    finally:
        lease.release(clean=lease.safe)


def test_one_thousand_small_jobs_preserve_results_and_idempotency(
    capacity_service, record_property
):
    service = capacity_service
    start = time.monotonic()
    accepted = [settle_small_job(service, "small-" + str(index)) for index in range(1000)]
    status = service.store.capacity_status()
    assert status["jobs"] == 1000 and status["reserved_bytes"] == 0
    assert status["artifact_payload_bytes"] >= 1000 * 1024
    assert status["physical_bytes"] < status["limit_bytes"] - CONTROL_HEADROOM
    assert len({item[0]["job_id"] for item in accepted}) == 1000
    reopened = Store(service.settings.state, service.settings.project_identity)
    for job, artifact in accepted:
        assert reopened.job(job["job_id"])["state"] == "completed"
        assert reopened.read_artifact(artifact["artifact_id"])[1] == "x" * 1024

    async def controls():
        try:
            rejected = await service.call("cq_doctor", {"request_key": "job-1001"})
            assert rejected["error"]["code"] == "STATE_LIMIT", rejected
            assert service.store.capacity_status()["jobs"] == 1000
            duplicate = successful(await service.call("cq_doctor", {"request_key": "small-0"}))
            assert duplicate["reused"] and duplicate["job_id"] == accepted[0][0]["job_id"]
            assert duplicate["terminal_state"] == "completed"
            for job, artifact in (accepted[0], accepted[-1]):
                found = successful(await service.call("cq_job_get", {"job_id": job["job_id"]}))
                assert found["state"] == "completed"
                cancelled = successful(
                    await service.call("cq_job_cancel", {"job_id": job["job_id"]})
                )
                assert cancelled["cancellation_requested"] is False
                snapshot = successful(
                    await service.call("cq_artifact_get", {"artifact_id": artifact["artifact_id"]})
                )
                assert snapshot["text"] == "x" * 1024
        finally:
            await service.close()

    asyncio.run(controls())
    record(record_property, "small_jobs", {**status, "seconds": time.monotonic() - start})


def test_ten_thousand_cursors_reuse_expire_and_survive_restart(tmp_path, record_property):
    store = Store(tmp_path / "state", "cursor-project")
    start = time.monotonic()
    tokens = [store.cursor("fixed-binding", position) for position in range(10000)]
    assert len(set(tokens)) == 10000
    before = store.capacity_status()
    assert before["cursors"] == 10000 and before["reserved_bytes"] == 0
    assert store.cursor("fixed-binding", 9999) == tokens[-1]
    with pytest.raises(ServiceError) as full:
        store.cursor("fixed-binding", 10000)
    assert full.value.code == "STATE_LIMIT"
    reopened = Store(store.root, "cursor-project")
    for position, token in enumerate(tokens):
        assert reopened.read_cursor(token, "fixed-binding") == ("fixed-binding", position)
    with reopened.transaction() as db:
        db.execute("UPDATE cursors SET expires=0 WHERE id=?", (tokens[0],))
    with pytest.raises(ServiceError) as stale:
        reopened.read_cursor(tokens[0])
    assert stale.value.code == "STALE_CURSOR"
    replacement = reopened.cursor("fixed-binding", 10000)
    assert replacement not in tokens
    after = reopened.capacity_status()
    assert after["cursors"] == 10000 and after["reserved_bytes"] == 0
    assert reopened.read_cursor(tokens[-1], "fixed-binding") == ("fixed-binding", 9999)
    record(
        record_property,
        "cursors",
        {"before": before, "after_expiry_reclaim": after, "seconds": time.monotonic() - start},
    )


def test_one_hundred_maximum_snapshot_attempts_obey_default_capacity(tmp_path, record_property):
    store = Store(tmp_path / "state", "snapshot-project")
    payload = "x" * CAPTURE_LIMIT
    expected = hashlib.sha256(payload.encode()).hexdigest()
    accepted, rejected, checkpoints = [], [], []
    start = time.monotonic()
    for index in range(100):
        reservation = "snapshot-" + str(index)
        reserved = False
        try:
            with store.transaction() as db:
                store.reserve(db, reservation)
            reserved = True
            artifact = store.artifact("diff_result", payload, {}, reservation=reservation)
            assert artifact["sha256"] == expected and artifact["size_chars"] == CAPTURE_LIMIT
            accepted.append(artifact)
        except ServiceError as exc:
            assert exc.code == "STATE_LIMIT"
            rejected.append(index)
        finally:
            if reserved:
                store.release(reservation)
        status = store.capacity_status()
        assert status["reserved_bytes"] == 0
        assert status["physical_bytes"] < status["limit_bytes"] - CONTROL_HEADROOM
        checkpoints.append(status["physical_bytes"])
    assert 1 <= len(accepted) < 30 and len(accepted) + len(rejected) == 100
    assert rejected == list(range(len(accepted), 100)), "No eviction or intermittent acceptance"
    assert all(value == checkpoints[len(accepted) - 1] for value in checkpoints[len(accepted) :])
    reopened = Store(store.root, "snapshot-project")
    for artifact in accepted:
        _, text, digest, _ = reopened.read_artifact(artifact["artifact_id"])
        assert len(text) == CAPTURE_LIMIT and digest == expected
    with store.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == len(accepted)
    record(
        record_property,
        "maximum_snapshots",
        {
            "attempts": 100,
            "accepted": len(accepted),
            "rejected": len(rejected),
            "first_rejected_index": rejected[0],
            "status": store.capacity_status(),
            "seconds": time.monotonic() - start,
        },
    )


def test_competing_connections_cannot_oversell_reservations(tmp_path, record_property):
    root = tmp_path / "state"
    stores = [Store(root, "race-project", capacity=27 * 1024 * 1024) for _ in range(8)]
    rounds = []
    for turn in range(3):
        barrier = threading.Barrier(8)

        def reserve(index, turn=turn, barrier=barrier):
            identity = f"race-{turn}-{index}"
            barrier.wait(timeout=10)
            try:
                with stores[index].transaction() as db:
                    stores[index].reserve(db, identity)
                return identity, "accepted"
            except ServiceError as exc:
                return identity, exc.code

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        winners = [identity for identity, outcome in results if outcome == "accepted"]
        assert len(winners) == 1, results
        assert all(outcome in ("accepted", "STATE_LIMIT") for _, outcome in results)
        status = stores[0].capacity_status()
        assert status["reserved_bytes"] == RESERVATION
        assert status["physical_bytes"] + RESERVATION <= status["limit_bytes"] - CONTROL_HEADROOM
        artifact = stores[0].artifact("gate_result", "settled", {}, reservation=winners[0])
        stores[0].release(winners[0])
        assert stores[0].read_artifact(artifact["artifact_id"])[1] == "settled"
        assert stores[0].capacity_status()["reserved_bytes"] == 0
        rounds.append(results)
    record(record_property, "reservation_races", rounds)


def test_eight_processes_share_one_atomic_reservation_budget(tmp_path, record_property):
    store = Store(tmp_path / "state", "process-race", capacity=27 * 1024 * 1024)
    coordination = tmp_path / "coordination"
    coordination.mkdir()
    fixture = Path(__file__).parent / "fixtures/capacity_reserver.py"
    processes = []
    try:
        for index in range(8):
            processes.append(
                subprocess.Popen(
                    [sys.executable, str(fixture), str(store.root), str(coordination), str(index)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        deadline = time.monotonic() + 15
        while len(list(coordination.glob("*.ready"))) != 8:
            assert all(process.poll() is None for process in processes), "Contender exited early"
            assert time.monotonic() < deadline, "Not all reservation contenders became ready"
            time.sleep(0.02)
        (coordination / "go").write_text("go", encoding="utf-8")
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
            results.append(json.loads(stdout))
        winners = [item for item in results if item["outcome"] == "accepted"]
        assert len(winners) == 1, results
        assert all(item["outcome"] in ("accepted", "STATE_LIMIT") for item in results)
        assert store.capacity_status()["reserved_bytes"] == RESERVATION
        store.release(winners[0]["identity"])
        assert store.capacity_status()["reserved_bytes"] == 0
        record(record_property, "process_reservation_race", results)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def test_capacity_pressure_preserves_real_process_cancel_and_existing_reads(
    capacity_service, monkeypatch, record_property
):
    service = capacity_service
    service.store.capacity = 27 * 1024 * 1024  # Smaller fixture, same 16 MiB control reserve.
    finished, artifact = settle_small_job(service, "already-finished")
    marker = service.settings.state.parent / "child.json"
    child_code = (
        "import json,os,time; from pathlib import Path; "
        f"Path({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid()}})); time.sleep(40)"
    )
    monkeypatch.setattr(service, "_job_command", lambda job: [sys.executable, "-c", child_code])

    async def controls():
        try:
            accepted = successful(await service.call("cq_doctor", {"request_key": "active"}))
            identity = accepted["job_id"]
            deadline = time.monotonic() + 10
            while not marker.exists():
                assert time.monotonic() < deadline, "Controlled subprocess did not start"
                await asyncio.sleep(0.02)
            pid = json.loads(marker.read_text())["pid"]
            assert process_identity(pid) is not None
            listing = successful(await service.call("cq_runs_list", {"limit": 1}))
            assert listing["total"] == 2 and listing["next_cursor"]
            status = service.store.capacity_status()
            # Count a real state file; leave less than the 64 KiB metadata margin.
            pad_bytes = (
                status["limit_bytes"]
                - CONTROL_HEADROOM
                - status["reserved_bytes"]
                - status["physical_bytes"]
                - 32768
            )
            assert pad_bytes > 0
            (service.store.root / "quota-pressure.bin").write_bytes(b"0" * pad_bytes)
            responses = {}
            for operation, arguments in (
                ("cq_doctor", {"request_key": "while-full"}),
                ("cq_scan_start", {"request_key": "while-full", "adapters": ["ruff-check"]}),
                ("cq_runs_list", {}),
            ):
                response = await service.call(operation, arguments)
                assert response["error"]["code"] == "STATE_LIMIT", response
                responses[operation] = response["error"]["code"]
            duplicate = successful(await service.call("cq_doctor", {"request_key": "active"}))
            assert duplicate["reused"] and duplicate["job_id"] == identity
            snapshot = successful(
                await service.call("cq_artifact_get", {"artifact_id": artifact["artifact_id"]})
            )
            assert snapshot["text"] == "x" * 1024
            resumed = successful(
                await service.call("cq_runs_list", {"limit": 1, "cursor": listing["next_cursor"]})
            )
            assert resumed["returned"] == 1 and resumed["next_cursor"] is None
            assert len({listing["items"][0]["id"], resumed["items"][0]["id"]}) == 2
            start = time.monotonic()
            found = successful(await service.call("cq_job_get", {"job_id": identity}))
            get_seconds = time.monotonic() - start
            assert found["state"] == "running" and get_seconds < 1
            start = time.monotonic()
            cancelled = successful(await service.call("cq_job_cancel", {"job_id": identity}))
            cancel_seconds = time.monotonic() - start
            assert cancelled["cancellation_requested"] and cancel_seconds < 1
            deadline = time.monotonic() + 10
            while True:
                found = successful(await service.call("cq_job_get", {"job_id": identity}))
                if found["state"] == "cancelled":
                    break
                assert time.monotonic() < deadline, found
                await asyncio.sleep(0.02)
            assert found["cleanup"] == "confirmed" and found["result"] is None
            assert process_identity(pid) is None
            assert service.store.capacity_status()["reserved_bytes"] == 0
            assert service.store.job(finished["job_id"])["state"] == "completed"
            lease = ProjectLock(service.settings.project_identity).acquire()
            lease.release(clean=True)
            assert not (service.settings.project / "audits").exists()
            record(
                record_property,
                "control_at_capacity",
                {
                    "fixture_capacity": service.store.capacity,
                    "padding_bytes": pad_bytes,
                    "rejections": responses,
                    "get_seconds": get_seconds,
                    "cancel_seconds": cancel_seconds,
                    "terminal_state": found["state"],
                    "cleanup": found["cleanup"],
                    "status": service.store.capacity_status(),
                },
            )
        finally:
            await service.close()

    asyncio.run(controls())
