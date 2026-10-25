"""Locked core comparisons, current-input verification and verdict projection."""

from __future__ import annotations

from .contracts import ServiceError, envelope, fits
from .evidence import RunView, comparability, gate_verdict, parse_output, reason
from .locking import ProjectLock
from .processes import execute
from .settings import Settings
from .store import Store, new_id


class QualityOperations:
    settings: Settings
    store: Store

    def _execute(self, operation, argv, lease, event, timeout=60):
        if event.is_set():
            raise ServiceError("CLI_ERROR", "Operation cancelled before execution")
        self.settings.check()
        result = execute(
            self.settings.command(operation, *argv), self.settings, lease, event, timeout
        )
        self.settings.check()
        return result

    def _verify_current(self, view, lease, event):
        result = self._execute(
            "inputs",
            [
                "--project",
                str(self.settings.project),
                "--summary",
                "--timeout-seconds",
                str(self.settings.inputs_timeout),
            ],
            lease,
            event,
            self.settings.inputs_timeout + 1,
        )
        try:
            view.freshness(result)
        except ServiceError as exc:
            if exc.code not in ("INPUTS_TIMEOUT", "INPUTS_UNAVAILABLE"):
                raise
            view.header.update(
                verification_status="timed_out" if exc.code == "INPUTS_TIMEOUT" else "failed",
                reasons=[
                    reason(
                        "FRESHNESS_TIMEOUT" if exc.code == "INPUTS_TIMEOUT" else exc.code, str(exc)
                    )
                ],
            )

    def _quality(self, operation, args, event):
        lease = ProjectLock(self.settings.project_identity).acquire()
        reservation = new_id("op")
        try:
            with self.store.transaction() as db:
                self.store.reserve(db, reservation)
            view = RunView(self.settings.project, args["run_id"])
            base = (
                RunView(self.settings.project, args["base_run_id"], baseline=True)
                if "base_run_id" in args
                else None
            )
            comparison = comparability(view, base) if base else None
            is_gate = operation == "cq_gate"
            core, exit_code = self._core_quality(args, view, base, lease, event, is_gate)
            verify = args.get("verify_current", is_gate)
            if verify:
                self._verify_current(view, lease, event)
            view.check_unchanged(self.settings.project)
            if base:
                base.check_unchanged(self.settings.project, baseline=True)
            data = {
                "run_header": view.header,
                "base_run_header": base.header if base else None,
                "comparability": comparison,
            }
            if is_gate:
                data.update(
                    gate_verdict(
                        core,
                        view.header,
                        requested_current=verify,
                        base=base,
                        comparison=comparison,
                    )
                )
            else:
                data.update(
                    temporal_scope="historical_runs",
                    current_target_verified=view.header["verified_now"],
                )
            data["artifact"] = self.store.artifact(
                "gate_result" if is_gate else "diff_result",
                core,
                view.header,
                reservation=reservation,
            )
            data["core_gate" if is_gate else "core_diff"] = core
            if not fits(envelope(operation, data, exit_code=exit_code)):
                data.pop("core_gate" if is_gate else "core_diff")
                data["core_inline"] = False
                data["core_summary"] = {
                    key: core[key]
                    for key in ("passed", "target", "new", "fixed", "existing", "suppressed")
                    if key in core
                }
            return data, exit_code
        finally:
            try:
                if lease.safe:
                    self.store.release(reservation)
            finally:
                lease.release(clean=lease.safe)

    def _core_quality(self, args, view, base, lease, event, is_gate):
        argv = ["--project", str(self.settings.project), "--run", view.run.run_id, "--no-save"]
        if base:
            argv += ["--baseline", base.run.run_id]
        if is_gate:
            argv += ["--target", args.get("target", "A")]
        captured = self._execute("gate" if is_gate else "diff", argv, lease, event)
        required = (
            ("passed", "checks", "exit_code")
            if is_gate
            else ("new", "fixed", "existing", "new_details", "fixed_details")
        )
        core = parse_output(captured, {0, 1, 2} if is_gate else {0, 1}, required=required)
        if is_gate and core["exit_code"] != captured["exit_code"]:
            raise ServiceError("INVALID_OUTPUT", "Gate exit code contradicts its JSON result")
        return core, captured["exit_code"]
