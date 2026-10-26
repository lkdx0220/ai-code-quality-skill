"""Owner-local cancellation and explicit, retryable terminal persistence."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field

from ..redact import redact_obj
from .contracts import TERMINAL, ServiceError
from .store import Store


@dataclass
class OwnedJob:
    body: dict
    event: threading.Event
    lock: threading.RLock = field(default_factory=threading.RLock)
    pending: dict | None = None
    cancellation_persisted: bool = False


class ControlPlane:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.lock = threading.Lock()
        self.jobs: dict[str, OwnedJob] = {}

    def track(self, body, event):
        with self.lock:
            self.jobs[body["job_id"]] = OwnedJob(copy.deepcopy(body), event)

    def _owned(self, identity):
        with self.lock:
            return self.jobs.get(identity)

    def _forget(self, identity, owned):
        with self.lock:
            if self.jobs.get(identity) is owned:
                del self.jobs[identity]

    def _flush(self, identity, owned):
        if owned.pending is not None:
            owned.body = self.store.finish(identity, **owned.pending)
            owned.cancellation_persisted = owned.body["cancellation_requested"]
            owned.pending = None
            self._forget(identity, owned)
            return True
        return False

    @staticmethod
    def _view(owned, error=None):
        body = copy.deepcopy(owned.body)
        body.update(
            state_source="owner_memory" if error else "state_store",
            state_persisted=error is None,
            cancellation_persisted=owned.cancellation_persisted,
        )
        body["cancellation_requested"] |= owned.event.is_set()
        if error:
            body["persistence_error"] = {"code": error.code, "message": str(error)}
        return body

    def get(self, identity):
        owned = self._owned(identity)
        if owned is None:
            body = self.store.job(identity)
            return {
                **body,
                "state_source": "state_store",
                "state_persisted": True,
                "cancellation_persisted": body["cancellation_requested"],
            }
        with owned.lock:
            try:
                if not self._flush(identity, owned):
                    owned.body = self.store.job(identity)
                    owned.cancellation_persisted = owned.body["cancellation_requested"]
                return self._view(owned)
            except ServiceError as error:
                if error.code not in ("STATE_BUSY", "IO_ERROR"):
                    raise
                return self._view(owned, error)

    def started(self, identity, **changes):
        owned = self._owned(identity)
        if owned:
            with owned.lock:
                owned.body.update(changes)

    def cancel(self, identity):
        owned = self._owned(identity)
        if owned is None:
            accepted, body = self.store.cancel(identity)
            return accepted, {
                **body,
                "state_persisted": True,
                "cancellation_persisted": body["cancellation_requested"],
            }
        with owned.lock:
            # Once terminal facts are selected, a later cancel cannot rewrite completion.
            if owned.pending is not None or owned.body["state"] in TERMINAL:
                return False, self.get(identity)
            owned.event.set()
            try:
                accepted, owned.body = self.store.cancel(identity)
                owned.cancellation_persisted = owned.body["cancellation_requested"]
                return accepted, self._view(owned)
            except ServiceError as error:
                if error.code not in ("STATE_BUSY", "IO_ERROR"):
                    raise
                return True, self._view(owned, error)

    def finish(self, identity, **changes):
        owned = self._owned(identity)
        if owned is None:
            return self.store.finish(identity, **changes)
        with owned.lock:
            if owned.event.is_set():
                changes["cancellation_requested"] = True
                if changes["state"] == "completed":
                    changes.update(state="cancelled", result=None)
            owned.pending = redact_obj(changes)
            owned.body.update(owned.pending)
            try:
                self._flush(identity, owned)
            except ServiceError as error:
                if error.code not in ("STATE_BUSY", "IO_ERROR"):
                    raise
                return self._view(owned, error)
            return self._view(owned)

    def reconcile(self):
        """Retry pending terminal writes before accepting more execution work."""
        with self.lock:
            entries = list(self.jobs.items())
        for identity, owned in entries:
            with owned.lock:
                self._flush(identity, owned)

    def cancelled(self, identity):
        # Cross-instance durable cancellation is polled without waiting behind a writer.
        try:
            return self.store.job(identity, timeout=0)["cancellation_requested"]
        except ServiceError as error:
            if error.code not in ("STATE_BUSY", "IO_ERROR"):
                raise
            return False
