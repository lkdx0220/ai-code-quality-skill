"""Real crash fixture: accept a job, optionally start an owned process tree."""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ai_code_quality.mcp.locking import process_identity
from ai_code_quality.mcp.service import Service
from ai_code_quality.mcp.settings import Settings


async def owner(project, state, marker, phase, interpreter):
    settings = Settings(Path(project), Path(state), tool_python=interpreter)
    settings.command = lambda *args: [sys.executable, __file__, "tree", marker + ".tree"]
    service = Service(settings)
    if phase == "accepted":
        data, _worker = service._submit("cq_doctor", {"request_key": "crash"})
    else:
        response = await service.call("cq_doctor", {"request_key": "crash"})
        assert response["ok"], response
        data = response["data"]
    Path(marker).write_text(json.dumps({"owner_pid": os.getpid(), **data}), encoding="utf-8")
    await asyncio.sleep(120)


def tree(marker):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    Path(marker).write_text(
        json.dumps(
            {
                "group": os.getpgrp(),
                "pid": os.getpid(),
                "birth": process_identity(os.getpid()),
                "child": child.pid,
                "child_birth": process_identity(child.pid),
            }
        ),
        encoding="utf-8",
    )
    time.sleep(120)


if __name__ == "__main__":
    if sys.argv[1] == "tree":
        tree(sys.argv[2])
    else:
        asyncio.run(owner(*sys.argv[1:]))
