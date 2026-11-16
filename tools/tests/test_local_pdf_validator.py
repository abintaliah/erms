"""Availability reminders only: no services or database are started."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import check_local_pdf_validator as validator


@pytest.mark.parametrize("setting", ["/missing/verapdf", ""])
def test_missing_validator_warns_without_blocking(monkeypatch, capsys, setting):
    monkeypatch.setenv("MESSAGING_PDF_VALIDATOR", setting)
    validator.check()
    warning = capsys.readouterr().err
    assert "Message capture (Save record)" in warning
    assert "Other application features can still start" in warning
    assert "bash tools/install-local-tools.sh" in warning


@pytest.mark.parametrize("configured", [True, False])
def test_configured_and_path_executables_work(tmp_path, monkeypatch, capsys, configured):
    tool = tmp_path / "verapdf"
    tool.write_text('#!/bin/sh\n[ "$1" = "--version" ]\n')
    tool.chmod(0o700)
    if configured:
        monkeypatch.setenv("MESSAGING_PDF_VALIDATOR", str(tool))
    else:
        monkeypatch.delenv("MESSAGING_PDF_VALIDATOR", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
    validator.check()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "oserror"])
def test_runtime_failure_is_bounded_and_nonblocking(monkeypatch, capsys, failure):
    monkeypatch.setenv("MESSAGING_PDF_VALIDATOR", "verapdf")
    monkeypatch.setattr(validator.shutil, "which", lambda _: "/fake/verapdf")

    def run(command, **kwargs):
        assert command == ["/fake/verapdf", "--version"]
        assert kwargs["timeout"] == 10
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 10)
        if failure == "oserror":
            raise OSError("cannot execute")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(validator.subprocess, "run", run)
    validator.check()
    assert "Java runtime" in capsys.readouterr().err


def test_cli_returns_success_for_missing_dependency_from_another_directory(tmp_path):
    script = Path(validator.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path,
        env={**os.environ, "MESSAGING_PDF_VALIDATOR": "/missing/verapdf"},
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0
    assert "WARNING" in result.stderr
