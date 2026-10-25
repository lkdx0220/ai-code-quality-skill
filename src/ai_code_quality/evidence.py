"""Shared, standard-library-only publication and integrity primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

ARTIFACT_SCHEMA_VERSION = 2
PUBLISHED_FILES = ("summary.json", "findings.json", "report.md", "inputs.json", "raw/coverage.json")
_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value) or value.upper() in _DEVICES:
        raise EvidenceError(
            "INVALID_ARGUMENT",
            "ID must be 1..128 ASCII letters, digits, _ or -; device names are forbidden",
        )
    return value


def inside(path: Path, root: Path) -> Path:
    real = path.resolve()
    if not real.is_relative_to(root.resolve()):
        raise EvidenceError("OUTSIDE_PROJECT", f"Path escapes its permitted root: {path}")
    return real


def file_digest(path: Path, deadline: float | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            check_deadline(deadline)
            digest.update(block)
    check_deadline(deadline)
    return digest.hexdigest()


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise EvidenceError("INPUTS_TIMEOUT", "Input inventory exceeded its configured deadline")


def canonical_chunks(value: Any) -> Iterator[str]:
    return json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":")).iterencode(
        value
    )


def object_digest(value: Any) -> str:
    digest = hashlib.sha256()
    for chunk in canonical_chunks(value):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def atomic_text(path: Path, chunks: Iterable[str]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            for chunk in chunks:
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, canonical_chunks(payload))


def sync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def publish_run(run_dir: Path, run_id: str, cq_version: str) -> None:
    files: dict[str, object] = {}
    for name in PUBLISHED_FILES:
        path = inside(run_dir / name, run_dir)
        if not path.exists() and name == "raw/coverage.json":
            files[name] = {"absent": True}
        else:
            if not path.is_file():
                raise EvidenceError(
                    "INVALID_ARTIFACT", f"Published dependency is not a file: {name}"
                )
            files[name] = {"sha256": file_digest(path)}
    atomic_json(
        run_dir / ".complete.json",
        {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "run_id": run_id,
            "cq_version": cq_version,
            "files": files,
        },
    )


def verify_publication(run_dir: Path, run_id: str) -> dict[str, object]:
    marker = inside(run_dir / ".complete.json", run_dir)
    if not marker.is_file():
        raise EvidenceError("RUN_NOT_READY", "Run does not have a completion marker")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data.get("schema_version") != ARTIFACT_SCHEMA_VERSION
            or data.get("run_id") != run_id
        ):
            raise EvidenceError(
                "INVALID_ARTIFACT", "Completion marker identity/schema does not match"
            )
        files = data["files"]
        if not isinstance(files, dict) or set(files) != set(PUBLISHED_FILES):
            raise EvidenceError(
                "INVALID_ARTIFACT", "Completion marker has missing or unexpected dependencies"
            )
        for name in PUBLISHED_FILES:
            path = inside(run_dir / name, run_dir)
            entry = files[name]
            if entry == {"absent": True} and name == "raw/coverage.json":
                if path.exists():
                    raise EvidenceError("INVALID_ARTIFACT", "Coverage appeared after publication")
            elif not isinstance(entry, dict) or entry.get("sha256") != file_digest(path):
                raise EvidenceError("INVALID_ARTIFACT", f"Published artifact changed: {name}")
        return data
    except (
        FileNotFoundError,
        IsADirectoryError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        raise EvidenceError(
            "INVALID_ARTIFACT", "Completion marker or dependency is unreadable"
        ) from exc
    except OSError as exc:
        raise EvidenceError("IO_ERROR", "Cannot read a published artifact") from exc
