"""Test-only barriers around committed reservations and real stdio quality calls."""

import os
import sys
from contextlib import contextmanager

from fault_stdio_server import pause, tree


def server(phase, marker, project, state):
    from ai_code_quality.mcp.server import main
    from ai_code_quality.mcp.settings import Settings
    from ai_code_quality.mcp.store import Store

    if phase == "reserved":
        original = Store.transaction

        @contextmanager
        def transaction(self, **kwargs):
            with original(self, **kwargs) as db:
                yield db
            with original(self, readonly=True) as db:
                rows = dict(db.execute("SELECT id,bytes FROM reservations WHERE id GLOB 'op-*'"))
            if rows:
                pause(marker, owner=os.getpid(), phase=phase, reservations=rows)

        Store.transaction = transaction
    elif phase == "snapshot":
        original_artifact = Store.artifact

        def artifact(self, kind, value, header, **kwargs):
            result = original_artifact(self, kind, value, header, **kwargs)
            if kind in ("gate_result", "diff_result"):
                pause(marker, owner=os.getpid(), phase=phase, artifact=result)
            return result

        Store.artifact = artifact
    elif phase == "active":
        original_command = Settings.command

        def command(self, operation, *arguments):
            if operation in ("gate", "diff"):
                return [sys.executable, __file__, "tree", marker]
            return original_command(self, operation, *arguments)

        Settings.command = command
    raise SystemExit(
        main(["--project", project, "--state-dir", state, "--tool-python", sys.executable])
    )


if __name__ == "__main__":
    if sys.argv[1] == "tree":
        tree(sys.argv[2])
    else:
        server(*sys.argv[1:])
