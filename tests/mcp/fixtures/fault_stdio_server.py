"""Test-only barriers around the real stdio entry point; never installed as a tool."""

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from ai_code_quality.mcp.locking import process_identity


def announce(path, **value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")


def pause(path, **value):
    announce(path, **value)
    time.sleep(90)
    raise RuntimeError("Crash controller did not terminate the fixture")


def quiet_scan(arguments):
    from ai_code_quality import cli, scan
    from ai_code_quality.adapters.base import Adapter
    from ai_code_quality.schema import AdapterResult

    class Quiet(Adapter):
        name = "ruff-check"

        def run(self, ctx):
            return AdapterResult(name=self.name, tool="ruff", status="ok", version="fixture")

    scan.get_adapters = lambda _: [Quiet()]
    raise SystemExit(cli.main(arguments))


def tree(marker):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
    announce(
        marker,
        pid=os.getpid(),
        birth=process_identity(os.getpid()),
        child=child.pid,
        child_birth=process_identity(child.pid),
        group=os.getpgrp() if os.name != "nt" else None,
    )
    time.sleep(90)


def gated_scan(marker, arguments):
    announce(marker, pid=os.getpid(), birth=process_identity(os.getpid()))
    deadline = time.monotonic() + 45
    while not Path(marker + ".go").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("Disk fixture was not released")
        time.sleep(0.02)
    quiet_scan(arguments)


def server(phase, marker, project, state):
    from ai_code_quality.mcp.jobs import JobOperations
    from ai_code_quality.mcp.server import main
    from ai_code_quality.mcp.settings import Settings
    from ai_code_quality.mcp.store import Store

    def command(self, operation, *arguments):
        if phase == "active":
            return [sys.executable, __file__, "tree", marker]
        if phase == "disk-project":
            return [
                sys.executable,
                __file__,
                "gated-scan",
                marker,
                operation,
                *arguments,
                "--format",
                "json",
            ]
        return [sys.executable, __file__, "scan", operation, *arguments, "--format", "json"]

    Settings.command = command
    if phase == "precommit":
        original = Store.transaction

        @contextmanager
        def transaction(self, **kwargs):
            with original(self, **kwargs) as db:
                yield db
                row = db.execute("SELECT body FROM jobs WHERE request_key='crash'").fetchone()
                if row:
                    pause(marker, phase=phase, job=json.loads(row[0]))

        # Schema creation runs before the jobs table contains a matching row.
        Store.transaction = transaction
    elif phase == "accepted":

        def worker(self, job, lease, event):
            pause(marker, phase=phase, job=job)

        JobOperations._worker = worker
    elif phase == "published":
        original_result = JobOperations._job_result

        def result(self, job, captured):
            value = original_result(self, job, captured)
            pause(marker, phase=phase, job=job, result=value)

        JobOperations._job_result = result
    elif phase == "pending":
        from ai_code_quality.mcp.contracts import ServiceError

        def failed_finish(self, identity, **changes):
            announce(marker, phase=phase, job_id=identity)
            raise ServiceError("IO_ERROR", "Injected terminal persistence failure")

        Store.finish = failed_finish
    raise SystemExit(
        main(["--project", project, "--state-dir", state, "--tool-python", sys.executable])
    )


if __name__ == "__main__":
    if sys.argv[1] == "server":
        server(*sys.argv[2:])
    elif sys.argv[1] == "tree":
        tree(sys.argv[2])
    elif sys.argv[1] == "scan":
        quiet_scan(sys.argv[2:])
    elif sys.argv[1] == "gated-scan":
        gated_scan(sys.argv[2], sys.argv[3:])
