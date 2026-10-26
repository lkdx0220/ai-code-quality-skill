"""Async protocol orchestration over execution and evidence operations."""

from __future__ import annotations

import asyncio
import threading

from ..evidence import EvidenceError
from ..runs import RunNotFoundError
from .contracts import ERROR_CODES, SCHEMAS, ServiceError, envelope, fits, validate
from .control import ControlPlane
from .jobs import JobOperations
from .queries import QueryOperations
from .settings import Settings
from .store import Store


class Service(JobOperations, QueryOperations):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.state, settings.project_identity)
        self.control = ControlPlane(self.store)
        self.tasks: set[asyncio.Task] = set()
        self.events: set[threading.Event] = set()
        self.closing = False

    async def call(self, operation, arguments):
        exit_code = None
        try:
            if self.closing:
                raise ServiceError("CLI_ERROR", "Server is shutting down")
            arguments = validate(operation, arguments)
            if operation in ("cq_doctor", "cq_scan_start"):
                data = await self._accept_and_start(operation, arguments)
            else:
                event = threading.Event()
                self.events.add(event)
                task = asyncio.create_task(
                    asyncio.to_thread(self._dispatch, operation, arguments, event)
                )
                self.tasks.add(task)
                task.add_done_callback(self._forget_task)
                try:
                    data, exit_code = await asyncio.shield(task)
                except asyncio.CancelledError:
                    event.set()
                    await asyncio.shield(task)
                    raise
                finally:
                    self.events.discard(event)
            response = envelope(operation, data, exit_code=exit_code)
            if data.get("persistence_error"):
                response["warnings"].append("Owner memory state only; state persistence failed")
            if not fits(response):
                raise ServiceError(
                    "OUTPUT_TOO_LARGE",
                    "Result exceeds the wire budget; use artifact pagination or the CLI",
                )
        except (ServiceError, EvidenceError, RunNotFoundError) as exc:
            code = exc.code if exc.code in ERROR_CODES else "INVALID_ARTIFACT"
            response = envelope(operation, error={"code": code, "message": str(exc)})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            response = envelope(
                operation,
                error={
                    "code": "INVALID_ARTIFACT",
                    "message": "Malformed evidence: " + type(exc).__name__,
                },
            )
        except OSError:
            response = envelope(
                operation, error={"code": "IO_ERROR", "message": "Local file operation failed"}
            )
        logged = await asyncio.to_thread(
            self.store.audit, operation, response["ok"], (response["error"] or {}).get("code")
        )
        if not logged:
            response["warnings"].append("Service call audit could not be persisted")
        if not fits(response):
            code = (response["error"] or {}).get("code", "OUTPUT_TOO_LARGE")
            response = envelope(
                operation if operation in SCHEMAS else "unknown",
                error={
                    "code": code,
                    "message": "Response exceeds the wire budget; use paginated results or the CLI",
                },
            )
            if not logged:
                response["warnings"].append("Service call audit could not be persisted")
        return response

    def _forget_task(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Failures are persisted or returned by the awaiting call.

    async def _accept_and_start(self, operation, arguments):
        submission = asyncio.create_task(asyncio.to_thread(self._submit, operation, arguments))
        self.tasks.add(submission)
        submission.add_done_callback(self._forget_task)
        interrupted = False
        try:
            data, worker = await asyncio.shield(submission)
        except asyncio.CancelledError:
            interrupted = True
            data, worker = await asyncio.shield(submission)
        if worker:
            job, lease = worker
            event = threading.Event()
            if interrupted or self.closing:
                event.set()
            self.control.track(job, event)
            self.events.add(event)
            task = asyncio.create_task(asyncio.to_thread(self._worker, job, lease, event))
            self.tasks.add(task)
            task.add_done_callback(self._forget_task)
            task.add_done_callback(lambda _: self.events.discard(event))
        if interrupted:
            raise asyncio.CancelledError
        return data

    async def close(self):
        self.closing = True
        for event in list(self.events):
            event.set()
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        try:
            await asyncio.to_thread(self.control.reconcile)
        except ServiceError:
            pass  # Pending facts cannot survive exit; restart uses conservative interrupted recovery.

    def _dispatch(self, operation, arguments, event):
        if operation == "cq_job_get":
            return self._job_get(arguments["job_id"]), None
        if operation == "cq_job_cancel":
            accepted, body = self.control.cancel(arguments["job_id"])
            return {
                "job_id": body["job_id"],
                "cancellation_requested": accepted,
                "state": body["state"],
                "cleanup": body["cleanup"],
                "state_persisted": body["state_persisted"],
                "cancellation_persisted": body.get("cancellation_persisted", False),
                **(
                    {"persistence_error": body["persistence_error"]}
                    if body.get("persistence_error")
                    else {}
                ),
            }, None
        if operation == "cq_artifact_get":
            return self._artifact_get(arguments), None
        if operation == "cq_runs_list":
            return self._runs_list(arguments), None
        if operation == "cq_findings_get":
            return self._findings(arguments, event), None
        return self._quality(operation, arguments, event)
