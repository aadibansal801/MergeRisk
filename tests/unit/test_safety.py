from pathlib import Path
import sys

import pytest

from mergerisk.git.plumbing import bounded_run, environment, validate_path
from mergerisk.verification import RuntimeConfig, verify_runtime


@pytest.mark.parametrize("path", ["../escape.py", "/etc/file", "C:/file", ".git/config", "a/../../x", "a\\b", "a//b"])
def test_unsafe_paths_refused(path):
    with pytest.raises(ValueError):
        validate_path(path)


def test_subprocess_limits_and_environment(monkeypatch):
    monkeypatch.setenv("GIT_DIR", "unrelated")
    assert "GIT_DIR" not in environment()
    with pytest.raises(RuntimeError, match="output exceeds"):
        bounded_run([sys.executable, "-c", "print('x'*100000)"], limit=1024)
    with pytest.raises(RuntimeError, match="timed out"):
        bounded_run([sys.executable, "-c", "import time;time.sleep(5)"], timeout=0.1)


def test_runtime_is_explicit_and_unavailable_without_sandbox(monkeypatch):
    monkeypatch.setattr("mergerisk.verification.shutil.which", lambda _: None)
    config = RuntimeConfig("sha256:" + "a" * 64, ("python", "-m", "pytest"))
    assert verify_runtime(None, None, config)["status"] == "validation_unavailable"
    for image in ["python:latest", "--privileged", "sha256:bad"]:
        with pytest.raises(ValueError):
            RuntimeConfig(image, ("python",))
    with pytest.raises(ValueError):
        RuntimeConfig("sha256:" + "a" * 64, ())
