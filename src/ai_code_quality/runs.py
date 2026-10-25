"""run 目录的解析与加载：diff/gate/triage/baseline 共用。

run_ref 支持完整 run_id 或唯一前缀；找不到/歧义抛 RunNotFoundError（CLI 映射退出码 3）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from .evidence import (
    ARTIFACT_SCHEMA_VERSION,
    EvidenceError,
    inside,
    validate_id,
    verify_publication,
)

BASELINES_SUBDIR = "baselines"


class RunNotFoundError(LookupError):
    """run/baseline 引用无法解析（不存在、歧义或损坏）。"""

    def __init__(self, message: str, code: str = "RUN_NOT_FOUND"):
        super().__init__(message)
        self.code = code


@dataclass
class RunData:
    run_id: str
    run_dir: Path
    summary: dict[str, object]
    findings: list[dict[str, object]] = field(default_factory=list)

    @property
    def findings_active(self) -> list[dict[str, object]]:
        """未豁免的 findings（suppressed 的不参与 diff/gate 判定）。"""
        return [f for f in self.findings if f.get("status") != "suppressed"]

    @property
    def findings_suppressed(self) -> list[dict[str, object]]:
        return [f for f in self.findings if f.get("status") == "suppressed"]

    def has_tool_errors(self) -> bool:
        tools = cast("list[object]", self.summary.get("tools") or [])
        return any(t.get("status") in ("error", "timeout") for t in tools if isinstance(t, dict))


def audits_dir(project_root: Path) -> Path:
    return project_root / "audits"


def resolve_run_dir(project_root: Path, run_ref: str) -> Path:
    try:
        return _resolve_run_dir(project_root, run_ref)
    except EvidenceError as exc:
        raise RunNotFoundError(str(exc), exc.code) from exc


def _resolve_run_dir(project_root: Path, run_ref: str) -> Path:
    validate_id(run_ref)
    root = inside(audits_dir(project_root), project_root)
    if not root.is_dir():
        raise RunNotFoundError(f"项目没有 audits/ 目录: {project_root}")
    exact = inside(root / run_ref, root)
    if exact.is_dir():
        return exact
    matches = sorted(
        inside(d, root)
        for d in root.iterdir()
        if os.path.normcase(d.name).startswith(os.path.normcase(run_ref))
        and d.is_dir()
        and (d / "summary.json").is_file()
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = "、".join(m.name for m in matches[:5])
        raise RunNotFoundError(f"run 前缀 {run_ref!r} 命中多个 run，请用更长的前缀: {names}")
    raise RunNotFoundError(f"找不到 run: {run_ref}（audits/ 下没有匹配的 run 目录）")


def load_run(project_root: Path, run_ref: str) -> RunData:
    run_dir = resolve_run_dir(project_root, run_ref)
    try:
        summary_path = inside(run_dir / "summary.json", run_dir)
        if not summary_path.exists():
            raise RunNotFoundError("Run has not published its summary", "RUN_NOT_READY")
        if not summary_path.is_file():
            raise RunNotFoundError("Summary is not a regular file", "INVALID_ARTIFACT")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise RunNotFoundError("summary must be an object", "INVALID_ARTIFACT")
        published = _verify_if_published(run_dir, summary)
        fdata = json.loads(inside(run_dir / "findings.json", run_dir).read_text(encoding="utf-8"))
        findings = _validate_findings(run_dir, summary, fdata, published)
        # Catch changes between validation and reading, without claiming an atomic snapshot.
        _verify_if_published(run_dir, summary)
    except EvidenceError as exc:
        raise RunNotFoundError(f"{exc.code}: {exc}", exc.code) from exc
    except (OSError, ValueError) as e:
        code = (
            "IO_ERROR"
            if isinstance(e, OSError) and not isinstance(e, FileNotFoundError)
            else "INVALID_ARTIFACT"
        )
        raise RunNotFoundError(f"run {run_dir.name} 的产物读取失败: {e}", code) from e
    run_id = str(summary.get("run_id") or run_dir.name)
    return RunData(run_id=run_id, run_dir=run_dir, summary=summary, findings=findings)


def _verify_if_published(run_dir: Path, summary: dict) -> bool:
    marker = inside(run_dir / ".complete.json", run_dir)
    inputs = inside(run_dir / "inputs.json", run_dir)
    has_schema = "artifact_schema_version" in summary
    if not (has_schema or marker.exists() or inputs.exists()):
        return False
    version = summary.get("artifact_schema_version")
    if has_schema and (type(version) is not int or version != ARTIFACT_SCHEMA_VERSION):
        raise EvidenceError("INVALID_ARTIFACT", "Unsupported artifact schema version")
    verify_publication(run_dir, run_dir.name)
    if not has_schema:
        raise EvidenceError("INVALID_ARTIFACT", "Published run is missing its schema version")
    return True


def _validate_findings(run_dir: Path, summary: dict, fdata: object, published: bool) -> list[dict]:
    if not isinstance(fdata, dict):
        raise RunNotFoundError("findings document must be an object", "INVALID_ARTIFACT")
    findings = fdata.get("findings")
    if not isinstance(findings, list):
        raise RunNotFoundError("findings must be an array", "INVALID_ARTIFACT")
    if any(not isinstance(item, dict) for item in findings):
        raise RunNotFoundError("findings entries must be objects", "INVALID_ARTIFACT")
    for identity in (summary.get("run_id"), fdata.get("run_id")):
        if identity is not None and identity != run_dir.name:
            raise RunNotFoundError("Run identities do not match its directory", "INVALID_ARTIFACT")
    if published and (summary.get("run_id") != run_dir.name or fdata.get("run_id") != run_dir.name):
        raise RunNotFoundError("Published run is missing its identity", "INVALID_ARTIFACT")
    return findings


def validate_baseline_name(name: str) -> str:
    try:
        return validate_id(name)
    except EvidenceError as exc:
        raise RunNotFoundError(str(exc), exc.code) from exc


def baseline_path(project_root: Path, name: str) -> Path:
    validate_baseline_name(name)
    try:
        audit_root = inside(audits_dir(project_root), project_root)
        root = inside(audit_root / BASELINES_SUBDIR, audit_root)
        return inside(root / f"{name}.json", root)
    except EvidenceError as exc:
        raise RunNotFoundError(str(exc), exc.code) from exc
