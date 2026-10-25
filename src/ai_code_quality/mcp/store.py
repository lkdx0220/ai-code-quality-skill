"""Transactional job, immutable snapshot and cursor registry."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..redact import REDACTION_RULES_VERSION, redact_obj
from .contracts import CAPTURE_LIMIT, ServiceError, encode

RESERVATION = 9 * 1024 * 1024
CONTROL_HEADROOM = 16 * 1024 * 1024
ARTIFACT_TYPES = frozenset(
    (
        "summary",
        "findings",
        "finding_overflow",
        "report",
        "inputs_summary",
        "publication_summary",
        "gate_result",
        "diff_result",
        "job_diagnostic",
    )
)


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex


class Store:
    def __init__(self, root: Path, project: str, *, capacity=256 * 1024 * 1024):
        root.mkdir(parents=True, exist_ok=True, mode=0o700 if os.name != "nt" else 0o777)
        self.root, self.path, self.capacity = root, root / "state.sqlite3", capacity
        if self.path.is_symlink() or self.path.resolve().parent != root.resolve():
            raise ServiceError("OUTSIDE_PROJECT", "State database escapes its directory")
        with self.transaction() as db:
            ddl = """
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    digest TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, bytes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, type TEXT NOT NULL,
                    text TEXT NOT NULL, digest TEXT NOT NULL, header TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cursors (id TEXT PRIMARY KEY, binding TEXT NOT NULL,
                    position INTEGER NOT NULL, expires REAL NOT NULL, UNIQUE(binding, position));
            """
            for statement in ddl.split(";"):
                if statement.strip():
                    db.execute(statement)
            previous = db.execute("SELECT value FROM meta WHERE key='project'").fetchone()
            if previous and previous[0] != project:
                raise ServiceError(
                    "STATE_PROJECT_MISMATCH", "State directory belongs to a different project"
                )
            db.execute("INSERT OR IGNORE INTO meta VALUES ('project', ?)", (project,))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            code = "STATE_BUSY" if "locked" in str(exc).lower() else "IO_ERROR"
            raise ServiceError(code, "State database operation failed") from exc
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def physical_bytes(self):
        return sum(path.stat().st_size for path in self.root.iterdir() if path.is_file())

    def reserve(self, db, identity, amount=RESERVATION, *, job=False):
        used = db.execute("SELECT COALESCE(SUM(bytes),0) FROM reservations").fetchone()[0]
        if self.physical_bytes() + used + amount > self.capacity - CONTROL_HEADROOM:
            raise ServiceError(
                "STATE_LIMIT", "State capacity exhausted; existing reads/cancel remain available"
            )
        if job and db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= 1000:
            raise ServiceError(
                "STATE_LIMIT", "Job limit reached; export and clean state after stopping the server"
            )
        db.execute("INSERT INTO reservations VALUES (?,?)", (identity, amount))

    def release(self, identity):
        with self.transaction() as db:
            db.execute("DELETE FROM reservations WHERE id=?", (identity,))

    def capacity_status(self):
        with self.transaction() as db:
            artifacts = db.execute(
                "SELECT COALESCE(SUM(LENGTH(CAST(text AS BLOB))+LENGTH(CAST(header AS BLOB))),0) FROM artifacts"
            ).fetchone()[0]
            cursors = db.execute("SELECT COUNT(*) FROM cursors").fetchone()[0]
            jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            reserved = db.execute("SELECT COALESCE(SUM(bytes),0) FROM reservations").fetchone()[0]
            index_bytes = db.execute(
                "SELECT COALESCE(SUM(LENGTH(CAST(binding AS BLOB))),0) FROM cursors"
            ).fetchone()[0]
            physical = self.physical_bytes()
            sqlite_bytes = self.path.stat().st_size
        return {
            "limit_bytes": self.capacity,
            "physical_bytes": physical,
            "sqlite_bytes": sqlite_bytes,
            "wal_bytes": 0,
            "artifact_payload_bytes": artifacts,
            "cursor_binding_bytes": index_bytes,
            "payloads_included_in_sqlite": True,
            "reserved_bytes": reserved,
            "control_headroom_bytes": CONTROL_HEADROOM,
            "jobs": jobs,
            "cursors": cursors,
            "note": "Physical bytes include logs and SQLite journal; payload counts are not additive",
        }

    def job(self, identity):
        with self.transaction() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (identity,)).fetchone()
        if not row:
            raise ServiceError("JOB_NOT_FOUND", "Unknown job ID")
        return json.loads(row[0])

    def update_job(self, identity, **changes):
        with self.transaction() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ServiceError("JOB_NOT_FOUND", "Unknown job ID")
            job = json.loads(row[0])
            job.update(changes)
            db.execute(
                "UPDATE jobs SET state=?,body=? WHERE id=?",
                (job["state"], encode(redact_obj(job)), identity),
            )
        return job

    def all_jobs(self):
        with self.transaction() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM jobs ORDER BY id")]

    def cancel(self, identity):
        from .contracts import TERMINAL

        with self.transaction() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ServiceError("JOB_NOT_FOUND", "Unknown job ID")
            body = json.loads(row[0])
            accepted = body["state"] not in TERMINAL
            if accepted:
                body["cancellation_requested"] = True
                db.execute("UPDATE jobs SET body=? WHERE id=?", (encode(body), identity))
        return accepted, body

    def finish(self, identity, **changes):
        with self.transaction() as db:
            body = json.loads(
                db.execute("SELECT body FROM jobs WHERE id=?", (identity,)).fetchone()[0]
            )
            if body["cancellation_requested"] and changes["state"] == "completed":
                changes.update(state="cancelled", result=None)
            body.update(redact_obj(changes))
            db.execute(
                "UPDATE jobs SET state=?,body=? WHERE id=?", (body["state"], encode(body), identity)
            )
            if changes.get("cleanup") == "confirmed":
                db.execute("DELETE FROM reservations WHERE id=?", (identity,))
        return body

    def artifact(self, kind, value, header, *, reservation=None):
        if kind not in ARTIFACT_TYPES:
            raise ServiceError("INVALID_ARTIFACT", "Unsupported artifact type")
        text = value if isinstance(value, str) else encode(redact_obj(value))
        from ..redact import redact_text

        text = redact_text(text)
        raw = text.encode("utf-8")
        if len(raw) > CAPTURE_LIMIT:
            raise ServiceError(
                "OUTPUT_TOO_LARGE", "Snapshot exceeds 8 MiB; use findings pagination or the CLI"
            )
        identity, digest = new_id("a"), hashlib.sha256(raw).hexdigest()
        metadata = redact_obj(
            {
                **header,
                "snapshot_at": time.time(),
                "historical": True,
                "source": header.get("run_id", header.get("job_id", header.get("kind", "service"))),
                "redaction_rules_version": REDACTION_RULES_VERSION,
                "freshness_at_snapshot": header.get("freshness"),
                "freshness": "unknown",
                "verified_now": False,
                "verification_status": "not_requested",
            }
        )
        with self.transaction() as db:
            temporary = reservation is None
            if temporary:
                self.reserve(db, identity, len(raw) + len(encode(metadata).encode()) + 65536)
            else:
                cost = len(raw) + len(encode(metadata).encode()) + 65536
                row = db.execute(
                    "SELECT bytes FROM reservations WHERE id=?", (reservation,)
                ).fetchone()
                if not row or row[0] < cost:
                    raise ServiceError("STATE_LIMIT", "Operation reservation exhausted")
                db.execute("UPDATE reservations SET bytes=bytes-? WHERE id=?", (cost, reservation))
            db.execute(
                "INSERT INTO artifacts VALUES (?,?,?,?,?)",
                (identity, kind, text, digest, encode(metadata)),
            )
            if temporary:
                db.execute("DELETE FROM reservations WHERE id=?", (identity,))
        return {"artifact_id": identity, "sha256": digest, "size_chars": len(text), "type": kind}

    def read_artifact(self, identity):
        with self.transaction() as db:
            row = db.execute(
                "SELECT type,text,digest,header FROM artifacts WHERE id=?", (identity,)
            ).fetchone()
        if not row:
            raise ServiceError("INVALID_ARTIFACT", "Unknown artifact ID")
        kind, text, digest, header = row
        if kind not in ARTIFACT_TYPES:
            raise ServiceError("INVALID_ARTIFACT", "Unknown registered artifact type")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise ServiceError("INVALID_ARTIFACT", "Artifact content changed")
        return kind, text, digest, json.loads(header)

    def cursor(self, binding, position):
        now = time.time()
        with self.transaction() as db:
            db.execute("DELETE FROM cursors WHERE expires<?", (now,))
            row = db.execute(
                "SELECT id FROM cursors WHERE binding=? AND position=?", (binding, position)
            ).fetchone()
            if row:
                return row[0]
            if db.execute("SELECT COUNT(*) FROM cursors").fetchone()[0] >= 10000:
                raise ServiceError("STATE_LIMIT", "Cursor limit reached")
            identity = new_id("c")
            self.reserve(db, identity, len(binding.encode()) + 65536)
            db.execute(
                "INSERT INTO cursors VALUES (?,?,?,?)", (identity, binding, position, now + 86400)
            )
            db.execute("DELETE FROM reservations WHERE id=?", (identity,))
            return identity

    def read_cursor(self, identity, binding=None):
        with self.transaction() as db:
            row = db.execute(
                "SELECT binding,position,expires FROM cursors WHERE id=?", (identity,)
            ).fetchone()
        if not row or row[2] < time.time() or (binding is not None and row[0] != binding):
            raise ServiceError(
                "STALE_CURSOR", "Cursor expired, arguments changed, or run evidence changed"
            )
        return row[0], row[1]

    def audit(self, operation, ok, code):
        """Bounded metadata only; no arguments, environment or raw diagnostics."""
        path = self.root / "calls.jsonl"
        try:
            # Same SQLite writer lock serializes rotation across instances as well as threads.
            with self.transaction():
                previous = self.root / "calls.previous.jsonl"
                for target in (path, previous):
                    if target.is_symlink() or target.resolve().parent != self.root.resolve():
                        return False
                if path.exists() and path.stat().st_size > 4 * 1024 * 1024:
                    os.replace(path, previous)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        encode(
                            {
                                "time": time.time(),
                                "operation": str(operation)[:64],
                                "ok": ok,
                                "code": code,
                            }
                        )
                        + "\n"
                    )
        except (OSError, ServiceError, sqlite3.Error):
            return False
        return True
