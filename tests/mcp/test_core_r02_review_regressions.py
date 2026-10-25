import json
import os
import subprocess
import sys

import pytest

from ai_code_quality import baseline, cli, evidence, scan
from ai_code_quality.adapters.base import Adapter
from ai_code_quality.adapters.pytest_cov import PytestCovAdapter
from ai_code_quality.config import Config
from ai_code_quality.gate import run_gate
from ai_code_quality.redact import REDACTED, redact_obj, redact_text
from ai_code_quality.runs import RunNotFoundError, load_run
from ai_code_quality.schema import AdapterResult


def legacy_run(project, name="legacy", findings=None, tools=None):
    path = project / "audits" / name
    path.mkdir(parents=True)
    (path / "summary.json").write_text(
        json.dumps({"run_id": name, "tools": tools or []}), encoding="utf-8"
    )
    (path / "findings.json").write_text(
        json.dumps({"run_id": name, "findings": findings or []}), encoding="utf-8"
    )
    return path


def named_baseline(project, data):
    path = project / "audits/baselines/base.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode("utf-8"))
    return path


def directory_link(link, target):
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("command", ["gate", "diff", "baseline"])
def test_baseline_junction_rejects_outside_reads_and_writes(tmp_path, capsys, command):
    project, outside = tmp_path / "project", tmp_path / "outside"
    legacy_run(project)
    outside.mkdir()
    path = outside / "base.json"
    original = b'{"findings":[],"source_run_id":""}'
    path.write_bytes(original)
    directory_link(project / "audits/baselines", outside)
    args = [command, "--project", str(project), "--run", "legacy"]
    args += (
        ["--name", "base"] if command == "baseline" else ["--baseline", "base", "--format", "json"]
    )
    assert cli.main(args) == 3
    output = capsys.readouterr()
    if command != "baseline":
        assert json.loads(output.out)["error"]["code"] == "OUTSIDE_PROJECT"
    assert "Traceback" not in output.out + output.err
    assert path.read_bytes() == original
    assert not (project / "audits/legacy/gate.json").exists()
    assert not (project / "audits/legacy/diff.json").exists()


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {},
        {"findings": [1, 2]},
        {"findings": {}},
        {"findings": [], "source_run_id": 3},
        b"\xff\xfe{}",
    ],
)
@pytest.mark.parametrize("command", ["gate", "diff"])
def test_corrupt_baselines_are_not_quality_failures(tmp_path, capsys, data, command):
    legacy_run(tmp_path)
    named_baseline(tmp_path, data)
    assert (
        cli.main(
            [
                command,
                "--project",
                str(tmp_path),
                "--run",
                "legacy",
                "--baseline",
                "base",
                "--format",
                "json",
            ]
        )
        == 3
    )
    output = capsys.readouterr()
    assert json.loads(output.out)["error"]["code"] == "INVALID_ARTIFACT"
    assert "Traceback" not in output.err


def test_valid_baseline_remains_self_contained_after_source_is_deleted(tmp_path):
    data = {"source_run_id": "deleted", "findings": [{"id": "historical"}]}
    named_baseline(tmp_path, data)
    _, result = baseline.load_baseline(tmp_path, "base")
    assert result.findings == data["findings"]
    assert result.run_dir == tmp_path / "audits/baselines"


@pytest.mark.parametrize("name", ["CON", "nul", "LPT1", "a" * 300, "../bad"])
def test_baseline_names_fail_before_creating_files(tmp_path, capsys, name):
    legacy_run(tmp_path)
    assert (
        cli.main(["baseline", "--project", str(tmp_path), "--run", "legacy", "--name", name]) == 3
    )
    assert "Traceback" not in capsys.readouterr().err
    assert not (tmp_path / "audits/baselines").exists()


def test_atomic_baseline_failure_keeps_old_bytes(tmp_path, monkeypatch, capsys):
    legacy_run(tmp_path)
    path = named_baseline(tmp_path, {"findings": []})
    original = path.read_bytes()

    def refuse_replace(*args):
        raise PermissionError("injected atomic replace failure")

    monkeypatch.setattr(evidence.os, "replace", refuse_replace)
    assert (
        cli.main(["baseline", "--project", str(tmp_path), "--run", "legacy", "--name", "base"]) == 4
    )
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="Real unpaired-surrogate filenames require Windows")
def test_windows_surrogate_filename_is_inputs_unavailable(tmp_path, capsys):
    path = tmp_path / "bad\ud800name.py"
    path.write_bytes(b"value = 1\n")
    try:
        commands = [
            ["inputs", "--summary"],
            ["scan", "--run-id", "surrogate", "--adapters", "ruff-check"],
        ]
        for args in commands:
            assert cli.main([*args, "--project", str(tmp_path), "--format", "json"]) == 2
            output = capsys.readouterr()
            assert json.loads(output.out)["error"]["code"] == "INPUTS_UNAVAILABLE"
            assert "Traceback" not in output.err
        assert not (tmp_path / "audits/surrogate/.complete.json").exists()
    finally:
        path.unlink()


def test_real_pytest_usage_error_is_redacted_in_scan_console(tmp_path, capsys):
    secret = "sk-proj-" + "z" * 32
    (tmp_path / "test_ok.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = --bad-{secret}\n", encoding="utf-8")
    assert (
        cli.main(
            [
                "scan",
                "--project",
                str(tmp_path),
                "--run-id",
                "usage-error",
                "--adapters",
                "pytest",
                "--python",
                sys.executable,
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert REDACTED in output.out
    path = tmp_path / "audits/usage-error"
    data = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    assert data["tools"][0]["status"] == "error"
    assert "退出码 4" in data["tools"][0]["reason"]
    assert secret not in (path / "raw/pytest.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["gate", "diff"])
@pytest.mark.parametrize("fmt", ["json", "md"])
@pytest.mark.parametrize("no_save", [True, False])
def test_legacy_output_redacted_after_identity_matching(tmp_path, capsys, command, fmt, no_save):
    secret = "sk-proj-" + "w" * 32
    finding = {
        "id": "f1",
        "severity": "high",
        "source": "ruff",
        "rule": "F821",
        "category": "reliability",
        "file": secret + ".py",
        "line": 1,
        "message": "Authorization: Bearer short",
    }
    path = legacy_run(tmp_path, findings=[finding])
    named_baseline(tmp_path, {"findings": []})
    args = [
        command,
        "--project",
        str(tmp_path),
        "--run",
        "legacy",
        "--baseline",
        "base",
        "--format",
        fmt,
    ]
    if no_save:
        args += ["--no-save"]
    assert cli.main(args) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "Bearer short" not in output.out
    assert REDACTED in output.out
    saved = path / f"{command}.json"
    assert saved.exists() is not no_save
    if not no_save:
        text = saved.read_text(encoding="utf-8")
        assert secret not in text and "Bearer short" not in text
        if fmt == "json":
            assert json.loads(text) == json.loads(output.out)
    # Display filtering must not mutate the source or matching identity.
    assert load_run(tmp_path, "legacy").findings == [finding]


@pytest.mark.parametrize("statuses", [["skipped"], ["ok", "skipped"], ["ok"]])
def test_core_skipped_diagnostic_is_honest_without_changing_exit_policy(tmp_path, statuses):
    legacy_run(tmp_path, tools=[{"name": str(i), "status": s} for i, s in enumerate(statuses)])
    report = run_gate(tmp_path, "legacy")
    check = report.checks[0]
    assert check.passed and report.passed and report.exit_code == 0
    assert f"ok {statuses.count('ok')}，skipped {statuses.count('skipped')}" in check.detail
    assert "全部正常完成" not in check.detail


@pytest.mark.parametrize(
    "payload",
    [
        b'{\n"totals":{"percent_covered":100}\n}\n',
        b'{\r\n"totals":{"percent_covered":100}\r\n}\r\n',
        b'{"files":{"bad\xff.py":{}},"totals":{"percent_covered":100}}',
        b'{"files":{"sk-proj-' + b"x" * 32 + b'.py":{}},"totals":{"percent_covered":100}}',
    ],
)
def test_actual_coverage_producer_then_publication(tmp_path, monkeypatch, payload):
    final_bytes = []

    class Producer(PytestCovAdapter):
        def run(self, ctx):
            path = ctx.raw_dir / "coverage.json"
            path.write_bytes(payload)
            findings, files = [], []
            self._coverage_section(ctx, True, path, findings, files)
            final_bytes.append(path.read_bytes())
            return AdapterResult(
                name=self.name, tool=self.tool, status="ok", findings=findings, raw_files=files
            )

    monkeypatch.setattr(scan, "get_adapters", lambda _: [Producer()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    result = scan.run_scan(tmp_path, cfg=Config(), run_id="coverage-producer")
    path = result.run_dir / "raw/coverage.json"
    assert path.read_bytes() == final_bytes[0]
    assert b"sk-proj-" not in final_bytes[0] and b"\xff" not in final_bytes[0]
    assert json.loads(path.read_text(encoding="utf-8"))["totals"]["percent_covered"] == 100
    marker = evidence.verify_publication(result.run_dir, result.run_id)
    assert marker["files"]["raw/coverage.json"]["sha256"] == evidence.file_digest(path)
    assert load_run(tmp_path, result.run_id).summary["completed_adapters"] == ["pytest"]


@pytest.mark.parametrize(
    "text",
    [
        "Bearer authentication is required",
        "Bearer credentials are required",
        "the bearer of bad news",
        "Bearer documentation.",
    ],
)
def test_bearer_prose_is_preserved(text):
    assert redact_text(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Bearer abcdef123456",
        "Bearer abcdef_ghij",
        "Authorization: Bearer short",
        "Authorization: Basic abc",
    ],
)
def test_bearer_and_header_credential_contexts_are_redacted(text):
    assert redact_text(text) == text.rsplit(" ", 1)[0] + " " + REDACTED


@pytest.mark.parametrize("name", ["Authorization", "authorization", "Proxy-Authorization"])
@pytest.mark.parametrize("scheme", ["Bearer", "Basic"])
def test_structured_authorization_values_are_redacted(name, scheme):
    assert redact_obj({name: f"{scheme} abc"}) == {name: f"{scheme} {REDACTED}"}


def test_summary_directory_is_invalid_artifact(tmp_path):
    (tmp_path / "audits/run/summary.json").mkdir(parents=True)
    with pytest.raises(RunNotFoundError) as error:
        load_run(tmp_path, "run")
    assert error.value.code == "INVALID_ARTIFACT"


def test_coverage_directory_is_not_published_as_absent(tmp_path, monkeypatch):
    class BadCoverage(Adapter):
        name = "pytest"

        def run(self, ctx):
            (ctx.raw_dir / "coverage.json").mkdir()
            return AdapterResult(name=self.name, tool="pytest", status="ok")

    monkeypatch.setattr(scan, "get_adapters", lambda _: [BadCoverage()])
    monkeypatch.setattr("ai_code_quality.doctor.required_missing", lambda _: set())
    with pytest.raises(evidence.EvidenceError) as error:
        scan.run_scan(tmp_path, cfg=Config(), run_id="bad-coverage")
    assert error.value.code == "INVALID_ARTIFACT"
    assert not (tmp_path / "audits/bad-coverage/.complete.json").exists()
