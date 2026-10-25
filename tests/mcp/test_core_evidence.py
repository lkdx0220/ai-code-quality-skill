import json
import sys
from pathlib import Path

import pytest

from ai_code_quality import cli, evidence, scan
from ai_code_quality.adapters import get_adapters
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.config import Config
from ai_code_quality.evidence import EvidenceError, file_digest, publish_run, verify_publication
from ai_code_quality.redact import redact_text
from ai_code_quality.runs import RunNotFoundError, load_run
from ai_code_quality.schema import AdapterResult
from ai_code_quality.targets import inputs_summary, monitor_inputs


class QuietAdapter(Adapter):
    name = "ruff-check"

    def run(self, ctx):
        return AdapterResult(name=self.name, tool="ruff", status="ok", version="fixture")


@pytest.fixture
def scanned(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    monkeypatch.setattr(scan, "get_adapters", lambda _: [QuietAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    return scan.run_scan(tmp_path, cfg=Config(python_source="cli"), run_id="mcp-fixture")


def test_new_run_is_published_and_integrity_covers_coverage(scanned):
    marker = verify_publication(scanned.run_dir, scanned.run_id)
    assert marker["files"]["raw/coverage.json"] == {"absent": True}
    assert load_run(scanned.run_dir.parent.parent, scanned.run_id).findings == []
    (scanned.run_dir / "raw/coverage.json").write_text('{"totals":{"percent_covered":100}}')
    with pytest.raises(EvidenceError, match="Coverage appeared"):
        verify_publication(scanned.run_dir, scanned.run_id)


def test_collision_never_changes_existing_bytes(scanned):
    before = file_digest(scanned.run_dir / "summary.json")
    with pytest.raises(EvidenceError) as error:
        scan.run_scan(scanned.run_dir.parent.parent, cfg=Config(), run_id=scanned.run_id)
    assert error.value.code == "RUN_COLLISION"
    assert file_digest(scanned.run_dir / "summary.json") == before


def test_unpublished_new_run_is_not_legacy(scanned):
    (scanned.run_dir / ".complete.json").unlink()
    with pytest.raises(RunNotFoundError, match="RUN_NOT_READY"):
        load_run(scanned.run_dir.parent.parent, scanned.run_id)


def test_partial_publication_does_not_publish_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "get_adapters", lambda _: [QuietAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())

    def fail_after_summary(run_dir, run_id, summary, findings):
        (run_dir / "summary.json").write_text(json.dumps(summary))
        raise OSError("interrupted fixture")

    monkeypatch.setattr(scan, "_write_artifacts", fail_after_summary)
    with pytest.raises(OSError):
        scan.run_scan(tmp_path, cfg=Config(), run_id="partial")
    assert not (tmp_path / "audits/partial/.complete.json").exists()


def test_inputs_follow_exclusions_detect_add_delete_and_config(tmp_path):
    (tmp_path / "app.py").write_text("x=1")
    (tmp_path / ".gitignore").write_text("ignored/\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored/not_monitored.py").write_text("x=2")
    first = monitor_inputs(tmp_path)
    assert [entry["path"] for entry in first["files"]] == ["app.py"]
    assert first["config_digests"]["cq.toml"] == {"absent": True}
    assert "files" not in inputs_summary(first)
    (tmp_path / "new.py").write_text("x=3")
    second = monitor_inputs(tmp_path)
    assert second["monitor_digest"] != first["monitor_digest"]
    (tmp_path / "new.py").unlink()
    assert monitor_inputs(tmp_path)["monitor_digest"] == first["monitor_digest"]
    (tmp_path / "cq.toml").write_text("respect_gitignore=false")
    assert monitor_inputs(tmp_path)["monitor_digest"] != first["monitor_digest"]


def test_explicit_empty_adapters_never_fall_back(tmp_path, capsys):
    with pytest.raises(ValueError, match="不能为空"):
        get_adapters([])
    assert cli.main(["scan", "--project", str(tmp_path), "--adapters", "", "--format", "json"]) == 3
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_ARGUMENT"
    assert not (tmp_path / "audits").exists()


@pytest.mark.parametrize("value", ["../escape", "CON", "NUL", "has.dot", "a/b"])
def test_unsafe_run_id_rejected_before_creating_audits(tmp_path, value):
    with pytest.raises(EvidenceError):
        scan.run_scan(tmp_path, cfg=Config(), run_id=value, enabled_adapters=["ruff-check"])
    assert not (tmp_path / "audits").exists()


def test_explicit_default_python_keeps_source(tmp_path, monkeypatch):
    monkeypatch.delenv("CQ_PYTHON", raising=False)
    cfg = Config.load(tmp_path, cli_overrides={"python": sys.executable})
    assert cfg.python_source == "cli"
    assert {"enabled_adapters", "no_deepsec", "respect_gitignore"} <= cfg.snapshot().keys()


def test_bearer_rule_redacts_known_header():
    assert (
        redact_text("Authorization: Bearer opaque-token-value")
        == "Authorization: Bearer ***REDACTED***"
    )


def test_no_save_gate_diff_return_without_touching_run(scanned, capsys):
    root = scanned.run_dir.parent.parent
    marker = file_digest(scanned.run_dir / ".complete.json")
    common = ["--project", str(root), "--run", scanned.run_id, "--format", "json", "--no-save"]
    assert cli.main(["gate", *common]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == scanned.run_id
    assert cli.main(["diff", *common, "--baseline", scanned.run_id]) == 0
    assert json.loads(capsys.readouterr().out)["new"] == 0
    assert not (scanned.run_dir / "gate.json").exists()
    assert not (scanned.run_dir / "diff.json").exists()
    assert file_digest(scanned.run_dir / ".complete.json") == marker


@pytest.mark.parametrize(
    "bad_marker", [[], None, {}, {"schema_version": 2, "run_id": "mcp-fixture", "files": []}]
)
def test_malformed_marker_is_not_a_result(scanned, bad_marker, capsys):
    (scanned.run_dir / ".complete.json").write_text(json.dumps(bad_marker), encoding="utf-8")
    with pytest.raises(EvidenceError) as error:
        verify_publication(scanned.run_dir, scanned.run_id)
    assert error.value.code == "INVALID_ARTIFACT"
    assert (
        cli.main(
            [
                "gate",
                "--project",
                str(scanned.run_dir.parent.parent),
                "--run",
                scanned.run_id,
                "--format",
                "json",
                "--no-save",
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_ARTIFACT"


@pytest.mark.parametrize("mutation", ["missing_array", "bad_entry", "wrong_id"])
def test_valid_hash_cannot_hide_invalid_finding_schema(scanned, mutation):
    data = {"run_id": scanned.run_id, "findings": []}
    if mutation == "missing_array":
        data.pop("findings")
    elif mutation == "bad_entry":
        data["findings"] = [None]
    else:
        data["run_id"] = "another-run"
    (scanned.run_dir / "findings.json").write_text(json.dumps(data), encoding="utf-8")
    publish_run(scanned.run_dir, scanned.run_id, "fixture")
    with pytest.raises(RunNotFoundError) as error:
        load_run(scanned.run_dir.parent.parent, scanned.run_id)
    assert error.value.code == "INVALID_ARTIFACT"


@pytest.mark.parametrize(
    "failure_point",
    [
        "inputs.json",
        "coverage.json",
        "summary.json",
        "findings.json",
        "report.md",
        ".complete.json",
    ],
)
def test_each_publication_write_failure_is_unpublished(tmp_path, monkeypatch, failure_point):
    class CoverageAdapter(QuietAdapter):
        def run(self, ctx):
            (ctx.raw_dir / "coverage.json").write_text("{}", encoding="utf-8")
            return super().run(ctx)

    monkeypatch.setattr(scan, "get_adapters", lambda _: [CoverageAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    original = evidence.atomic_text

    def fail(path, chunks):
        if path.name == failure_point:
            raise OSError("injected write failure")
        return original(path, chunks)

    monkeypatch.setattr(evidence, "atomic_text", fail)
    monkeypatch.setattr(scan, "atomic_text", fail)
    original_sync = scan.sync_file

    def fail_sync(path):
        if path.name == failure_point:
            raise OSError("injected sync failure")
        return original_sync(path)

    monkeypatch.setattr(scan, "sync_file", fail_sync)
    with pytest.raises(OSError, match="injected"):
        scan.run_scan(tmp_path, cfg=Config(), run_id="interrupted")
    assert not (tmp_path / "audits/interrupted/.complete.json").exists()


def test_changed_during_scan_is_never_consistent(tmp_path, monkeypatch):
    source = tmp_path / "app.py"
    source.write_text("x=1", encoding="utf-8")

    class ChangingAdapter(QuietAdapter):
        def run(self, ctx):
            source.write_text("x=2", encoding="utf-8")
            return super().run(ctx)

    monkeypatch.setattr(scan, "get_adapters", lambda _: [ChangingAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    out = scan.run_scan(tmp_path, cfg=Config(), run_id="changed")
    assert out.summary["scan_consistency"] == "unstable"
    assert (
        out.summary["inputs"]["before"]["monitor_digest"]
        != out.summary["inputs"]["after"]["monitor_digest"]
    )


def test_inventory_failure_has_no_completed_scan(tmp_path, monkeypatch, capsys):
    def timeout(*args, **kwargs):
        raise EvidenceError("INPUTS_TIMEOUT", "fixture timeout")

    monkeypatch.setattr(scan, "monitor_inputs", timeout)
    assert (
        cli.main(
            [
                "scan",
                "--project",
                str(tmp_path),
                "--run-id",
                "timeout",
                "--adapters",
                "ruff-check",
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INPUTS_TIMEOUT"
    assert not (tmp_path / "audits/timeout/.complete.json").exists()


@pytest.mark.parametrize("command", ["gate", "diff"])
def test_save_io_failure_is_exit_four(scanned, monkeypatch, capsys, command):
    def cannot_write(*args, **kwargs):
        raise OSError("read-only fixture")

    monkeypatch.setattr(evidence, "atomic_json", cannot_write)
    args = [
        command,
        "--project",
        str(scanned.run_dir.parent.parent),
        "--run",
        scanned.run_id,
        "--format",
        "json",
    ]
    if command == "diff":
        args += ["--baseline", scanned.run_id]
    assert cli.main(args) == 4
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "IO_ERROR"


@pytest.mark.parametrize("command", ["gate", "diff"])
def test_read_io_failure_is_exit_four(scanned, monkeypatch, capsys, command):
    original = Path.read_text

    def cannot_read(path, *args, **kwargs):
        if path == scanned.run_dir / "summary.json":
            raise PermissionError("denied fixture")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", cannot_read)
    args = [
        command,
        "--project",
        str(scanned.run_dir.parent.parent),
        "--run",
        scanned.run_id,
        "--format",
        "json",
        "--no-save",
    ]
    if command == "diff":
        args += ["--baseline", scanned.run_id]
    assert cli.main(args) == 4
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "IO_ERROR"
