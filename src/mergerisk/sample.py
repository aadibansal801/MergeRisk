"""Known-safe sample repositories, used by the repeatable product demonstration."""
from pathlib import Path
from mergerisk.git.plumbing import run_git

BASE = b"import json\n\ndef a():\n    return 1\n\n# additional functions\n"
RIGHT = BASE + b"\ndef b(x):\n    return json.dumps(x)\n"
FIXED = RIGHT


def create_sample(path: Path, *, unsafe: bool = False) -> dict[str, str]:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError("Sample repository directory must be empty")

    def git(*args):
        return run_git(path, list(args)).stdout.decode().strip()

    git("init", "-b", "target")
    git("config", "user.name", "MergeRisk Demo")
    git("config", "user.email", "demo@example.invalid")
    git("config", "core.autocrlf", "false")

    def commit(data, message):
        (path / "app.py").write_bytes(data)
        git("add", "app.py")
        git("-c", "core.hooksPath=", "commit", "-m", message)
        return git("rev-parse", "HEAD")

    base_data = b"def fetch():\n    return 1\n\n# additional functions\n" if unsafe else BASE
    base = commit(base_data, "base")
    left_data = base_data.replace(b"fetch()", b"fetch(required)") if unsafe else base_data.replace(b"import json\n", b"")
    left = commit(left_data, "target removes unused import" if not unsafe else "target requires argument")
    git("checkout", "-b", "source", base)
    right_data = base_data + (b"\ndef caller():\n    return fetch()\n" if unsafe else RIGHT[len(BASE):])
    right = commit(right_data, "source adds caller")
    git("checkout", "target")
    return {"base": base, "left": left, "right": right}
