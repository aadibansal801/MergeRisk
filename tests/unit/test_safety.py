from pathlib import Path
import sys

import pytest

from mergerisk.git.plumbing import bounded_run, environment, installed_tool, validate_path
from mergerisk.verification import RuntimeConfig, _validate_snapshot_paths, verify_runtime


@pytest.mark.parametrize("path", ["../escape.py", "/etc/file", "C:/file", ".git/config", "a/../../x", "a\\b", "a//b"])
def test_unsafe_paths_refused(path):
    with pytest.raises(ValueError):
        validate_path(path)


def test_subprocess_limits_and_environment(monkeypatch):
    monkeypatch.setenv("GIT_DIR", "unrelated")
    assert "GIT_DIR" not in environment()
    assert environment({"GIT_ALLOW_PROTOCOL": "https"})["GIT_ALLOW_PROTOCOL"] == ""
    assert environment()["GIT_NO_LAZY_FETCH"] == "1"
    with pytest.raises(RuntimeError, match="output exceeds"):
        bounded_run([sys.executable, "-c", "print('x'*100000)"], limit=1024)
    with pytest.raises(RuntimeError, match="timed out"):
        bounded_run([sys.executable, "-c", "import time;time.sleep(5)"], timeout=0.1)


def test_runtime_is_explicit_and_unavailable_without_sandbox(monkeypatch):
    monkeypatch.setattr("mergerisk.verification.installed_tool", lambda *args: None)
    config = RuntimeConfig("sha256:" + "a" * 64, ("python", "-m", "pytest"))
    assert verify_runtime(None, None, config)["status"] == "validation_unavailable"
    for image in ["python:latest", "--privileged", "sha256:bad"]:
        with pytest.raises(ValueError):
            RuntimeConfig(image, ("python",))


def test_installed_tool_uses_absolute_paths_outside_source(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    repo, cwd, tools_dir = (tmp_path / name for name in ("repo", "cwd", "installed"))
    for directory in (repo, cwd, tools_dir):
        directory.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", os.pathsep.join((".", str(repo), str(cwd), str(tools_dir))))

    def resolve(candidate):
        assert Path(candidate).is_absolute()
        return candidate

    monkeypatch.setattr("mergerisk.git.plumbing.shutil.which", resolve)
    assert Path(installed_tool("git", repo)).parent == tools_dir


@pytest.mark.skipif(sys.platform not in {"win32", "darwin"}, reason="Host uses case-sensitive Git path preflight")
def test_runtime_refuses_ambiguous_directory_spellings():
    with pytest.raises(ValueError, match="may alias"):
        _validate_snapshot_paths(["Docs/one.py", "docs/two.py"])


def test_terminal_summary_escapes_non_printing_source_text():
    from mergerisk.cli import _terminal

    assert _terminal("first\rline\nsecond\tline") == "first\\rline\nsecond\tline"
    with pytest.raises(ValueError):
        RuntimeConfig("sha256:" + "a" * 64, ())


def test_compiler_scope_syntax_is_detected_without_execution():
    from mergerisk.analysis.pipeline import AnalysisOrchestrator
    valid = {"app.py": "value = 1\n"}
    candidate = {"app.py": "return 1\n"}
    result = AnalysisOrchestrator().analyze_sources(valid, valid, valid, candidate)
    assert [f.rule_id for f in result.findings] == ["MR-PY-SYNTAX-001"]
