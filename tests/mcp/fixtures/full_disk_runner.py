"""Linux-only real ENOSPC controller, executed inside a private mount namespace.

Only the bounded tmpfs is filled. Project/state placement varies by scenario;
logs, barriers and the final JSON report always live outside that filesystem.
"""

import asyncio
import errno
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

from ai_code_quality.evidence import verify_publication
from ai_code_quality.mcp.locking import group_members, process_identity
from ai_code_quality.mcp.settings import Settings
from ai_code_quality.mcp.store import Store


def hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def fill(volume):
    target = volume / "filler"
    written = 0
    with target.open("wb", buffering=0) as stream:
        for size in (65536, 4096):
            while True:
                try:
                    written += stream.write(b"x" * size)
                    assert written <= 33 * 1024 * 1024, "Mount size was not enforced"
                except OSError as error:
                    assert error.errno == errno.ENOSPC, error
                    break
    remaining = os.statvfs(volume).f_bavail * os.statvfs(volume).f_frsize
    assert remaining == 0, remaining
    return {"filler_bytes": written, "available_bytes": remaining, "errno": errno.ENOSPC}


async def until(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.02)
    raise AssertionError("Timed out waiting for real disk-full fixture")


def json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def result(response):
    data = json.loads(response.content[0].text)
    assert data == response.structured_content
    assert response.is_error == (not data["ok"])
    return data


async def exercise(mode, root, volume, record):
    project = (volume if mode == "project" else root) / "project"
    state = (volume if mode == "state" else root) / "state"
    project.mkdir()
    (project / "app.py").write_text("answer = 42\n", encoding="utf-8")
    fixture = Path(__file__).with_name("fault_stdio_server.py")
    seed = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            str(fixture),
            "scan",
            "scan",
            "--project",
            str(project),
            "--run-id",
            "previous",
            "--adapters",
            "ruff-check",
            "--format",
            "json",
        ],
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert seed.returncode == 0, seed.stderr.decode(errors="replace")
    (root / "seed.json").write_bytes(seed.stdout)
    old_run = project / "audits/previous"
    verify_publication(old_run, "previous")
    before = hashes(old_run)
    store = Store(state, Settings(project, state).project_identity)
    old_artifact = store.artifact("report", "previous immutable evidence", {})
    marker = root / "ready.json"
    phase = "disk-project" if mode == "project" else "active"
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(fixture), "server", phase, str(marker), str(project), str(state)],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    tree = None
    filler = volume / "filler"
    try:
        with (root / "server-stderr.log").open("w", encoding="utf-8") as stderr:
            async with (
                stdio_client(params, errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=30) as session,
            ):
                await session.initialize()
                accepted = result(
                    await session.call_tool(
                        "cq_scan_start", {"request_key": "disk-full", "adapters": ["ruff-check"]}
                    )
                )
                assert accepted["ok"], accepted
                job = accepted["data"]
                record["accepted"] = accepted
                tree = await until(lambda: json_file(marker))
                record["child"] = tree
                record["full"] = fill(volume)
                if mode == "state":
                    # Read-only SQLite transactions may succeed even when writes cannot.
                    for tool, arguments in (
                        ("cq_job_get", {"job_id": job["job_id"]}),
                        ("cq_artifact_get", {"artifact_id": old_artifact["artifact_id"]}),
                    ):
                        response = result(await session.call_tool(tool, arguments))
                        record[tool] = response
                        assert response["ok"], response
                    started = time.monotonic()
                    cancelled = result(
                        await session.call_tool("cq_job_cancel", {"job_id": job["job_id"]})
                    )
                    record["cancel_seconds"] = time.monotonic() - started
                    record["cancel_while_full"] = cancelled
                    assert record["cancel_seconds"] < 1
                    assert cancelled["ok"] and cancelled["data"]["cancellation_requested"], (
                        cancelled
                    )
                    assert cancelled["data"]["cancellation_persisted"] is False
                    assert cancelled["data"]["persistence_error"]["code"] == "IO_ERROR"
                    assert cancelled["warnings"]
                    with closing(sqlite3.connect(store.path)) as db:
                        persisted = json.loads(
                            db.execute(
                                "SELECT body FROM jobs WHERE id=?", (job["job_id"],)
                            ).fetchone()[0]
                        )
                        assert not persisted["cancellation_requested"]
                    deadline = time.monotonic() + 10
                    while True:
                        memory = result(
                            await session.call_tool("cq_job_get", {"job_id": job["job_id"]})
                        )
                        assert memory["ok"], memory
                        if memory["data"]["state"] == "cancelled":
                            break
                        assert time.monotonic() < deadline, memory
                        await asyncio.sleep(0.02)
                    record["terminal_while_full"] = memory
                    assert memory["data"]["cleanup"] == "confirmed"
                    assert memory["data"]["state_persisted"] is False
                    assert memory["data"]["state_source"] == "owner_memory"
                    assert process_identity(tree["pid"]) != tree["birth"]
                    assert process_identity(tree["child"]) != tree["child_birth"]
                    assert not group_members(tree["group"])
                    assert os.statvfs(volume).f_bavail == 0
                    late = result(
                        await session.call_tool("cq_job_cancel", {"job_id": job["job_id"]})
                    )
                    assert late["ok"] and late["data"]["cancellation_requested"] is False
                    filler.unlink()
                    retried = result(
                        await session.call_tool("cq_job_cancel", {"job_id": job["job_id"]})
                    )
                    assert retried["ok"] and not retried["data"]["cancellation_requested"], retried
                    record["cancel_after_freeing"] = retried
                else:
                    Path(str(marker) + ".go").touch()
                deadline = time.monotonic() + 20
                while True:
                    polled = result(
                        await session.call_tool("cq_job_get", {"job_id": job["job_id"]})
                    )
                    assert polled["ok"], polled
                    if polled["data"]["state"] in ("cancelled", "failed"):
                        break
                    assert time.monotonic() < deadline, polled
                    await asyncio.sleep(0.05)
                settled = polled["data"]
                record["terminal"] = polled
                assert settled["cleanup"] == "confirmed", settled
                assert settled["state_persisted"] is True, settled
                assert settled["state"] == ("failed" if mode == "project" else "cancelled")
                if mode == "project":
                    assert settled["cq_exit_code"] == 4, settled
                    assert settled["error"]["code"] == "IO_ERROR", settled
                    assert not (project / "audits" / job["run_id"] / ".complete.json").exists()
                    filler.unlink()
                await until(lambda: process_identity(tree["pid"]) != tree["birth"])
                if "child" in tree:
                    await until(lambda: process_identity(tree["child"]) != tree["child_birth"])
                    assert not group_members(tree["group"])
                assert store.capacity_status()["reserved_bytes"] == 0
                assert (
                    store.read_artifact(old_artifact["artifact_id"])[1]
                    == "previous immutable evidence"
                )
                verify_publication(old_run, "previous")
                assert hashes(old_run) == before
                old = result(await session.call_tool("cq_findings_get", {"run_id": "previous"}))
                assert old["ok"], old
                record.update(old_evidence_unchanged=True, reserved_bytes=0, cleanup="confirmed")
    finally:
        filler.unlink(missing_ok=True)
        if tree and process_identity(tree["pid"]) == tree["birth"]:
            os.killpg(tree.get("group", tree["pid"]), signal.SIGKILL)
            await until(lambda: not group_members(tree.get("group", tree["pid"])))


def main():
    mode, directory = sys.argv[1:]
    assert mode in ("state", "project") and os.geteuid() == 0
    root = Path(directory).resolve()
    assert root.is_relative_to(Path("/var/tmp")) and root.name.startswith("cq-disk-full-")
    root.mkdir(exist_ok=False)
    volume = root / "volume"
    volume.mkdir()
    record = {"scenario": mode, "filesystem": "tmpfs", "limit_bytes": 32 * 1024 * 1024}
    subprocess.run(
        ["mount", "-t", "tmpfs", "-o", "size=32m", "cq-fault-fixture", str(volume)], check=True
    )
    try:
        asyncio.run(exercise(mode, root, volume, record))
    finally:
        try:
            subprocess.run(["umount", str(volume)], check=True)
        finally:
            record["unmounted"] = not os.path.ismount(volume)
            (root / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    assert record["unmounted"]
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
