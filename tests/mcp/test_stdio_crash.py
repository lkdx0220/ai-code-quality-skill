"""Kill the actual stdio server, then recover through a new SDK session.

Five precise windows use an explicitly instrumented subprocess entry point;
the separate black-box case runs the unmodified -m entry point and real doctor.
"""

import asyncio
import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from ai_code_quality.evidence import verify_publication
from ai_code_quality.mcp.locking import group_members, process_identity


def read_json(path):
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
    raise AssertionError("Timed out waiting for stdio crash fixture")


def database_rows(state):
    try:
        with sqlite3.connect(state / "state.sqlite3", timeout=0.1) as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM jobs")]
    except sqlite3.OperationalError:
        return []


def payload(response):
    value = json.loads(response.content[0].text)
    assert value == response.structured_content
    assert response.is_error == (not value["ok"])
    return value


def kill_owner(pid):
    # Kill ONLY the server. Killing a whole tree would invalidate cleanup evidence.
    os.kill(pid, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)


@pytest.mark.parametrize(
    "phase", ["precommit", "accepted", "active", "published", "pending", "blackbox"]
)
def test_stdio_owner_crash_is_not_replayed(tmp_path, phase, record_property):
    pytest.importorskip(
        "mcp.client.session", reason="Optional MCP SDK required for actual stdio acceptance"
    )
    from mcp import ClientSession, StdioServerParameters, stdio_client
    from mcp.shared.exceptions import MCPError

    project, state = tmp_path / "project", tmp_path / "state"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    marker = tmp_path / "barrier.json"
    fixture = Path(__file__).parent / "fixtures/fault_stdio_server.py"
    runtime = os.environ.get("CQ_MCP_FAULT_SERVER_PYTHON", sys.executable)
    ordinary_args = [
        "-m",
        "ai_code_quality.mcp",
        "--project",
        str(project),
        "--state-dir",
        str(state),
        "--tool-python",
        runtime,
    ]
    arguments = (
        ordinary_args
        if phase == "blackbox"
        else [str(fixture), "server", phase, str(marker), str(project), str(state)]
    )
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    record = {"phase": phase, "instrumented": phase != "blackbox"}
    tree, owner = None, None

    async def run():
        nonlocal tree, owner
        params = StdioServerParameters(command=runtime, args=arguments, env=env)
        with (tmp_path / "first-stderr.log").open("w", encoding="utf-8") as stderr:
            async with (
                stdio_client(params, errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=20) as session,
            ):
                await session.initialize()
                assert len((await session.list_tools()).tools) == 9
                operation = "cq_doctor" if phase == "blackbox" else "cq_scan_start"
                args = {"request_key": "crash"}
                if operation == "cq_scan_start":
                    args["adapters"] = ["ruff-check"]
                pending = asyncio.create_task(session.call_tool(operation, args))
                if phase == "blackbox":
                    accepted = payload(await pending)
                    assert accepted["ok"], accepted
                    await until(lambda: database_rows(state))
                    row = database_rows(state)[0]
                    owner = row["owner_pid"]
                    from ai_code_quality.mcp.locking import ProjectLock
                    from ai_code_quality.mcp.settings import Settings

                    intent_path = ProjectLock(Settings(project, state).project_identity).owner_path
                    active = await until(
                        lambda: (
                            (value := read_json(intent_path))
                            and value.get("phase") == "active"
                            and value
                        )
                    )
                    record["active_child"] = active["child_pid"]
                    tree = {
                        "pid": active["child_pid"],
                        "birth": active["child_birth"],
                        "group": active["child_pid"] if os.name != "nt" else None,
                    }
                else:
                    boundary = await until(lambda: read_json(marker))
                    if phase == "active":
                        tree = boundary
                    row = boundary.get("job") or database_rows(state)[0]
                    owner = row["owner_pid"]
                    if phase == "precommit":
                        assert database_rows(state) == []
                    if phase in ("published", "pending"):
                        run_dir = project / "audits" / row["run_id"]
                        verify_publication(run_dir, row["run_id"])
                    if phase != "precommit":
                        accepted = payload(await pending)
                        assert accepted["ok"], accepted
                    if phase == "pending":
                        observed = payload(
                            await session.call_tool("cq_job_get", {"job_id": row["job_id"]})
                        )
                        assert observed["ok"] and observed["data"]["state"] == "completed"
                        assert observed["data"]["cleanup"] == "confirmed"
                        assert observed["data"]["state_persisted"] is False
                        assert observed["warnings"]
                        assert database_rows(state)[0]["state"] == "running"
                        record["memory_terminal_lost_on_crash"] = observed
                record.update(
                    job_id=row["job_id"], owner_pid=owner, owner_birth=process_identity(owner)
                )
                kill_owner(owner)
                if not pending.done():
                    try:
                        await pending
                    except MCPError as exc:
                        record["inflight_disconnect"] = type(exc).__name__
                await until(lambda: process_identity(owner) is None)
                try:
                    await session.list_tools()
                except MCPError as exc:
                    record["disconnected"] = type(exc).__name__
                else:
                    raise AssertionError("Killed stdio server still answered tools/list")

        params = StdioServerParameters(command=runtime, args=ordinary_args, env=env)
        with (tmp_path / "recovery-stderr.log").open("w", encoding="utf-8") as stderr:
            async with (
                stdio_client(params, errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=20) as session,
            ):
                await session.initialize()
                if phase == "precommit":
                    assert database_rows(state) == []
                    with sqlite3.connect(state / "state.sqlite3") as db:
                        assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0
                    record["rolled_back"] = True
                else:
                    if tree and os.name != "nt":
                        surviving = group_members(tree["group"])
                        # Real doctor may finish naturally between SIGKILL and recovery.
                        # The controlled active case guarantees a surviving process tree.
                        if phase == "active":
                            assert surviving
                        record["group_survived_until_recovery"] = bool(surviving)
                        if surviving:
                            assert process_identity(tree["pid"]) == tree["birth"]
                            if "child" in tree:
                                assert process_identity(tree["child"]) == tree["child_birth"]
                            blocked = payload(
                                await session.call_tool(
                                    "cq_doctor", {"request_key": "while-orphaned"}
                                )
                            )
                            assert blocked["error"]["code"] == "CLEANUP_FAILED", blocked
                            record["orphan_blocked"] = True
                            os.killpg(tree["group"], signal.SIGKILL)
                            await until(lambda: not group_members(tree["group"]))
                    elif tree:
                        await until(lambda: process_identity(tree["pid"]) != tree["birth"])
                        if "child" in tree:
                            await until(
                                lambda: process_identity(tree["child"]) != tree["child_birth"]
                            )
                        record["job_object_reaped_tree"] = True
                    recovered = payload(
                        await session.call_tool("cq_job_get", {"job_id": row["job_id"]})
                    )
                    assert recovered["ok"], recovered
                    assert recovered["data"]["state"] == "interrupted", recovered
                    assert recovered["data"]["cleanup"] == "confirmed", recovered
                    assert recovered["data"]["state_persisted"] is True, recovered
                    assert recovered["data"]["cq_exit_code"] is None
                    reused = payload(await session.call_tool(operation, args))
                    assert reused["ok"] and reused["data"]["reused"], reused
                    assert reused["data"]["job_id"] == row["job_id"]
                    assert reused["data"]["terminal_state"] == "interrupted"
                    with sqlite3.connect(state / "state.sqlite3") as db:
                        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
                        assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0
                    if phase in ("published", "pending"):
                        verify_publication(run_dir, row["run_id"])
                        findings = payload(
                            await session.call_tool("cq_findings_get", {"run_id": row["run_id"]})
                        )
                        assert findings["ok"], findings
                        record["published_evidence_preserved"] = True
                    record["recovered"] = "interrupted"
                # Uncommitted same key is new; committed same key never replays.
                fresh = payload(await session.call_tool("cq_doctor", {"request_key": "new"}))
                assert fresh["ok"] and not fresh["data"]["reused"], fresh
                cancelled = payload(
                    await session.call_tool("cq_job_cancel", {"job_id": fresh["data"]["job_id"]})
                )
                assert cancelled["ok"], cancelled
                record["new_key_accepted"] = True

    try:
        asyncio.run(run())
    finally:
        if owner and process_identity(owner) == record.get("owner_birth"):
            kill_owner(owner)
        if tree and os.name != "nt" and process_identity(tree["pid"]) == tree["birth"]:
            os.killpg(tree["group"], signal.SIGKILL)
    record_property("crash", json.dumps(record))
    print(json.dumps(record, sort_keys=True), flush=True)
