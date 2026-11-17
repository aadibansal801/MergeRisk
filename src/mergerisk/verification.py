"""Optional explicit runtime checks. Never executes repository code on the host."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from mergerisk.git.plumbing import bounded_run, read_blobs, tree_entries, validate_path


@dataclass(frozen=True)
class RuntimeConfig:
    image: str
    command: tuple[str, ...]
    timeout: int = 30

    def __post_init__(self):
        if not isinstance(self.image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image):
            raise ValueError("Runtime image must be a locally available immutable sha256 image ID")
        if not isinstance(self.command, (tuple, list)) or not self.command or len(self.command) > 32 or any(not isinstance(a, str) or "\0" in a or len(a) > 1024 for a in self.command):
            raise ValueError("Runtime command must be a nonempty argument array (at most 32 arguments)")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 120:
            raise ValueError("Runtime timeout must be 1–120 seconds")


def verify_runtime(service, preview, config: RuntimeConfig):
    docker = shutil.which("docker")
    unavailable = {"status": "validation_unavailable", "reason": "Docker sandbox unavailable; no project code was executed.", "runs": []}
    if not docker or not preview.scenario.is_clean:
        return unavailable
    try:
        info = bounded_run([docker, "image", "inspect", config.image], timeout=10, limit=65536)
        if info.returncode:
            return {**unavailable, "reason": "Configured image is not available locally; no automatic pulls."}
    except (OSError, RuntimeError) as error:
        return {**unavailable, "reason": str(error)}
    runs = []
    for role, revision in (("left", preview.scenario.left_commit), ("right", preview.scenario.right_commit),
                           ("merge", preview.scenario.merge_tree), ("fixed", preview.scenario.merge_tree)):
        entries = tree_entries(service.repo, revision)
        if any(mode not in {"100644", "100755"} for mode, _, _ in entries.values()):
            return {**unavailable, "reason": "Symlink/submodule snapshots cannot enter the runtime sandbox."}
        blobs = read_blobs(service.repo, [oid for _, _, oid in entries.values()])
        with tempfile.TemporaryDirectory(prefix="mergerisk-runtime-") as temp:
            root = Path(temp)
            root.chmod(0o755)
            for path, (mode, _, oid) in entries.items():
                validate_path(path)
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                parent = destination.parent
                while parent != root:
                    parent.chmod(0o755)
                    parent = parent.parent
                content = preview.repair.candidate.get(path, blobs[oid]) if role == "fixed" else blobs[oid]
                destination.write_bytes(content)
                destination.chmod(0o755 if mode == "100755" else 0o644)
            name = "mergerisk-" + uuid.uuid4().hex
            argv = [docker, "run", "--rm", "--pull=never", "--name", name,
                    "--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL",
                    "--security-opt=no-new-privileges", "--pids-limit=64", "--cpus=1", "--memory=256m", "--memory-swap=256m",
                    "--ulimit=nofile=256:256", "--log-driver=none",
                    "--tmpfs=/tmp:rw,noexec,nosuid,size=67108864", "--tmpfs=/run:rw,noexec,nosuid,size=16777216",
                    "--mount", f"type=bind,source={root},target=/workspace,readonly", "--workdir=/workspace",
                    "--env=PYTHONDONTWRITEBYTECODE=1", "--entrypoint", config.command[0], config.image, *config.command[1:]]
            try:
                result = bounded_run(argv, timeout=config.timeout, limit=65536)
                runs.append({"role": role, "command": list(config.command), "image": config.image,
                             "exit_code": result.returncode, "stdout": result.stdout.decode("utf-8", "replace"),
                             "stderr": result.stderr.decode("utf-8", "replace")})
            except (OSError, RuntimeError) as error:
                runs.append({"role": role, "command": list(config.command), "image": config.image, "exit_code": None, "error": str(error)})
            finally:
                bounded_run([docker, "rm", "-f", name], timeout=10, limit=65536)
    parents_pass = all(r["exit_code"] == 0 for r in runs[:2])
    fixed_pass = runs[-1]["exit_code"] == 0
    return {"status": "runtime_verified" if parents_pass and fixed_pass else "validation_unavailable", "runs": runs,
            "comparison": ("merge-introduced failure repaired" if parents_pass and runs[2]["exit_code"] != 0 and fixed_pass
                           else "configured checks passed" if parents_pass and fixed_pass
                           else "parent/environment/candidate failure; insufficient evidence for runtime verification"),
            "scope": "Only the explicitly configured command in a restricted container; not proof of arbitrary behavior."}
