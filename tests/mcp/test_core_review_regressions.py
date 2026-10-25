import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from ai_code_quality import cli, evidence, runs, scan
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.config import Config
from ai_code_quality.evidence import EvidenceError, file_digest, object_digest
from ai_code_quality.redact import REDACTED, redact_text
from ai_code_quality.runs import RunNotFoundError, load_run
from ai_code_quality.schema import AdapterResult
from ai_code_quality.targets import monitor_inputs


class QuietAdapter(Adapter):
    name = "ruff-check"

    def run(self, ctx):
        return AdapterResult(name=self.name, tool="ruff", status="ok")


@pytest.fixture
def project_run(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_bytes(b"answer = 42\n")
    monkeypatch.setattr(scan, "get_adapters", lambda _: [QuietAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    return scan.run_scan(tmp_path, cfg=Config(python_source="cli"), run_id="review-run")


@pytest.mark.parametrize("version", [3, "2", None, 2.0, True])
def test_single_schema_mutation_cannot_disable_integrity(project_run, version):
    path = project_run.run_dir / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    if version is None:
        del summary["artifact_schema_version"]
    else:
        summary["artifact_schema_version"] = version
    path.write_text(json.dumps(summary), encoding="utf-8")
    (project_run.run_dir / "findings.json").write_text('{"findings":[]}', encoding="utf-8")
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, project_run.run_id)
    assert error.value.code == "INVALID_ARTIFACT"


def test_inputs_remains_a_new_format_indicator_without_schema_or_marker(project_run):
    path = project_run.run_dir / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    del summary["artifact_schema_version"]
    path.write_text(json.dumps(summary), encoding="utf-8")
    (project_run.run_dir / ".complete.json").unlink()
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, project_run.run_id)
    assert error.value.code == "RUN_NOT_READY"


@pytest.mark.parametrize("name", evidence.PUBLISHED_FILES)
def test_all_published_dependencies_reject_changes(project_run, name):
    (project_run.run_dir / name).write_bytes(b"{}\n")
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, project_run.run_id)
    assert error.value.code == "INVALID_ARTIFACT"


@pytest.mark.parametrize("name", [".complete.json", "summary.json", "findings.json"])
@pytest.mark.parametrize("command", ["gate", "diff", "triage", "fix", "suppress", "baseline"])
def test_binary_damage_is_an_artifact_error_for_all_consumers(project_run, capsys, name, command):
    (project_run.run_dir / name).write_bytes(b"\xff\xfe{}")
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, project_run.run_id)
    assert error.value.code == "INVALID_ARTIFACT"
    args = [
        command,
        "--project",
        str(project_run.run_dir.parent.parent),
        "--run",
        project_run.run_id,
    ]
    if command == "diff":
        args += ["--baseline", project_run.run_id]
    if command in ("gate", "diff", "triage", "fix"):
        args += ["--format", "json"]
    assert cli.main(args) == 3
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    if command in ("gate", "diff", "triage"):
        assert json.loads(captured.out)["error"]["code"] == "INVALID_ARTIFACT"


def test_second_verification_has_the_same_exception_type(project_run, monkeypatch):
    calls = 0
    original = runs.verify_publication

    def change_between_reads(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise EvidenceError("INVALID_ARTIFACT", "dependency changed after first validation")
        return original(*args)

    monkeypatch.setattr(runs, "verify_publication", change_between_reads)
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, project_run.run_id)
    assert calls == 2
    assert error.value.code == "INVALID_ARTIFACT"


@pytest.mark.parametrize("ref", ["../outside/evil", "a/b", "a\\b", "C:evil", "CON", "."])
def test_read_references_are_single_level_ids(project_run, ref):
    with pytest.raises(RunNotFoundError) as error:
        load_run(project_run.run_dir.parent.parent, ref)
    assert error.value.code == "INVALID_ARGUMENT"


def directory_link(link: Path, target: Path):
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("at_audits_root", [True, False])
def test_junction_or_symlink_cannot_escape_read_root(tmp_path, at_audits_root):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    evil = outside if not at_audits_root else outside / "evil"
    evil.mkdir(exist_ok=True)
    (evil / "summary.json").write_text("{}", encoding="utf-8")
    (evil / "findings.json").write_text('{"findings":[]}', encoding="utf-8")
    if at_audits_root:
        directory_link(project / "audits", outside)
    else:
        (project / "audits").mkdir()
        directory_link(project / "audits/evil", outside)
    with pytest.raises(RunNotFoundError) as error:
        load_run(project, "evil")
    assert error.value.code == "OUTSIDE_PROJECT"


def test_platform_case_alias_rules(project_run):
    root = project_run.run_dir.parent.parent
    for ref in ("REVIEW-RUN", "REVIEW-"):
        if os.name == "nt":
            run = load_run(root, ref)
            assert run.run_id == "review-run"
            assert run.run_dir.name == "review-run"
        else:
            with pytest.raises(RunNotFoundError):
                load_run(root, ref)


def test_legacy_and_incomplete_directories_remain_distinguishable(tmp_path):
    run = tmp_path / "audits/legacy"
    run.mkdir(parents=True)
    with pytest.raises(RunNotFoundError) as error:
        load_run(tmp_path, "legacy")
    assert error.value.code == "RUN_NOT_READY"
    (run / "summary.json").write_text("{}", encoding="utf-8")
    (run / "findings.json").write_text('{"findings":[]}', encoding="utf-8")
    assert load_run(tmp_path, "lega").run_id == "legacy"


def test_redacted_inventory_is_recomputable_and_preserves_path_identity(project_run, capsys):
    root = project_run.run_dir.parent.parent
    names = ["sk-proj-" + char * 32 + ".py" for char in ("a", "b")]
    for name in names:
        (root / name).write_bytes(b"value = 1\n")
    previous = monitor_inputs(root)
    entries = [entry for entry in previous["files"] if REDACTED in entry["path"]]
    assert len(entries) == 2
    assert len({entry["path"] for entry in entries}) == 1
    assert {entry["path_sha256"] for entry in entries} == {
        hashlib.sha256(name.encode("utf-8")).hexdigest() for name in names
    }
    canonical = {
        key: value
        for key, value in previous.items()
        if key not in ("monitor_digest", "files_count", "checked_at")
    }
    assert object_digest(canonical) == previous["monitor_digest"]
    assert cli.main(["inputs", "--project", str(root)]) == 0
    full_text = capsys.readouterr().out
    assert not any(name in full_text for name in names)
    assert json.loads(full_text)["monitor_digest"] == previous["monitor_digest"]
    assert cli.main(["inputs", "--project", str(root), "--summary"]) == 0
    assert json.loads(capsys.readouterr().out)["monitor_digest"] == previous["monitor_digest"]
    assert (
        cli.main(
            [
                "scan",
                "--project",
                str(root),
                "--adapters",
                "ruff-check",
                "--run-id",
                "redacted",
                "--format",
                "json",
            ]
        )
        == 0
    )
    scan_text = capsys.readouterr().out
    assert not any(name in scan_text for name in names)
    for artifact in ("inputs.json", "summary.json", "findings.json", "report.md"):
        assert not any(
            name in (root / "audits/redacted" / artifact).read_text(encoding="utf-8")
            for name in names
        )
    inventory = json.loads((root / "audits/redacted/inputs.json").read_text(encoding="utf-8"))
    assert inventory["before"]["monitor_digest"] == previous["monitor_digest"]
    (root / names[0]).unlink()
    renamed = "sk-proj-" + "c" * 32 + ".py"
    (root / renamed).write_bytes(b"value = 1\n")
    assert monitor_inputs(root)["monitor_digest"] != previous["monitor_digest"]


def test_selected_tools_are_not_confused_with_completed_tools(tmp_path, monkeypatch):
    class DisabledAdapter(QuietAdapter):
        name = "deepsec"

        def run(self, ctx):
            assert ctx.cfg.no_deepsec
            return AdapterResult(
                name=self.name, tool="deepsec", status="skipped", reason="disabled"
            )

    monkeypatch.setattr(scan, "get_adapters", lambda _: [DisabledAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    out = scan.run_scan(
        tmp_path, cfg=Config(no_deepsec=True), run_id="disabled", inputs_timeout_seconds=120
    )
    assert out.summary["selected_adapters"] == out.summary["effective_adapters"] == ["deepsec"]
    assert out.summary["attempted_adapters"] == out.summary["completed_adapters"] == []
    assert out.summary["skipped_adapters"] == ["deepsec"]
    assert out.summary["inputs_timeout_seconds"] == 120


def test_coverage_publication_preserves_final_adapter_bytes(tmp_path, monkeypatch):
    payload = b'{\r\n  "totals": {"percent_covered":100}\r\n}\r\n'

    class CoverageAdapter(QuietAdapter):
        def run(self, ctx):
            (ctx.raw_dir / "coverage.json").write_bytes(payload)
            return super().run(ctx)

    monkeypatch.setattr(scan, "get_adapters", lambda _: [CoverageAdapter()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    out = scan.run_scan(tmp_path, cfg=Config(), run_id="coverage")
    path = out.run_dir / "raw/coverage.json"
    assert path.read_bytes() == payload
    marker = evidence.verify_publication(out.run_dir, out.run_id)
    assert marker["files"]["raw/coverage.json"]["sha256"] == file_digest(path)
    assert load_run(tmp_path, out.run_id).summary["completed_adapters"] == ["ruff-check"]


@pytest.mark.parametrize(
    "header", ["Authorization: Basic dXNlcjpwYXNz", "Proxy-Authorization: Bearer short"]
)
def test_authorization_headers_redact_known_schemes(header):
    assert redact_text(header) == header.rsplit(" ", 1)[0] + " " + REDACTED


def test_bearer_prose_is_not_a_token():
    assert redact_text("the bearer of bad news") == "the bearer of bad news"
