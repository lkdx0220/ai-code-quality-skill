"""Bounded finding, artifact and run-index queries."""

from __future__ import annotations

import json

from ..evidence import inside, object_digest
from ..redact import redact_obj
from .contracts import ServiceError, encode, envelope, fits
from .evidence import RunView, unverified_header
from .locking import ProjectLock
from .quality import QualityOperations


class QueryOperations(QualityOperations):
    def _artifact_get(self, args):
        kind, text, digest, header = self.store.read_artifact(args["artifact_id"])
        offset = args.get("offset", 0)
        if offset > len(text):
            raise ServiceError("INVALID_ARGUMENT", "Artifact offset exceeds its length")
        count = min(args.get("length", 4096), len(text) - offset)
        while True:
            if count == 0 and offset < len(text):
                raise ServiceError(
                    "OUTPUT_TOO_LARGE", "Artifact metadata leaves no room for a codepoint"
                )
            data = {
                "artifact_id": args["artifact_id"],
                "type": kind,
                "run_header": header,
                "text": text[offset : offset + count],
                "offset": offset,
                "next_offset": offset + count if offset + count < len(text) else None,
                "size_chars": len(text),
                "sha256": digest,
                "media_type": "text/plain; charset=utf-8",
            }
            if fits(envelope("cq_artifact_get", data)):
                return data
            if count < 1:
                raise ServiceError(
                    "OUTPUT_TOO_LARGE", "Artifact metadata exceeds the response budget"
                )
            count //= 2

    def _findings(self, args, event):
        view = RunView(self.settings.project, args["run_id"])
        if args.get("verify_current", False):
            lease = ProjectLock(self.settings.project_identity).acquire()
            try:
                self._verify_current(view, lease, event)
            finally:
                lease.release(clean=lease.safe)
        selection = {
            "run_id": view.run.run_id,
            "severity": args.get("severity"),
            "status": args.get("status"),
            "limit": args.get("limit", 50),
            "verify_current": args.get("verify_current", False),
        }
        binding = object_digest(
            {"kind": "findings", "selection": selection, "digests": view.binding}
        )
        position = self.store.read_cursor(args["cursor"], binding)[1] if args.get("cursor") else 0
        findings = [
            item
            for item in view.run.findings
            if all(key not in args or item.get(key) == args[key] for key in ("severity", "status"))
        ]
        data = {
            "run_header": view.header,
            "items": [],
            "total": len(findings),
            "returned": 0,
            "next_cursor": None,
            "available_statuses": sorted({str(item.get("status")) for item in view.run.findings}),
        }
        for item in findings[position : position + args.get("limit", 50)]:
            tagged = {"inline": True, "finding": redact_obj(item)}
            if not fits(
                envelope(
                    "cq_findings_get", {**data, "items": [tagged], "next_cursor": "c-" + "0" * 32}
                )
            ):
                artifact = self.store.artifact("finding_overflow", item, view.header)
                tagged = {"inline": False, "id": item.get("id"), **artifact}
            candidate = {**data, "items": [*data["items"], tagged], "next_cursor": "c-" + "0" * 32}
            if not fits(envelope("cq_findings_get", candidate)):
                if not data["items"]:
                    raise ServiceError(
                        "OUTPUT_TOO_LARGE", "Finding placeholder cannot fit the page budget"
                    )
                break
            data["items"].append(tagged)
        data["returned"] = len(data["items"])
        after = position + data["returned"]
        if after < len(findings):
            data["next_cursor"] = self.store.cursor(binding, after)
        view.check_unchanged(self.settings.project)
        return data

    def _runs_list(self, args):
        include_legacy = args.get("include_legacy", False)
        limit = args.get("limit", 20)
        if args.get("cursor"):
            binding, offset = self.store.read_cursor(args["cursor"])
            selection = json.loads(binding)
            if (
                selection.get("kind") != "runs"
                or selection.get("include_legacy") != include_legacy
                or selection.get("limit") != limit
            ):
                raise ServiceError("STALE_CURSOR", "List cursor arguments changed")
            _, text, _, _ = self.store.read_artifact(selection["artifact_id"])
            items = json.loads(text)
        else:
            items = self._index(include_legacy)
            artifact = self.store.artifact("job_diagnostic", items, {"kind": "run_index"})
            binding = encode(
                {
                    "kind": "runs",
                    "artifact_id": artifact["artifact_id"],
                    "limit": limit,
                    "include_legacy": include_legacy,
                }
            )
            offset = 0
        data = {
            "items": [],
            "total": len(items),
            "returned": 0,
            "next_cursor": None,
            "capacity": self.store.capacity_status(),
        }
        for item in items[offset : offset + limit]:
            candidate = {**data, "items": [*data["items"], item], "next_cursor": "c-" + "0" * 32}
            if not fits(envelope("cq_runs_list", candidate)):
                if not data["items"]:
                    raise ServiceError("OUTPUT_TOO_LARGE", "Run index item exceeds budget")
                break
            data["items"].append(item)
        data["returned"] = len(data["items"])
        if offset + data["returned"] < len(items):
            data["next_cursor"] = self.store.cursor(binding, offset + data["returned"])
        return data

    def _index(self, include_legacy):
        items = [
            {
                "kind": "job",
                "id": job["job_id"],
                "state": job["state"],
                "run_id": job["run_id"],
                "run_header": unverified_header(job["run_id"]) if job["run_id"] else None,
            }
            for job in self.store.all_jobs()
        ]
        root = inside(self.settings.project / "audits", self.settings.project)
        if root.exists():
            for index, candidate in enumerate(root.iterdir()):
                if index >= 10000 or len(items) >= 10000:
                    raise ServiceError("INDEX_LIMIT", "Run directory index exceeds 10000 entries")
                path = inside(candidate, root)
                if path.name == "baselines" or not path.is_dir():
                    continue
                summary_path = inside(path / "summary.json", path)
                marker_path = inside(path / ".complete.json", path)
                if not summary_path.is_file() or (not include_legacy and not marker_path.is_file()):
                    continue
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if not isinstance(summary, dict) or summary.get("run_id", path.name) != path.name:
                    raise ServiceError("INVALID_ARTIFACT", "Invalid run index identity")
                present = marker_path.is_file()
                if present:
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    if (
                        not isinstance(marker, dict)
                        or marker.get("run_id") != path.name
                        or type(marker.get("schema_version")) is not int
                        or marker["schema_version"] != 2
                    ):
                        raise ServiceError(
                            "INVALID_ARTIFACT", "Invalid completion marker in run index"
                        )
                items.append(
                    {
                        "kind": "run",
                        "id": path.name,
                        "run_header": {
                            **unverified_header(path.name, created_at=summary.get("created_at")),
                            "marker_present": present,
                        },
                    }
                )
        return sorted(items, key=lambda item: (item["kind"], item["id"]))
