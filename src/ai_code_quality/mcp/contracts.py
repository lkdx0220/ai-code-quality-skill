"""Wire contracts shared by the SDK boundary and the service."""

from __future__ import annotations

import json
from typing import Any

from ..evidence import validate_id
from ..redact import redact_obj
from ..schema import SEVERITIES

ERROR_CODES = frozenset(
    (
        "INVALID_ARGUMENT",
        "POLICY_DENIED",
        "REQUEST_CONFLICT",
        "PROJECT_BUSY",
        "STATE_BUSY",
        "STATE_PROJECT_MISMATCH",
        "JOB_NOT_FOUND",
        "RUN_NOT_FOUND",
        "RUN_NOT_READY",
        "RUN_COLLISION",
        "INVALID_ARTIFACT",
        "STALE_CURSOR",
        "OUTSIDE_PROJECT",
        "CONFIG_CHANGED",
        "AMBIGUOUS_BASE_RUN",
        "STATE_LIMIT",
        "INDEX_LIMIT",
        "CLEANUP_FAILED",
        "CLI_UNAVAILABLE",
        "CLI_ERROR",
        "INVALID_OUTPUT",
        "OUTPUT_TOO_LARGE",
        "IO_ERROR",
        "INPUTS_TIMEOUT",
        "INPUTS_UNAVAILABLE",
    )
)
DEFAULT_ADAPTERS = ("ruff-check", "ruff-format", "mypy", "radon", "vulture")
ADAPTERS = (*DEFAULT_ADAPTERS, "import-linter", "deepsec", "pytest")
TERMINAL = frozenset(
    ("completed", "failed", "cancelled", "timed_out", "interrupted", "cleanup_failed")
)
WIRE_LIMIT = 64 * 1024
CAPTURE_LIMIT = 8 * 1024 * 1024


class ServiceError(Exception):
    def __init__(self, code: str, message: str):
        if code not in ERROR_CODES:
            raise ValueError(f"Undeclared error code: {code}")
        self.code = code
        super().__init__(message)


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def envelope(operation: str, data=None, *, error=None, exit_code=None) -> dict:
    return redact_obj(
        {
            "schema_version": "1.2",
            "operation": operation,
            "ok": error is None,
            "cq_exit_code": exit_code,
            "data": data,
            "warnings": [],
            "error": error,
        }
    )


def wire(value: dict) -> dict:
    return {
        "content": [{"type": "text", "text": encode(value)}],
        "structuredContent": value,
        "isError": not value["ok"],
    }


def fits(value: dict) -> bool:
    return len(encode(wire(value)).encode("utf-8")) <= WIRE_LIMIT - 512


def identifier(value: str) -> str:
    try:
        return validate_id(value)
    except ValueError as exc:
        raise ServiceError("INVALID_ARGUMENT", str(exc)) from exc


ID = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[A-Za-z0-9_-]+$"}
BOOL = {"type": "boolean"}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


SCHEMAS = {
    "cq_doctor": schema({"request_key": ID}, ("request_key",)),
    "cq_scan_start": schema(
        {
            "request_key": ID,
            "adapters": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "enum": list(ADAPTERS)},
            },
            "timeout_seconds": integer(1, 86400),
        },
        ("request_key",),
    ),
    "cq_job_get": schema({"job_id": ID}, ("job_id",)),
    "cq_job_cancel": schema({"job_id": ID}, ("job_id",)),
    "cq_runs_list": schema({"cursor": ID, "limit": integer(1, 50), "include_legacy": BOOL}),
    "cq_findings_get": schema(
        {
            "run_id": ID,
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "status": {"type": "string", "enum": ["new", "suppressed"]},
            "cursor": ID,
            "limit": integer(1, 100),
            "verify_current": BOOL,
        },
        ("run_id",),
    ),
    "cq_diff": schema(
        {"run_id": ID, "base_run_id": ID, "verify_current": BOOL}, ("run_id", "base_run_id")
    ),
    "cq_gate": schema(
        {
            "run_id": ID,
            "target": {"type": "string", "enum": ["A", "B"]},
            "base_run_id": ID,
            "verify_current": BOOL,
        },
        ("run_id",),
    ),
    "cq_artifact_get": schema(
        {"artifact_id": ID, "offset": integer(0, 2**63 - 1), "length": integer(1, 8192)},
        ("artifact_id",),
    ),
}
DESCRIPTIONS = {
    "cq_doctor": "Submit an asynchronous environment check. Wait for completion before scanning; holds the project lock.",
    "cq_scan_start": "Submit a local scan of a trusted project. Default five analyzers exclude security/architecture/tests. Missing selected tools are runtime gaps. pytest requires startup permission and explicit selection.",
    "cq_job_get": "Read job state, cancellation, deadlines and results. state_persisted=false means owner-memory facts; polling retries pending terminal writes. Execution success is not quality acceptance.",
    "cq_job_cancel": "Request cancellation; owner-local signals survive state write failure. Check cancellation_persisted and poll cleanup/state_persisted; accepted cancellation is not confirmed cleanup.",
    "cq_runs_list": "Discover local jobs and published runs. marker_present does not mean integrity verified.",
    "cq_findings_get": "Read bounded pages of findings. Oversize items have artifact references. Current freshness is opt-in.",
    "cq_diff": "Compare verified historical runs with explicit comparability. Does not write original audit files.",
    "cq_gate": "Return core quality checks plus an evidence-aware verdict. Default successful scans give pass_with_gaps; missing selected tools give cannot_judge. Quality failure is a valid result, not a tool error.",
    "cq_artifact_get": "Read registered redacted snapshots by Unicode codepoint. Never reads arbitrary source or raw paths.",
}


def validate(operation: str, arguments: Any) -> dict:
    if operation not in SCHEMAS or not isinstance(arguments, dict):
        raise ServiceError("INVALID_ARGUMENT", "Unknown tool or non-object arguments")
    spec = SCHEMAS[operation]
    if set(arguments) - spec["properties"].keys() or not set(spec["required"]) <= arguments.keys():
        raise ServiceError("INVALID_ARGUMENT", "Unknown or missing argument")
    for name, value in arguments.items():
        _validate_value(value, spec["properties"][name])
    return arguments


def _validate_value(value, spec):
    types = {"string": str, "integer": int, "boolean": bool, "array": list}
    if type(value) is not types[spec["type"]]:
        raise ServiceError("INVALID_ARGUMENT", "Incorrect argument type")
    if "enum" in spec and value not in spec["enum"]:
        raise ServiceError("INVALID_ARGUMENT", "Value outside the supported enumeration")
    if "pattern" in spec:
        identifier(value)
    if spec["type"] == "integer" and not spec["minimum"] <= value <= spec["maximum"]:
        raise ServiceError("INVALID_ARGUMENT", "Integer outside allowed bounds")
    if spec["type"] == "array":
        if not value:
            raise ServiceError("INVALID_ARGUMENT", "Explicit adapter list cannot be empty")
        for item in value:
            _validate_value(item, spec["items"])
        if len(set(value)) != len(value):
            raise ServiceError("INVALID_ARGUMENT", "Duplicate adapters")
