"""Resolving a venv's executable symlink discards its installed tool environment."""

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from ai_code_quality.mcp.settings import Settings


@pytest.mark.skipif(os.name != "posix", reason="POSIX venv Python is a symlink")
@pytest.mark.parametrize("source", ["cli", "env", "config", "default"])
def test_frozen_interpreter_preserves_real_venv_imports(tmp_path, source):
    tool_env = tmp_path / "tools venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(tool_env)
    python = tool_env / "bin" / "python"
    assert python.is_symlink()
    probe = subprocess.run(
        [str(python), "-c", "import json,sysconfig; print(json.dumps(sysconfig.get_paths()))"],
        capture_output=True,
        text=True,
        check=True,
    )
    site = Path(json.loads(probe.stdout)["purelib"])
    (site / "cq_venv_only_probe.py").write_text("VALUE = 'from venv'\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    if source == "config":
        (project / "cq.toml").write_text(f"python = {json.dumps(str(python))}\n", encoding="utf-8")
    env = dict(
        os.environ, PYTHONPATH=str(Path(sys.modules[Settings.__module__].__file__).parents[2])
    )
    env.pop("CQ_PYTHON", None)
    if source == "env":
        env["CQ_PYTHON"] = str(python)
    script = """
import json, subprocess, sys
from pathlib import Path
from ai_code_quality.mcp.settings import Settings
project, state, origin, python = sys.argv[1:]
settings = Settings(Path(project), Path(state), **({'tool_python': python} if origin == 'cli' else {}))
result = subprocess.run([settings.tool_python, '-c', 'import cq_venv_only_probe; print(cq_venv_only_probe.VALUE)'], capture_output=True, text=True)
print(json.dumps(dict(interpreter=settings.tool_python, source=settings.python_source, code=result.returncode, stdout=result.stdout, stderr=result.stderr)))
"""
    result = subprocess.run(
        [str(python), "-c", script, str(project), str(tmp_path / "state"), source, str(python)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["code"] == 0, data
    assert data["stdout"].strip() == "from venv"
    assert data["interpreter"] == str(python.absolute())
    assert data["source"] == source
