"""Opt-in Linux actual ENOSPC acceptance on an isolated, bounded tmpfs."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("CQ_MCP_REAL_DISK_FULL") != "1",
    reason="Requires explicit Linux private-mount acceptance: CQ_MCP_REAL_DISK_FULL=1",
)


@pytest.mark.parametrize("scenario", ["state", "project"])
def test_bounded_real_enospc(scenario, tmp_path, record_property):
    pytest.importorskip("mcp")
    assert os.geteuid() == 0, "Run only in the isolated root-capable Linux acceptance environment"
    root = Path("/var/tmp") / ("cq-disk-full-" + uuid.uuid4().hex)
    fixture = Path(__file__).parent / "fixtures/full_disk_runner.py"
    command = [
        "unshare",
        "--mount",
        "--propagation",
        "private",
        sys.executable,
        str(fixture),
        scenario,
        str(root),
    ]
    process = subprocess.run(command, capture_output=True, text=True, timeout=100, check=False)
    (tmp_path / "controller-stdout.log").write_text(process.stdout, encoding="utf-8")
    (tmp_path / "controller-stderr.log").write_text(process.stderr, encoding="utf-8")
    assert process.returncode == 0, process.stderr + process.stdout
    record = json.loads((root / "result.json").read_text(encoding="utf-8"))
    assert record["unmounted"] and record["old_evidence_unchanged"]
    assert record["full"]["available_bytes"] == 0
    record_property("disk_full", json.dumps({"evidence_directory": str(root), **record}))
    print(json.dumps({"evidence_directory": str(root), **record}), flush=True)
