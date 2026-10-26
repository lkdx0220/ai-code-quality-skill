"""The process boundary rejects command strings and preserves literal arguments."""

import json
import os
import sys
import threading

import pytest

from ai_code_quality.mcp.contracts import ServiceError
from ai_code_quality.mcp.locking import ProjectLock, process_identity
from ai_code_quality.mcp.processes import execute
from ai_code_quality.mcp.settings import Settings


@pytest.mark.parametrize(
    "argv",
    [
        "python -c pass",
        b"python",
        None,
        {},
        [],
        (),
        [""],
        [sys.executable, 1],
        [sys.executable, True],
        [sys.executable, "invalid\0argument"],
    ],
)
def test_invalid_arguments_rejected_before_execution_intent(argv):
    # No settings/lease are available: touching execution state would also fail this test.
    with pytest.raises(ServiceError) as error:
        execute(argv, None, None, threading.Event(), 5)
    assert error.value.code == "INVALID_ARGUMENT"


@pytest.mark.parametrize("container", [list, tuple])
def test_real_process_receives_metacharacters_as_literal_arguments(tmp_path, container):
    if os.name == "nt":
        pytest.importorskip("win32api")
    project = tmp_path / "trusted project 中文"
    project.mkdir()
    settings = Settings(project, tmp_path / "state", tool_python=sys.executable)
    payloads = [
        "",
        "a b 中文😀",
        "quote\"and'apostrophe",
        "; echo injected > injected.txt",
        "$(echo injected) & | < > `echo injected`",
        "two\nlines",
    ]
    script = "import json,sys; print(json.dumps(sys.argv[1:],ensure_ascii=False))"
    argv = container([sys.executable, "-c", script, *payloads])
    lease = ProjectLock(settings.project_identity).acquire()
    try:
        result = execute(argv, settings, lease, threading.Event(), 10)
        assert result["exit_code"] == 0, result["stderr"]
        assert json.loads(result["stdout"].decode("utf-8")) == payloads
        assert not (project / "injected.txt").exists()
        assert process_identity(result["pid"]) is None
        assert lease.safe is True
    finally:
        lease.release(clean=lease.safe)
