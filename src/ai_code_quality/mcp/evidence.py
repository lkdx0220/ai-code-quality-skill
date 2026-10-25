"""Project-bound historical evidence and independent MCP verdicts."""

from __future__ import annotations

import json
import time

from ..evidence import file_digest, inside, object_digest
from ..redact import redact_obj
from ..runs import baseline_path, load_run
from .contracts import ADAPTERS, ServiceError, identifier


def reason(code, detail, source="mcp"):
    return {"code": code, "detail": detail, "source": source}


def unverified_header(identity, *, state="unverified", created_at=None):
    """Discovery and pending jobs never imply a verified publication."""
    return {
        "run_id": identity,
        "run_state": state,
        "created_at": created_at,
        "publication": "unknown" if state == "unverified" else "incomplete",
        "scan_consistency": "unknown",
        "freshness": "unknown",
        "checked_at": None,
        "verified_now": False,
        "verification_status": "not_requested",
        "rules_version": None,
        "monitor_scope": None,
        "declared_scope": {"scope": "unknown", "selected_adapters": [], "policy_out_of_scope": []},
        "evidence": {
            "selected_tools_complete": False,
            "publication": "unknown" if state == "unverified" else "incomplete",
            "runtime_gaps": [],
            "core_skipped_checks": [],
        },
        "reasons": [reason("UNVERIFIED_RUN", "Read the completed run to verify its evidence")],
    }


class RunView:
    def __init__(self, project, identity, *, baseline=False):
        identifier(identity)
        audits = inside(project / "audits", project)
        path = inside(audits / identity, audits)
        if not path.is_dir():
            raise ServiceError(
                "RUN_NOT_FOUND", "A full existing run ID is required; prefixes are not accepted"
            )
        if baseline and baseline_path(project, identity).exists():
            raise ServiceError("AMBIGUOUS_BASE_RUN", "A named baseline shadows this run ID")
        self.run = load_run(project, identity)
        self.path, self.summary = self.run.run_dir, self.run.summary
        self.binding = self.fingerprint()
        self.verified = "artifact_schema_version" in self.summary
        self.header = self._header()

    def fingerprint(self):
        return {
            name: file_digest(self.path / name) if (self.path / name).exists() else None
            for name in ("summary.json", "findings.json", ".complete.json")
        }

    def _header(self):
        summary = self.summary
        selected = summary.get("selected_adapters")
        tools = summary.get("tools")
        if not isinstance(tools, list) or any(not isinstance(item, dict) for item in tools):
            raise ServiceError("INVALID_ARTIFACT", "Invalid tool state records")
        gaps = []
        if not isinstance(selected, list) or not selected:
            selected = [str(item.get("name")) for item in tools]
            gaps.append(reason("UNKNOWN_SELECTION", "Run does not declare its selected adapters"))
        for name in selected:
            matches = [item for item in tools if item.get("name") == name]
            if len(matches) != 1 or matches[0].get("status") != "ok":
                gaps.append(reason("TOOL_INCOMPLETE", str(name), "core"))
        excluded = sorted(set(ADAPTERS) - set(selected))
        if "pytest" not in selected:
            excluded.append("coverage")
        after = summary.get("inputs", {}).get("after", {})
        header = {
            "run_id": self.run.run_id,
            "run_state": "published" if self.verified else "unknown",
            "created_at": summary.get("created_at"),
            "scope": summary.get("scope"),
            "publication": "verified" if self.verified else "unknown",
            "identity": "explicit" if summary.get("run_id") else "inferred",
            "scan_consistency": summary.get("scan_consistency", "unknown"),
            "freshness": "unknown",
            "checked_at": None,
            "verified_now": False,
            "verification_status": "not_requested",
            "rules_version": after.get("rules_version"),
            "monitor_scope": after.get("monitor_scope"),
            "config_digest": object_digest(summary.get("config")),
            "inputs_digest": after.get("monitor_digest"),
            "declared_scope": {
                "scope": summary.get("scope"),
                "selected_adapters": selected,
                "policy_out_of_scope": excluded,
            },
            "evidence": {
                "selected_tools_complete": not gaps,
                "publication": "verified" if self.verified else "unknown",
                "runtime_gaps": gaps,
                "core_skipped_checks": [],
            },
            "reasons": [reason("CURRENT_NOT_VERIFIED", "Current workspace was not checked")],
        }
        return redact_obj(header)

    def check_unchanged(self, project, *, baseline=False):
        current = RunView(project, self.run.run_id, baseline=baseline)
        if current.binding != self.binding:
            raise ServiceError("INVALID_ARTIFACT", "Run evidence changed during this operation")

    def freshness(self, result):
        header = self.header
        if result.get("outcome") == "timed_out":
            header.update(
                verification_status="timed_out",
                reasons=[reason("FRESHNESS_TIMEOUT", "Workspace verification timed out")],
            )
            return
        data = parse_output(
            result, {0}, required=("monitor_digest", "rules_version", "config_digests")
        )
        after = self.summary.get("inputs", {}).get("after", {})
        comparable_rules = all(
            data.get(key) == after.get(key) for key in ("rules_version", "redaction_rules_version")
        )
        header.update(
            checked_at=time.time(), verified_now=True, verification_status="verified", reasons=[]
        )
        if self.summary.get("scan_consistency") != "consistent":
            header["freshness"] = "unstable"
        elif not comparable_rules or not after.get("monitor_digest"):
            header.update(freshness="unknown", verified_now=False, verification_status="failed")
            header["reasons"] = [
                reason("RULES_CHANGED", "Input monitoring rules are not comparable")
            ]
        else:
            header["freshness"] = (
                "current" if data["monitor_digest"] == after["monitor_digest"] else "stale"
            )


def parse_output(result, exits, *, required=()):
    if result.get("outcome"):
        raise ServiceError("CLI_ERROR", "Core operation " + result["outcome"])
    try:
        data = json.loads(result["stdout"].decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ServiceError(
            "INVALID_OUTPUT", "Core did not return a complete UTF-8 JSON object"
        ) from exc
    if not isinstance(data, dict):
        raise ServiceError("INVALID_OUTPUT", "Core output must be an object")
    if isinstance(data.get("error"), dict):
        from .contracts import ERROR_CODES

        error = data["error"]
        code = error.get("code")
        raise ServiceError(
            code if code in ERROR_CODES else "CLI_ERROR", str(error.get("message", "Core failed"))
        )
    if result["exit_code"] not in exits:
        raise ServiceError("CLI_ERROR", "Unexpected core exit code")
    if any(key not in data for key in required):
        raise ServiceError("INVALID_OUTPUT", "Core result is missing required fields")
    return redact_obj(data)


def comparability(current, base):
    reasons = []
    for view in (current, base):
        if not view.verified or view.header["scan_consistency"] != "consistent":
            reasons.append(
                reason(
                    "UNVERIFIED_BASELINE", "Both historical runs must be verified and consistent"
                )
            )
    a, b = current.summary, base.summary
    for key in ("scope", "selected_adapters", "cq_version", "config"):
        if key not in a or key not in b or a[key] != b[key]:
            reasons.append(reason("CONFIG_DIFFERENT", key))
    for key in ("rules_version", "redaction_rules_version", "config_digests"):
        aa, bb = a.get("inputs", {}).get("after", {}), b.get("inputs", {}).get("after", {})
        if key not in aa or key not in bb or aa[key] != bb[key]:
            reasons.append(reason("INPUT_RULES_DIFFERENT", key))
    versions_a, versions_b = _versions(current), _versions(base)
    if versions_a is None or versions_b is None:
        reasons.append(reason("TOOL_VERSIONS_UNKNOWN", "Selected analyzer versions must be known"))
    elif versions_a != versions_b:
        reasons.append(reason("TOOL_VERSIONS_DIFFERENT", "Analyzer versions differ"))
    return {"comparable": not reasons, "reasons": reasons}


def _versions(view):
    versions = {}
    for item in view.summary.get("tools", []):
        name, version = item.get("name"), item.get("version")
        if not isinstance(version, str) or version.strip().lower() in ("", "unknown", "n/a"):
            return None
        if not isinstance(name, str) or name in versions:
            return None
        versions[name] = version
    if set(versions) != set(view.header["declared_scope"]["selected_adapters"]):
        return None
    return versions or None


def _gate_checks(core):
    checks = core.get("checks")
    if type(core.get("passed")) is not bool or not isinstance(checks, list):
        raise ServiceError("INVALID_OUTPUT", "Invalid gate report")
    if any(not isinstance(item, dict) or type(item.get("passed")) is not bool for item in checks):
        raise ServiceError("INVALID_OUTPUT", "Invalid gate checks")
    return checks


def _evidence_verdict(core, header, failed, incomparable):
    if header["publication"] != "verified":
        return "cannot_judge", [
            reason("UNVERIFIED_RUN", "Legacy evidence is historical and unverified")
        ]
    if failed:
        return "fail", [
            reason("QUALITY_CHECK_FAILED", str(item["name"]), "core") for item in failed
        ]
    evidence = header["evidence"]
    incomplete = (
        not core["passed"]
        or core.get("exit_code") == 2
        or evidence["runtime_gaps"]
        or header["scan_consistency"] != "consistent"
        or incomparable
    )
    if incomplete:
        return "cannot_judge", [
            *evidence["runtime_gaps"],
            reason("EVIDENCE_INCOMPLETE", "Selected scope or baseline evidence is incomplete"),
        ]
    return None, []


def _freshness_verdict(header, requested_current, gaps):
    if not requested_current:
        return "pass_historical"
    if header["freshness"] == "stale":
        return "pass_stale"
    if header["freshness"] != "current":
        return "cannot_judge"
    return "pass_with_gaps" if gaps else "pass"


def gate_verdict(core, header, *, requested_current, base=None, comparison=None):
    checks = _gate_checks(core)
    skipped = [str(item.get("name")) for item in checks if item.get("skipped")]
    header["evidence"]["core_skipped_checks"] = skipped
    scope = {
        **header["declared_scope"],
        "target": core.get("target"),
        "baseline_requested": base is not None,
    }
    if base is None:
        scope["policy_out_of_scope"] = [*scope["policy_out_of_scope"], "baseline_delta"]
    trusted = {"blockers", "highs", "complexity", "coverage"}
    if base and comparison["comparable"]:
        trusted.add("new_blocker_high")
    failed = [item for item in checks if not item["passed"] and item.get("name") in trusted]
    verdict, reasons = _evidence_verdict(
        core, header, failed, base and not comparison["comparable"]
    )
    if verdict is None:
        verdict = _freshness_verdict(
            header, requested_current, scope["policy_out_of_scope"] or skipped
        )
    return {
        "verdict": verdict,
        "declared_scope": scope,
        "evidence": header["evidence"],
        "scope_gaps": scope["policy_out_of_scope"],
        "reasons": [*header["reasons"], *reasons],
        "temporal_scope": "current_workspace"
        if header["freshness"] == "current"
        else "historical_run",
    }
