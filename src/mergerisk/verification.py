"""Optional explicit runtime checks. Never executes repository code on the host."""
from __future__ import annotations

from dataclasses import dataclass
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tempfile
import unicodedata
import uuid

from mergerisk.git.plumbing import bounded_run, installed_tool, read_blobs, tree_entries, validate_path


_SNAPSHOT_LIMIT = 32 * 1024 * 1024


def _validate_snapshot_paths(entries):
    spellings = {}
    for path in entries:
        validate_path(path)
        if os.name != "nt" and sys.platform != "darwin":
            continue
        parts = path.split("/")
        for index, part in enumerate(parts, start=1):
            if os.name == "nt":
                reserved = ntpath.isreserved(part) if hasattr(ntpath, "isreserved") else PureWindowsPath(part).is_reserved()
                if reserved or part != part.rstrip(" .") or any(c in '<>"|?*' or ord(c) < 32 for c in part):
                    raise ValueError("A tracked path cannot be represented safely on Windows.")
            prefix = "/".join(parts[:index])
            key = unicodedata.normalize("NFC", prefix).casefold()
            if spellings.setdefault(key, prefix) != prefix:
                raise ValueError("Runtime snapshot has paths that may alias on the host filesystem.")


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
    unavailable = {"status": "validation_unavailable", "reason": "Docker sandbox unavailable; no project code was executed.", "runs": []}
    if service is None or preview is None or not preview.scenario.is_clean:
        return unavailable
    docker = installed_tool("docker", service.repo)
    if not docker:
        return unavailable
    try:
        info = bounded_run([docker, "image", "inspect", "--format", "{{json .Config.Volumes}}", config.image], timeout=10, limit=65536)
        if info.returncode:
            return {**unavailable, "reason": "Configured image is not available locally; no automatic pulls."}
        volumes = json.loads(info.stdout)
        if volumes not in (None, {}):
            return {**unavailable, "reason": "Runtime images cannot declare writable volumes."}
    except (OSError, RuntimeError, ValueError) as error:
        return {**unavailable, "reason": str(error)}
    runs = []
    for role, revision in (("left", preview.scenario.left_commit), ("right", preview.scenario.right_commit),
                           ("merge", preview.scenario.merge_tree), ("fixed", preview.scenario.merge_tree)):
        try:
            entries = tree_entries(service.repo, revision)
            if any(mode not in {"100644", "100755"} for mode, _, _ in entries.values()):
                raise ValueError("Symlink/submodule snapshots cannot enter the runtime sandbox.")
            _validate_snapshot_paths(entries)
            blobs = read_blobs(service.repo, [oid for _, _, oid in entries.values()])
            replacements = preview.repair.candidate if role == "fixed" else {}
            snapshot = {path: replacements.get(path, blobs[oid]) for path, (_, _, oid) in entries.items()}
            if sum(map(len, snapshot.values())) > _SNAPSHOT_LIMIT:
                raise ValueError("Runtime snapshot exceeds 32 MiB across tracked paths.")
        except (OSError, RuntimeError, ValueError) as error:
            return {**unavailable, "reason": str(error), "runs": runs}
        with tempfile.TemporaryDirectory(prefix="mergerisk-runtime-") as temp:
            root = Path(temp) / "snapshot"
            root.mkdir()
            root.chmod(0o755)
            for path, content in snapshot.items():
                mode = entries[path][0]
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                parent = destination.parent
                while parent != root:
                    parent.chmod(0o755)
                    parent = parent.parent
                with destination.open("xb") as stream:
                    stream.write(content)
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
                try:
                    cleanup = bounded_run([docker, "rm", "-f", name], timeout=10, limit=65536)
                    if cleanup.returncode and b"No such container" not in cleanup.stderr:
                        runs[-1]["cleanup_error"] = "Docker could not confirm container cleanup."
                except (OSError, RuntimeError):
                    runs[-1]["cleanup_error"] = "Docker could not confirm container cleanup."
            if (runs[-1]["exit_code"] is None or runs[-1]["exit_code"] in {125, 126, 127}
                    or runs[-1].get("cleanup_error")):
                return {**unavailable, "reason": "A runtime command or container cleanup did not complete reliably.", "runs": runs}
    verified = all(runs[i]["exit_code"] == 0 for i in (0, 1, 3))
    return {"status": "runtime_verified" if verified else "validation_unavailable", "runs": runs,
            "comparison": ("merge-introduced failure repaired" if verified and runs[2]["exit_code"] != 0
                           else "configured checks passed" if verified
                           else "parent/environment/candidate failure; insufficient evidence for runtime verification"),
            "scope": "Only the explicitly configured command in a restricted container; not proof of arbitrary behavior."}
