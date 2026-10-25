import asyncio
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from ai_code_quality import scan
from ai_code_quality.adapters import ADAPTER_NAMES
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.config import Config
from ai_code_quality.evidence import atomic_json, publish_run
from ai_code_quality.mcp.contracts import ADAPTERS, SCHEMAS, ServiceError, encode, validate, wire
from ai_code_quality.mcp.locking import ProjectLock, process_identity
from ai_code_quality.mcp.processes import execute
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings
from ai_code_quality.mcp.store import Store
from ai_code_quality.schema import AdapterResult


@pytest.fixture
def settings(tmp_path):
    if os.name == "nt":
        pytest.importorskip(
            "win32api", reason="Process-domain tests require the optional Windows MCP dependency"
        )
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    return Settings(
        project,
        tmp_path / "state",
        tool_python=os.environ.get("CQ_MCP_TEST_TOOL_PYTHON", sys.executable),
    )


def make_run(settings, monkeypatch, identity="sample", status="ok"):
    class Quiet(Adapter):
        name = "ruff-check"

        def run(self, ctx):
            return AdapterResult(
                name=self.name,
                tool="ruff",
                status=status,
                version="fixture-1",
                reason="fixture status",
            )

    monkeypatch.setattr(scan, "get_adapters", lambda _: [Quiet()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    return scan.run_scan(
        settings.project,
        cfg=Config(python=settings.tool_python, python_source="cli"),
        run_id=identity,
    )


def call(service, operation, **arguments):
    return asyncio.run(service.call(operation, arguments))


def test_adapter_policy_matches_core():
    assert set(ADAPTERS) == set(ADAPTER_NAMES)
    assert len(SCHEMAS) == 9
    assert all(spec["additionalProperties"] is False for spec in SCHEMAS.values())


@pytest.mark.parametrize(
    "arguments",
    [
        {"request_key": "x", "adapters": []},
        {"request_key": "x", "adapters": ["ruff-check"] * 2},
        {"request_key": "../escape"},
        {"request_key": "NUL"},
        {"request_key": "x", "timeout_seconds": True},
        {"request_key": "x", "shell": "anything"},
        {"request_key": "x", "adapters": [1]},
    ],
)
def test_invalid_arguments_are_rejected_before_side_effects(arguments):
    with pytest.raises(ServiceError) as error:
        validate("cq_scan_start", arguments)
    assert error.value.code == "INVALID_ARGUMENT"


def test_state_binding_and_cursor_restart(tmp_path):
    store = Store(tmp_path / "state", "project-one")
    token = store.cursor("binding", 3)
    assert store.cursor("binding", 3) == token
    reopened = Store(tmp_path / "state", "project-one")
    assert reopened.read_cursor(token, "binding") == ("binding", 3)
    with pytest.raises(ServiceError) as changed:
        reopened.read_cursor(token, "other")
    assert changed.value.code == "STALE_CURSOR"
    with pytest.raises(ServiceError) as mismatch:
        Store(tmp_path / "state", "project-two")
    assert mismatch.value.code == "STATE_PROJECT_MISMATCH"


def test_state_reservations_are_transient_and_atomic(tmp_path):
    store = Store(tmp_path / "state", "project", capacity=27 * 1024 * 1024)
    with store.transaction() as db:
        store.reserve(db, "one")
    with pytest.raises(ServiceError) as full, store.transaction() as db:
        store.reserve(db, "two")
    assert full.value.code == "STATE_LIMIT"
    artifact = store.artifact("gate_result", {"passed": True}, {}, reservation="one")
    store.release("one")
    with store.transaction() as db:
        store.reserve(db, "two")
    assert store.read_artifact(artifact["artifact_id"])[1] == '{"passed":true}'


def test_all_skipped_cannot_become_mcp_pass(settings, monkeypatch):
    make_run(settings, monkeypatch, status="skipped")
    service = Service(settings)
    result = call(service, "cq_gate", run_id="sample", verify_current=False)
    assert result["ok"], result
    assert result["data"]["core_gate"]["passed"] is True
    assert result["data"]["verdict"] == "cannot_judge"
    assert result["data"]["evidence"]["runtime_gaps"]


def test_freshness_history_stale_and_no_save(settings, monkeypatch):
    output = make_run(settings, monkeypatch)
    original = {
        path.relative_to(output.run_dir): path.read_bytes()
        for path in output.run_dir.rglob("*")
        if path.is_file()
    }
    service = Service(settings)
    historical = call(service, "cq_gate", run_id="sample", verify_current=False)
    assert historical["ok"] and historical["data"]["verdict"] == "pass_historical", historical
    current = call(service, "cq_gate", run_id="sample")
    assert current["ok"] and current["data"]["verdict"] == "pass_with_gaps", current
    (settings.project / "app.py").write_text("answer = 43\n", encoding="utf-8")
    stale = call(service, "cq_gate", run_id="sample")
    assert stale["ok"] and stale["data"]["verdict"] == "pass_stale", stale
    assert original == {
        path.relative_to(output.run_dir): path.read_bytes()
        for path in output.run_dir.rglob("*")
        if path.is_file()
    }


def test_source_changes_comparable_but_baseline_shadow_is_rejected(settings, monkeypatch):
    make_run(settings, monkeypatch, "base")
    (settings.project / "app.py").write_text("answer = 43\n", encoding="utf-8")
    make_run(settings, monkeypatch, "target")
    service = Service(settings)
    result = call(service, "cq_diff", run_id="target", base_run_id="base")
    assert result["ok"] and result["data"]["comparability"]["comparable"], result
    path = settings.project / "audits/baselines"
    path.mkdir()
    (path / "base.json").write_text('{"findings":[]}', encoding="utf-8")
    rejected = call(service, "cq_diff", run_id="target", base_run_id="base")
    assert rejected["error"]["code"] == "AMBIGUOUS_BASE_RUN"


def test_failed_quality_stays_a_successful_tool_call(settings, monkeypatch):
    output = make_run(settings, monkeypatch)
    payload = {
        "run_id": "sample",
        "findings": [
            {
                "id": "bad",
                "severity": "high",
                "source": "ruff",
                "category": "reliability",
                "rule": "F821",
                "message": "bad",
                "file": "app.py",
                "line": 1,
            }
        ],
    }
    atomic_json(output.run_dir / "findings.json", payload)
    publish_run(output.run_dir, "sample", "0.5.2")
    result = call(Service(settings), "cq_gate", run_id="sample", verify_current=False)
    assert result["ok"] and result["cq_exit_code"] == 1 and result["data"]["verdict"] == "fail", (
        result
    )
    assert wire(result)["isError"] is False


def test_large_finding_progress_unicode_artifact_and_stale_cursor(settings, monkeypatch):
    output = make_run(settings, monkeypatch)
    findings = [
        {"id": "large", "status": "new", "severity": "low", "message": "汉😀\x00" * 60000},
        {"id": "small", "status": "new", "severity": "low", "message": "small"},
    ]
    atomic_json(output.run_dir / "findings.json", {"run_id": "sample", "findings": findings})
    publish_run(output.run_dir, "sample", "0.5.2")
    service = Service(settings)
    first = call(service, "cq_findings_get", run_id="sample", limit=1)
    assert first["ok"], first
    data = first["data"]
    assert data["returned"] == 1 and data["items"][0]["inline"] is False and data["next_cursor"]
    second = call(service, "cq_findings_get", run_id="sample", limit=1, cursor=data["next_cursor"])
    assert second["data"]["items"][0]["finding"]["id"] == "small"
    artifact = data["items"][0]["artifact_id"]
    text, offset = "", 0
    while True:
        chunk = call(service, "cq_artifact_get", artifact_id=artifact, offset=offset, length=8192)
        assert chunk["ok"] and len(encode(wire(chunk)).encode()) <= 65536
        text += chunk["data"]["text"]
        next_offset = chunk["data"]["next_offset"]
        if next_offset is None:
            break
        assert next_offset > offset
        offset = next_offset
    assert json.loads(text) == findings[0]
    findings[1]["message"] = "changed"
    atomic_json(output.run_dir / "findings.json", {"run_id": "sample", "findings": findings})
    publish_run(output.run_dir, "sample", "0.5.2")
    stale = call(service, "cq_findings_get", run_id="sample", limit=1, cursor=data["next_cursor"])
    assert stale["error"]["code"] == "STALE_CURSOR"


def test_project_lock_is_cross_instance_and_cross_state(settings):
    first = ProjectLock(settings.project_identity).acquire()
    try:
        with pytest.raises(ServiceError) as busy:
            ProjectLock(settings.project_identity).acquire()
        assert busy.value.code == "PROJECT_BUSY"
    finally:
        first.release(clean=True)
    second = ProjectLock(settings.project_identity).acquire()
    second.release(clean=True)


@pytest.mark.parametrize("mode", ["normal", "cancelled", "timed_out", "overflow"])
def test_real_process_domain_cleanup(settings, mode):
    marker = settings.project / "child.json"
    script = settings.project / "process_tree.py"
    script.write_text(
        "import json, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(40)'])\n"
        "Path(sys.argv[1]).write_text(json.dumps({'pid': child.pid}))\n"
        + ("print('x' * (9 * 1024 * 1024), flush=True)\n" if mode == "overflow" else "")
        + ("time.sleep(40)\n" if mode in ("cancelled", "timed_out") else ""),
        encoding="utf-8",
    )
    lease = ProjectLock(settings.project_identity).acquire()
    event = threading.Event()
    timer = threading.Timer(1, event.set) if mode == "cancelled" else None
    if timer:
        timer.start()
    try:
        if mode == "overflow":
            with pytest.raises(ServiceError) as too_large:
                execute([sys.executable, str(script), str(marker)], settings, lease, event, 10)
            assert too_large.value.code == "OUTPUT_TOO_LARGE"
        else:
            result = execute(
                [sys.executable, str(script), str(marker)],
                settings,
                lease,
                event,
                1 if mode == "timed_out" else 10,
            )
            assert result["outcome"] == (None if mode == "normal" else mode)
        assert lease.safe
        assert marker.exists()
        assert process_identity(json.loads(marker.read_text())["pid"]) is None
    finally:
        if timer:
            timer.cancel()
        lease.release(clean=lease.safe)


def test_job_dedup_policy_and_terminal_retry(settings):
    async def scenario():
        service = Service(settings)
        try:
            denied = await service.call(
                "cq_scan_start", {"request_key": "denied", "adapters": ["pytest"]}
            )
            assert denied["error"]["code"] == "POLICY_DENIED"
            arguments = {"request_key": "scan", "adapters": ["ruff-check"]}
            first, repeated = await asyncio.gather(
                service.call("cq_scan_start", arguments), service.call("cq_scan_start", arguments)
            )
            assert first["ok"] and repeated["ok"], (first, repeated)
            assert first["data"]["job_id"] == repeated["data"]["job_id"]
            conflict = await service.call("cq_scan_start", {**arguments, "adapters": ["mypy"]})
            assert conflict["error"]["code"] == "REQUEST_CONFLICT"
            identity = first["data"]["job_id"]
            started = time.monotonic()
            while True:
                state = await service.call("cq_job_get", {"job_id": identity})
                assert state["ok"], state
                if state["data"]["state"] in ("completed", "failed", "cleanup_failed"):
                    break
                assert time.monotonic() - started < 15
                await asyncio.sleep(0.05)
            assert state["data"]["state"] == "completed", state
            terminal = await service.call("cq_scan_start", arguments)
            assert terminal["data"]["reused"] and terminal["data"]["terminal_state"] == "completed"
        finally:
            await service.close()

    asyncio.run(scenario())


def test_stdio_initialize_nine_tools_and_valid_domain_result(settings):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters, stdio_client

    async def scenario():
        args = [
            "-m",
            "ai_code_quality.mcp",
            "--project",
            str(settings.project),
            "--state-dir",
            str(settings.state),
            "--tool-python",
            settings.tool_python,
        ]
        parameters = StdioServerParameters(command=sys.executable, args=args, env=settings.env)
        start = time.monotonic()
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write, read_timeout_seconds=15) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            assert time.monotonic() - start < 5
            assert {tool.name for tool in tools.tools} == set(SCHEMAS)
            response = await session.call_tool("cq_runs_list", {})
            assert not response.is_error
            assert json.loads(response.content[0].text) == response.structured_content
            invalid = await session.call_tool("cq_scan_start", {"request_key": "x", "adapters": []})
            assert (
                invalid.is_error
                and invalid.structured_content["error"]["code"] == "INVALID_ARGUMENT"
            )

    asyncio.run(scenario())


def test_cancel_remains_responsive_and_terminal_key_is_not_reexecuted(settings, monkeypatch):
    original = settings.command

    def slow_command(operation, *arguments):
        if operation == "doctor":
            return [sys.executable, "-c", "import time; time.sleep(40)"]
        return original(operation, *arguments)

    monkeypatch.setattr(settings, "command", slow_command)

    async def scenario():
        service = Service(settings)
        try:
            submitted = await service.call("cq_doctor", {"request_key": "slow"})
            identity = submitted["data"]["job_id"]
            await asyncio.sleep(0.3)
            start = time.monotonic()
            cancelled = await service.call("cq_job_cancel", {"job_id": identity})
            assert time.monotonic() - start < 1
            assert cancelled["data"]["cancellation_requested"] is True
            for _ in range(100):
                result = await service.call("cq_job_get", {"job_id": identity})
                if result["data"]["state"] == "cancelled":
                    break
                await asyncio.sleep(0.05)
            assert (
                result["data"]["state"] == "cancelled" and result["data"]["cleanup"] == "confirmed"
            )
            again = await service.call("cq_doctor", {"request_key": "slow"})
            assert (
                again["data"]["job_id"] == identity
                and again["data"]["terminal_state"] == "cancelled"
            )
        finally:
            await service.close()

    asyncio.run(scenario())


def test_cancel_during_submission_does_not_leave_a_queued_job_or_lock(settings, monkeypatch):
    service = Service(settings)
    original = service._submit

    def delayed_accept(*args):
        result = original(*args)
        time.sleep(0.2)
        return result

    monkeypatch.setattr(service, "_submit", delayed_accept)

    async def scenario():
        task = asyncio.create_task(
            service.call("cq_doctor", {"request_key": "cancel-during-submit"})
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await service.close()
        jobs = service.store.all_jobs()
        assert len(jobs) == 1 and jobs[0]["state"] == "cancelled"
        lock = ProjectLock(settings.project_identity).acquire()
        lock.release(clean=True)

    asyncio.run(scenario())


def test_freshness_timeout_never_falls_back_to_historical_pass(settings, monkeypatch):
    make_run(settings, monkeypatch)
    service = Service(settings)
    original = service._execute

    def inputs_timeout(operation, *args, **kwargs):
        if operation == "inputs":
            return {"outcome": "timed_out"}
        return original(operation, *args, **kwargs)

    monkeypatch.setattr(service, "_execute", inputs_timeout)
    response = call(service, "cq_gate", run_id="sample")
    assert response["ok"] and response["data"]["verdict"] == "cannot_judge", response
    assert response["data"]["run_header"]["verification_status"] == "timed_out"


def test_legacy_baseline_cannot_prove_comparability(settings, monkeypatch):
    make_run(settings, monkeypatch)
    base = settings.project / "audits/old"
    base.mkdir()
    (base / "summary.json").write_text('{"run_id":"old","tools":[]}', encoding="utf-8")
    (base / "findings.json").write_text('{"findings":[]}', encoding="utf-8")
    result = call(Service(settings), "cq_diff", run_id="sample", base_run_id="old")
    assert result["ok"] and result["data"]["comparability"]["comparable"] is False, result


def test_configuration_change_blocks_execution(settings, monkeypatch):
    make_run(settings, monkeypatch)
    (settings.project / "cq.toml").write_text("coverage_threshold=50\n", encoding="utf-8")
    result = call(Service(settings), "cq_gate", run_id="sample", verify_current=False)
    assert result["error"]["code"] == "CONFIG_CHANGED"


def test_snapshot_digest_tampering_and_historical_freshness(settings):
    service = Service(settings)
    artifact = service.store.artifact(
        "gate_result", {"passed": True}, {"freshness": "current", "verified_now": True}
    )
    response = call(service, "cq_artifact_get", artifact_id=artifact["artifact_id"])
    assert response["data"]["run_header"]["freshness"] == "unknown"
    assert response["data"]["run_header"]["historical"] is True
    with service.store.transaction() as db:
        db.execute("UPDATE artifacts SET text='changed' WHERE id=?", (artifact["artifact_id"],))
    damaged = call(service, "cq_artifact_get", artifact_id=artifact["artifact_id"])
    assert damaged["error"]["code"] == "INVALID_ARTIFACT"


def test_unknown_versions_do_not_make_two_runs_comparable(settings, monkeypatch):
    for identity in ("base", "target"):
        output = make_run(settings, monkeypatch, identity)
        path = output.run_dir / "summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["tools"][0].pop("version")
        atomic_json(path, summary)
        publish_run(output.run_dir, identity, "0.5.2")
    result = call(Service(settings), "cq_diff", run_id="target", base_run_id="base")
    assert result["ok"], result
    assert result["data"]["comparability"]["comparable"] is False
    assert "TOOL_VERSIONS_UNKNOWN" in {
        item["code"] for item in result["data"]["comparability"]["reasons"]
    }


def test_gate_snapshot_retains_final_skipped_checks(settings, monkeypatch):
    make_run(settings, monkeypatch)
    service = Service(settings)
    result = call(service, "cq_gate", run_id="sample", verify_current=False)
    assert result["ok"], result
    header = service.store.read_artifact(result["data"]["artifact"]["artifact_id"])[3]
    assert header["evidence"] == result["data"]["evidence"]
    assert "coverage" in header["evidence"]["core_skipped_checks"]


def test_error_response_and_failed_audit_stay_bounded(settings, monkeypatch):
    service = Service(settings)

    def huge_error(*args):
        raise ServiceError("INVALID_OUTPUT", "oversize 😀" * 50000)

    monkeypatch.setattr(service, "_dispatch", huge_error)
    # A directory at the log path simulates an IO failure without changing permissions.
    (settings.state / "calls.jsonl").mkdir()
    result = call(service, "cq_runs_list")
    assert result["error"]["code"] == "INVALID_OUTPUT"
    assert len(encode(wire(result)).encode()) <= 65536


def test_snapshot_reservation_cannot_be_spent_twice(tmp_path):
    store = Store(tmp_path / "state", "project")
    with store.transaction() as db:
        store.reserve(db, "operation", 70000)
    store.artifact("gate_result", {}, {}, reservation="operation")
    with pytest.raises(ServiceError) as exhausted:
        store.artifact("gate_result", {}, {}, reservation="operation")
    assert exhausted.value.code == "STATE_LIMIT"


def test_concurrent_service_audits_are_complete(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    stores = [Store(tmp_path / "state", "project") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda i: stores[i % 2].audit("cq_runs_list", True, None), range(40))
        )
    assert all(results)
    rows = (tmp_path / "state/calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 40 and all(json.loads(row)["ok"] for row in rows)


def test_failed_spawn_does_not_leave_a_false_dirty_process_domain(settings):
    lease = ProjectLock(settings.project_identity).acquire()
    try:
        with pytest.raises(ServiceError) as failed:
            execute(
                [str(settings.project / "missing-python.exe")],
                settings,
                lease,
                threading.Event(),
                2,
            )
        assert failed.value.code == "CLI_UNAVAILABLE"
        assert lease.safe
    finally:
        lease.release(clean=lease.safe)
    recovered = ProjectLock(settings.project_identity).acquire()
    recovered.release(clean=True)


def test_large_diff_has_complete_snapshot_instead_of_truncation(settings, monkeypatch):
    make_run(settings, monkeypatch, "base")
    output = make_run(settings, monkeypatch, "target")
    findings = [
        {
            "id": str(index),
            "severity": "low",
            "source": "ruff",
            "rule": "fixture",
            "file": "app.py",
            "line": index,
            "message": "detail " * 100,
        }
        for index in range(200)
    ]
    atomic_json(output.run_dir / "findings.json", {"run_id": "target", "findings": findings})
    publish_run(output.run_dir, "target", "0.5.2")
    service = Service(settings)
    result = call(service, "cq_diff", run_id="target", base_run_id="base")
    assert result["ok"] and result["data"]["core_inline"] is False, result
    assert len(encode(wire(result)).encode()) <= 65536
    _, text, _, _ = service.store.read_artifact(result["data"]["artifact"]["artifact_id"])
    assert json.loads(text)["new_details"] == findings


@pytest.mark.skipif(
    os.name != "nt", reason="Windows owner-death recovery uses Job Object semantics"
)
def test_real_windows_owner_death_recovers_only_after_job_is_empty(settings):
    import win32api
    import win32con
    import win32process

    marker = settings.state.parent / "owner-ready.json"
    script = settings.state.parent / "owner.py"
    script.write_text(
        "import asyncio, json, os, sys\nfrom pathlib import Path\n"
        "from ai_code_quality.mcp.settings import Settings\n"
        "from ai_code_quality.mcp.service import Service\n"
        "async def run():\n"
        " s=Settings(Path(sys.argv[1]),Path(sys.argv[2]),tool_python=sys.argv[4])\n"
        " s.command=lambda *args: [sys.executable,'-c','import time; time.sleep(40)']\n"
        " service=Service(s)\n"
        " response=await service.call('cq_doctor',{'request_key':'crash'})\n"
        " await asyncio.sleep(0.5)\n"
        " Path(sys.argv[3]).write_text(json.dumps({'pid':os.getpid(),'job':response['data']['job_id']}))\n"
        " await asyncio.sleep(40)\nasyncio.run(run())\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(settings.project),
            str(settings.state),
            str(marker),
            settings.tool_python,
        ],
        env=settings.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    handle = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        owner = json.loads(marker.read_text())
        handle = win32api.OpenProcess(
            win32con.PROCESS_TERMINATE | win32con.SYNCHRONIZE, False, owner["pid"]
        )
        win32process.TerminateProcess(handle, 137)
        process.communicate(timeout=10)
        recovered = call(Service(settings), "cq_job_get", job_id=owner["job"])
        assert recovered["ok"], recovered
        assert recovered["data"]["state"] == "interrupted"
        lease = ProjectLock(settings.project_identity).acquire()
        lease.release(clean=True)
    finally:
        if handle is not None:
            handle.Close()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
