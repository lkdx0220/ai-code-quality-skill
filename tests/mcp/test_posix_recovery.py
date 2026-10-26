"""Linux product recovery must distinguish released locks from surviving tools."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ai_code_quality.mcp.locking import ProjectLock, group_members, process_identity
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc recovery semantics")


def wait_until(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for the crash fixture")


def load_marker(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


@pytest.mark.parametrize("phase", ["accepted", "active"])
@pytest.mark.parametrize("other_state", [False, True])
def test_sigkill_blocks_live_domain_and_never_replays_job(tmp_path, phase, other_state):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    settings = Settings(project, tmp_path / "state", tool_python=sys.executable)
    marker = tmp_path / "accepted.json"
    tree_marker = Path(str(marker) + ".tree")
    script = Path(__file__).parent / "fixtures/posix_owner.py"
    owner = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(project),
            str(settings.state),
            str(marker),
            phase,
            settings.tool_python,
        ],
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tree = None
    record = {"phase": phase, "other_state": other_state, "owner_pid": owner.pid}
    try:
        wait_until(lambda: load_marker(marker))
        accepted = load_marker(marker)
        if phase == "active":
            wait_until(lambda: load_marker(tree_marker))
            tree = load_marker(tree_marker)
            record["tree"] = tree
        owner.kill()
        stdout, stderr = owner.communicate(timeout=10)
        record.update(owner_exit=owner.returncode, stdout=stdout.decode(), stderr=stderr.decode())
        assert owner.returncode == -signal.SIGKILL, record

        async def recover():
            original = Service(settings)
            contender = (
                Service(Settings(project, tmp_path / "other-state", tool_python=sys.executable))
                if other_state
                else original
            )
            try:
                if tree:
                    assert process_identity(tree["pid"]) == tree["birth"]
                    assert process_identity(tree["child"]) == tree["child_birth"]
                    owner_path = ProjectLock(settings.project_identity).owner_path
                    intent = owner_path.read_bytes()
                    for operation, arguments in (
                        ("cq_doctor", {"request_key": "while-orphaned"}),
                        (
                            "cq_scan_start",
                            {"request_key": "scan-while-orphaned", "adapters": ["ruff-check"]},
                        ),
                    ):
                        blocked = await contender.call(operation, arguments)
                        assert not blocked["ok"], blocked
                        assert blocked["error"]["code"] == "CLEANUP_FAILED", blocked
                    unreadable = await original.call("cq_job_get", {"job_id": accepted["job_id"]})
                    assert unreadable["error"]["code"] == "CLEANUP_FAILED", unreadable
                    assert original.store.job(accepted["job_id"])["state"] == "running"
                    assert owner_path.read_bytes() == intent
                    assert (await contender.call("cq_runs_list", {}))["ok"]
                    record["orphan_blocked"] = True
                    # Only the fixture's positively identified group is terminated.
                    assert process_identity(tree["pid"]) == tree["birth"]
                    os.killpg(tree["group"], signal.SIGKILL)
                    wait_until(lambda: not group_members(tree["group"]))

                recovered = await original.call("cq_job_get", {"job_id": accepted["job_id"]})
                assert recovered["ok"], recovered
                job = recovered["data"]
                assert job["state"] == "interrupted" and job["cleanup"] == "confirmed", job
                assert job["result"] is None and job["cq_exit_code"] is None
                reused = await original.call("cq_doctor", {"request_key": "crash"})
                assert reused["ok"] and reused["data"]["reused"], reused
                assert reused["data"]["job_id"] == accepted["job_id"]
                assert reused["data"]["terminal_state"] == "interrupted"
                assert len(original.store.all_jobs()) == 1
                assert original.store.capacity_status()["reserved_bytes"] == 0
                lease = ProjectLock(settings.project_identity).acquire()
                lease.release(clean=True)
                new = await contender.call("cq_doctor", {"request_key": "after-cleanup"})
                assert new["ok"] and not new["data"]["reused"], new
                await contender.call("cq_job_cancel", {"job_id": new["data"]["job_id"]})
                record.update(
                    recovered_state=job["state"],
                    cleanup=job["cleanup"],
                    same_key_reused=True,
                    new_key_accepted=True,
                )
            finally:
                await contender.close()
                if contender is not original:
                    await original.close()

        asyncio.run(recover())
        assert not (project / "audits").exists()
        print(json.dumps(record, sort_keys=True))
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate(timeout=5)
        tree = tree or load_marker(tree_marker)
        if tree and process_identity(tree["pid"]) == tree["birth"]:
            os.killpg(tree["group"], signal.SIGKILL)
            wait_until(lambda: not group_members(tree["group"]))
