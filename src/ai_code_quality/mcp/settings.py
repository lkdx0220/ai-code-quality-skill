"""Lightweight frozen execution policy; startup never probes analyzers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..config import Config
from ..evidence import file_digest, inside, object_digest
from ..targets import MONITORED_CONFIGS
from .contracts import ServiceError


class Settings:
    def __init__(
        self,
        project: Path,
        state: Path,
        *,
        tool_python=None,
        allow_test_execution=False,
        max_scan_seconds=3600,
        inputs_timeout_seconds=60,
    ):
        self.project, self.state = project.resolve(), state.resolve()
        if not self.project.is_dir() or self.state.is_relative_to(self.project):
            raise ServiceError(
                "INVALID_ARGUMENT", "Project must exist; state must be outside the project"
            )
        if not 1 <= max_scan_seconds <= 86400 or not 1 <= inputs_timeout_seconds <= 600:
            raise ServiceError("INVALID_ARGUMENT", "Invalid startup deadline")
        self.allow_tests = allow_test_execution
        self.max_scan_seconds, self.inputs_timeout = max_scan_seconds, inputs_timeout_seconds
        self.env = dict(os.environ)
        self.config_hash = self.config_digest()
        config = Config.load(
            self.project, cli_overrides={"python": tool_python} if tool_python else {}
        )
        interpreter = Path(config.python)
        if not interpreter.is_absolute():
            interpreter = self.project / interpreter
        # A venv's symlink is part of its execution context; resolving it selects base Python.
        self.tool_python = os.path.abspath(interpreter)
        if not interpreter.is_file():
            raise ServiceError("CLI_UNAVAILABLE", "Configured tool interpreter does not exist")
        self.python_source = config.python_source
        self.env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        package_root = str(Path(__file__).resolve().parents[2])
        self.env["PYTHONPATH"] = os.pathsep.join(
            filter(None, (package_root, self.env.get("PYTHONPATH", "")))
        )
        self.fingerprint = object_digest(
            {
                "config": self.config_hash,
                "python": self.tool_python,
                "allow_tests": self.allow_tests,
                "max_scan_seconds": max_scan_seconds,
                "inputs_timeout": inputs_timeout_seconds,
                "environment": self.env,
            }
        )

    def config_digest(self):
        values = {}
        for name in MONITORED_CONFIGS:
            path = inside(self.project / name, self.project)
            if path.name == ".env" or path.name.startswith(".env."):
                raise ServiceError(
                    "OUTSIDE_PROJECT", "Execution config cannot alias an environment-secret file"
                )
            values[name] = file_digest(path) if path.exists() else None
        return object_digest(values)

    def check(self):
        if self.config_digest() != self.config_hash:
            raise ServiceError(
                "CONFIG_CHANGED", "Project execution configuration changed; restart this server"
            )

    def command(self, operation, *arguments):
        return [
            sys.executable,
            "-m",
            "ai_code_quality.cli",
            operation,
            *arguments,
            "--format",
            "json",
        ]

    @property
    def project_identity(self):
        return os.path.normcase(str(self.project))
