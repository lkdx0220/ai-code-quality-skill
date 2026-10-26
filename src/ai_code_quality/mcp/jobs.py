"""Transactional acceptance, job execution and conservative recovery."""

from __future__ import annotations

import json
import os
import time

from ..evidence import EvidenceError, inside, object_digest
from ..runs import RunNotFoundError
from .contracts import DEFAULT_ADAPTERS, TERMINAL, ServiceError, encode
from .control import ControlPlane
from .evidence import RunView, parse_output, unverified_header
from .locking import ProjectLock, process_identity
from .processes import execute
from .settings import Settings
from .store import Store, new_id

START_RETRY_SECONDS = 2


class JobOperations:
    settings: Settings
    store: Store
    control: ControlPlane

    def _submit(self, operation, arguments):
        self.control.reconcile()
        settings = self.settings
        adapters = sorted(arguments.get("adapters", DEFAULT_ADAPTERS))
        if "pytest" in adapters and not settings.allow_tests:
            raise ServiceError(
                "POLICY_DENIED", "pytest requires --allow-test-execution at server startup"
            )
        timeout = (
            600
            if operation == "cq_doctor"
            else arguments.get("timeout_seconds", settings.max_scan_seconds)
        )
        if operation == "cq_scan_start" and timeout > settings.max_scan_seconds:
            raise ServiceError("INVALID_ARGUMENT", "Scan deadline exceeds the startup maximum")
        settings.check()
        fingerprint = object_digest(
            {
                "operation": operation,
                "adapters": adapters,
                "timeout": timeout,
                "settings": settings.fingerprint,
            }
        )
        lease = None
        try:
            with self.store.transaction() as db:
                row = db.execute(
                    "SELECT digest,body FROM jobs WHERE request_key=?", (arguments["request_key"],)
                ).fetchone()
                if row:
                    if row[0] != fingerprint:
                        raise ServiceError(
                            "REQUEST_CONFLICT",
                            "request_key was used with different effective parameters",
                        )
                    original = json.loads(row[1])
                    return self._accepted(original, True), None
                identity = new_id("j")
                if db.execute("SELECT 1 FROM reservations WHERE id GLOB 'op-*' LIMIT 1").fetchone():
                    # Recover before quota admission, but never before domain validation.
                    lease = ProjectLock(settings.project_identity).acquire()
                    self.store.recover_operations(db, lease)
                self.store.reserve(db, identity, job=True)
                if lease is None:
                    lease = ProjectLock(settings.project_identity).acquire()
                body = {
                    "job_id": identity,
                    "request_key": arguments["request_key"],
                    "operation": operation,
                    "state": "queued",
                    "run_id": new_id("mcp") if operation == "cq_scan_start" else None,
                    "adapters": adapters,
                    "timeout_seconds": timeout,
                    "deadline_source": "call"
                    if "timeout_seconds" in arguments
                    else "startup_default",
                    "created_at": time.time(),
                    "cancellation_requested": False,
                    "cleanup": "not_started",
                    "owner_pid": os.getpid(),
                    "owner_birth": process_identity(os.getpid()),
                    "cq_exit_code": None,
                    "error": None,
                    "result": None,
                }
                db.execute(
                    "INSERT INTO jobs VALUES (?,?,?,?,?)",
                    (identity, arguments["request_key"], fingerprint, "queued", encode(body)),
                )
            return self._accepted(body, False), (body, lease)
        except BaseException:
            if lease:
                lease.release(clean=lease.safe)
            raise

    @staticmethod
    def _accepted(body, reused):
        return {
            "job_id": body["job_id"],
            "run_id": body["run_id"],
            "state": body["state"],
            "reused": reused,
            "terminal_state": body["state"] if body["state"] in TERMINAL else None,
            "rerun_hint": "Use a new request_key to execute again" if reused else None,
        }

    def _start_job(self, job, event, deadline):
        """Persist running before spawn; retry only transient writer contention."""
        identity = job["job_id"]
        retry_until = min(deadline, time.monotonic() + START_RETRY_SECONDS)
        last_error = None
        while True:
            if event.is_set() or self.control.cancelled(identity):
                return "cancelled"
            now = time.monotonic()
            if now >= deadline:
                return "timed_out"
            if last_error is not None and now >= retry_until:
                raise last_error
            try:
                started_at = time.time()
                self.store.update_job(identity, state="running", started_at=started_at)
                self.control.started(identity, state="running", started_at=started_at)
                return "running"
            except ServiceError as exc:
                if exc.code != "STATE_BUSY":
                    raise
                last_error = exc
            event.wait(max(0, min(0.03, retry_until - time.monotonic())))

    def _worker(self, job, lease, event):
        identity, settings = job["job_id"], self.settings
        deadline = time.monotonic() + job["timeout_seconds"]
        state, result, error, code = "failed", None, None, None
        try:
            if event.is_set() or self.control.cancelled(identity):
                state = "cancelled"
                return
            settings.check()
            startup = self._start_job(job, event, deadline)
            if startup != "running":
                state = startup
                return
            if event.is_set() or self.control.cancelled(identity):
                state = "cancelled"
                return
            argv = self._job_command(job)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                state = "timed_out"
                return
            captured = execute(
                argv,
                settings,
                lease,
                event,
                remaining,
                cancelled=lambda: self.control.cancelled(identity),
            )
            code = captured["exit_code"]
            if captured["outcome"]:
                state = captured["outcome"]
                return
            settings.check()
            result = self._job_result(job, captured)
            state = "completed"
        except (ServiceError, EvidenceError, RunNotFoundError) as exc:
            error = {"code": exc.code, "message": str(exc)}
        except Exception as exc:
            error = {"code": "IO_ERROR", "message": "Job processing failed: " + type(exc).__name__}
            raise ServiceError("IO_ERROR", error["message"]) from exc
        finally:
            clean = lease.safe
            if not clean:
                state, error = (
                    "cleanup_failed",
                    {"code": "CLEANUP_FAILED", "message": "Process cleanup was not confirmed"},
                )
            try:
                self.control.finish(
                    identity,
                    state=state,
                    result=result,
                    error=error,
                    cq_exit_code=code,
                    finished_at=time.time(),
                    cleanup="confirmed" if clean else "unconfirmed",
                )
            finally:
                lease.release(clean=clean)

    def _job_command(self, job):
        if job["operation"] == "cq_doctor":
            return self.settings.command("doctor", "--python", self.settings.tool_python)
        return self.settings.command(
            "scan",
            "--project",
            str(self.settings.project),
            "--run-id",
            job["run_id"],
            "--adapters",
            ",".join(job["adapters"]),
            "--python",
            self.settings.tool_python,
            "--inputs-timeout-seconds",
            str(self.settings.inputs_timeout),
        )

    def _job_result(self, job, captured):
        if job["operation"] == "cq_doctor":
            doctor = parse_output(captured, {0, 2}, required=("all_available", "tools"))
            artifact = self.store.artifact(
                "job_diagnostic", doctor, {"job_id": job["job_id"]}, reservation=job["job_id"]
            )
            return {
                "doctor": doctor
                if len(encode(doctor)) < 10000
                else {"all_available": doctor["all_available"]},
                "artifact": artifact,
            }
        summary = parse_output(
            captured, {0, 2}, required=("run_id", "tools", "artifact_schema_version")
        )
        if summary["run_id"] != job["run_id"]:
            raise ServiceError("INVALID_OUTPUT", "Core returned a different run identity")
        view = RunView(self.settings.project, job["run_id"])
        return {"run_header": view.header}

    def _job_get(self, identity):
        body = self.control.get(identity)
        if (
            body["state"] not in TERMINAL
            and process_identity(body["owner_pid"]) != body["owner_birth"]
        ):
            lease = ProjectLock(self.settings.project_identity).acquire()
            try:
                body = self.store.finish(
                    identity,
                    state="interrupted",
                    cleanup="confirmed",
                    result=None,
                    error={
                        "code": "CLI_ERROR",
                        "message": "Previous server exited; this job is not restarted",
                    },
                )
                body.update(
                    state_source="state_store",
                    state_persisted=True,
                    cancellation_persisted=body["cancellation_requested"],
                )
            finally:
                lease.release(clean=lease.safe)
        if body["run_id"]:
            path = inside(self.settings.project / "audits" / body["run_id"], self.settings.project)
            if body["state"] == "completed":
                body["result"] = {
                    "run_header": RunView(self.settings.project, body["run_id"]).header
                }
            elif not body.get("result"):
                body["result"] = {
                    "run_header": unverified_header(
                        body["run_id"], state="writing" if path.exists() else "pending"
                    )
                }
        return {
            key: value for key, value in body.items() if key not in ("owner_pid", "owner_birth")
        }
