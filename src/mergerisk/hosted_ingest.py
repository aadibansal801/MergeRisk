"""Fetch public GitHub branches into a disposable, checkout-free analysis repository."""
from __future__ import annotations

from base64 import b64encode
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
from time import monotonic, sleep

from mergerisk.git import UnresolvedParentError
from mergerisk.git.plumbing import installed_tool, run_git, tree_entries
from mergerisk.service import MergePreview, MergeService


_OWNER = r"[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,38}"
_REPOSITORY = re.compile(rf"({_OWNER})/([a-z0-9._-]{{1,100}})", re.ASCII | re.IGNORECASE)
_URL = re.compile(r"https://github\.com/([a-z0-9._/-]{3,144})/?", re.ASCII | re.IGNORECASE)
_BAD_REF_CHARACTERS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")
_FETCH_TIMEOUT = 30
_MAX_PACK_BYTES = 32 * 1024 * 1024
_MAX_TREE_BLOB_BYTES = 2 * 1024 * 1024
_MAX_TREE_BYTES = 24 * 1024 * 1024
_MAX_PATCH_BYTES = 300 * 1024
_MAX_FINDING_BYTES = 80 * 1024
_MAX_FINDINGS = 100
_MAX_RESPONSE_BYTES = 512 * 1024
_REFS = ("refs/mergerisk/target", "refs/mergerisk/source")


class HostedIngestError(ValueError):
    """A hosted analysis failure with a message safe to show to the requester."""


def _repository_slug(value: str) -> str:
    value = value.lower()
    match = _REPOSITORY.fullmatch(value)
    if not match or match[2] in {".", "..", ".git"}:
        raise HostedIngestError("Enter a GitHub repository URL in the form https://github.com/owner/repo.")
    return value


def parse_repository_url(url: str) -> str:
    """Return the canonical owner/repository slug for a GitHub HTTPS repo URL."""
    match = _URL.fullmatch(url.strip())
    if not match:
        raise HostedIngestError("Enter a GitHub repository URL in the form https://github.com/owner/repo.")
    return _repository_slug(match[1].lower().removesuffix("/").removesuffix(".git"))


def validate_branch(name: str) -> str:
    """Accept a literal branch name, without Git revision syntax."""
    try:
        size = len(name.encode("utf-8"))
    except UnicodeError as error:
        raise HostedIngestError("Enter a valid Git branch name.") from error
    if (not 0 < size <= 255 or name == "@" or name.startswith("-") or name.endswith(".")
            or ".." in name or "@{" in name or _BAD_REF_CHARACTERS.search(name)
            or any(not segment or segment.startswith(".") or segment.endswith(".lock") for segment in name.split("/"))):
        raise HostedIngestError("Enter a valid Git branch name.")
    return name


def _network_environment() -> dict[str, str]:
    keys = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "TMPDIR",
            "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keys}
    env.update({"GIT_ALLOW_PROTOCOL": "https", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1", "GCM_INTERACTIVE": "Never"})
    return env


def _stop_fetch(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=3, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    process.wait(timeout=5)


def _fetch(repo: Path, slug: str, target: str, source: str) -> None:
    git = installed_tool("git", repo)
    if git is None:
        raise HostedIngestError("The analysis worker cannot find Git.")
    args = [git, "-C", str(repo), "-c", "http.followRedirects=false", "-c", "http.sslVerify=true",
            "-c", "credential.helper=", "-c", f"core.hooksPath={os.devnull}", "-c", "fetch.fsckObjects=true",
            "-c", "fetch.unpackLimit=1", "-c", "pack.threads=1", "fetch", "--atomic", "--quiet",
            "--no-recurse-submodules", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", "--",
            f"https://github.com/{slug}.git", f"refs/heads/{target}:{_REFS[0]}", f"refs/heads/{source}:{_REFS[1]}"]
    if os.name == "posix":
        # Apply the pack-file limit before Git spawns its HTTPS and index-pack children.
        wrapper = "\n".join((
            "import os, resource, sys",
            "limit = int(sys.argv[1])",
            "resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))",
            "os.execv(sys.argv[2], sys.argv[2:])",
        ))
        args = [sys.executable, "-I", "-c", wrapper, str(_MAX_PACK_BYTES), *args]
        if watchdog := installed_tool("timeout", repo):
            # Bound the fetch group even if the supervising analysis worker is killed.
            args = [watchdog, "--signal=KILL", str(_FETCH_TIMEOUT), *args]
    deadline = monotonic() + _FETCH_TIMEOUT
    pack_dir = repo / ".git" / "objects" / "pack"
    with TemporaryFile() as errors, subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors,
        env=_network_environment(), start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        try:
            while True:
                size = 0
                for path in pack_dir.iterdir():
                    try:
                        size += path.stat().st_size
                    except FileNotFoundError:
                        continue  # Git may rename a completed pack while the transfer is monitored.
                if size > _MAX_PACK_BYTES:
                    raise HostedIngestError("Repository history exceeds the hosted size limit.")
                if os.fstat(errors.fileno()).st_size > 65536:
                    raise HostedIngestError("GitHub fetch exceeded the hosted diagnostic limit.")
                code = process.poll()
                if code is not None:
                    break
                if monotonic() >= deadline:
                    raise HostedIngestError("Fetching the repository exceeded the hosted time limit.")
                sleep(0.1)
        except BaseException:
            _stop_fetch(process)
            raise
        if code:
            errors.seek(0)
            diagnostic = errors.read(8192).lower()
            if b"file size limit" in diagnostic or b"file too large" in diagnostic:
                raise HostedIngestError("Repository history exceeds the hosted size limit.")
            raise HostedIngestError("GitHub could not provide both branches. Check the names and repository visibility.")


def _check_tree_sizes(repo: Path, revisions: tuple[str, str, str]) -> None:
    snapshots = [[oid for _, kind, oid in tree_entries(repo, rev).values() if kind == "blob"] for rev in revisions]
    blobs = sorted({oid for snapshot in snapshots for oid in snapshot})
    query = "".join(f"{oid}\n" for oid in blobs).encode("ascii")
    sizes = run_git(repo, ["cat-file", "--batch-check=%(objectsize)"], data=query).stdout.splitlines()
    if len(sizes) != len(blobs) or any(not size.isdigit() for size in sizes):
        raise HostedIngestError("Git returned incomplete repository objects.")
    lengths = dict(zip(blobs, map(int, sizes)))
    if (any(size > _MAX_TREE_BLOB_BYTES for size in lengths.values()) or sum(lengths.values()) > _MAX_TREE_BYTES
            or any(sum(lengths[oid] for oid in snapshot) > _MAX_TREE_BYTES for snapshot in snapshots)):
        raise HostedIngestError("Repository source snapshots exceed the hosted size limit.")


def _patch(repo: Path, preview: MergePreview) -> str | None:
    repair = preview.repair
    if repair is None or repair.validation != "static_verified":
        return None
    tree = preview.scenario.merge_tree
    changes = {path: data for path, data in repair.candidate.items() if data != preview.versions["merge"][path]}
    if not changes:
        return None
    entries = tree_entries(repo, tree)
    index_env = {"GIT_INDEX_FILE": str(repo / ".git" / "mergerisk-patch-index")}
    run_git(repo, ["read-tree", tree], env=index_env)
    records = bytearray()
    for path, data in sorted(changes.items()):
        mode, kind, _ = entries[path]
        if mode not in {"100644", "100755"} or kind != "blob":
            raise HostedIngestError("Repair export requires regular tracked files.")
        oid = run_git(repo, ["hash-object", "-w", "--stdin"], data=data).stdout.strip()
        records.extend(mode.encode() + b" " + oid + b"\t" + path.encode("utf-8", "surrogateescape") + b"\0")
    run_git(repo, ["update-index", "-z", "--index-info"], data=bytes(records), env=index_env)
    fixed = run_git(repo, ["write-tree"], env=index_env).stdout.decode("ascii").strip()
    patch = run_git(repo, ["diff", "--binary", "--full-index", "--no-color", "--no-ext-diff", "--no-textconv",
                           "--src-prefix=a/", "--dst-prefix=b/", tree, fixed, "--"], config=["core.quotePath=true"]).stdout
    if not patch or len(patch) > _MAX_PATCH_BYTES:
        return None
    run_git(repo, ["read-tree", tree], env=index_env)
    run_git(repo, ["apply", "--cached", "--whitespace=nowarn", "-"], env=index_env, data=patch)
    applied = run_git(repo, ["write-tree"], env=index_env).stdout.decode("ascii").strip()
    if applied != fixed:
        raise HostedIngestError("Repair export did not reproduce the verified candidate tree.")
    return b64encode(patch).decode("ascii")


def _safe_json(value):
    # Git paths can contain undecodable native bytes. Preserve exports as bytes and make display text valid UTF-8.
    return json.loads(json.dumps(value, ensure_ascii=False).encode("utf-8", "replace"))


def _summarize(repo: Path, result: dict, preview: MergePreview) -> dict:
    scenario, analysis, repair = preview.scenario, preview.original, preview.repair
    result.update(base_commit=scenario.base_commit, merge_tree=scenario.merge_tree,
                  conflict_files=scenario.conflict_files[:_MAX_FINDINGS])
    if analysis is None:
        result.update(status="textual_conflict", message="Git reported textual merge conflicts.")
        return _safe_json(result)
    used = 0
    for item in analysis.findings[:_MAX_FINDINGS]:
        finding = item.to_dict()
        used += len(json.dumps(finding))
        if used > _MAX_FINDING_BYTES:
            break
        result["findings"].append(finding)
    status = analysis.status.value
    if not analysis.findings and analysis.coverage.files_analyzed == 0:
        status = "inconclusive"
        result["message"] = "The candidate contains no supported Python files to analyze."
    elif status == "success":
        status = "findings_present" if analysis.findings else "no_supported_findings"
    result.update(status=status, finding_count=len(analysis.findings), coverage=asdict(analysis.coverage),
                  validation=repair.validation if repair else "validation_unavailable", patch_b64=_patch(repo, preview))
    return _safe_json(result)


def analyze_repository(repository: str, target: str, source: str) -> dict:
    """Analyze only the two explicit public branch histories, without running project code."""
    slug = _repository_slug(repository)
    target, source = validate_branch(target), validate_branch(source)
    if target == source:
        raise HostedIngestError("Choose two different branches to compare.")
    result = {"repository": slug, "target": target, "source": source, "base_commit": None, "merge_tree": None,
              "validation": "validation_unavailable", "findings": [], "finding_count": 0, "coverage": None,
              "conflict_files": [], "patch_b64": None, "message": None}
    try:
        with TemporaryDirectory(prefix="mergerisk-hosted-") as directory:
            repo = Path(directory)
            run_git(repo, ["init", "--quiet", "--template="])
            _fetch(repo, slug, target, source)
            service = MergeService(repo)
            left, right = (service.assembler.resolve_commit(ref) for ref in _REFS)
            result.update(target_commit=left, source_commit=right)
            try:
                base = service.assembler.compute_merge_base(left, right)
            except UnresolvedParentError:
                return {**result, "status": "inconclusive", "message": "Git could not resolve a unique common ancestor."}
            if base in (left, right):
                tip = left if base == right else right
                tree = run_git(repo, ["rev-parse", f"{tip}^{{tree}}"]).stdout.decode("ascii").strip()
                if base == right:
                    return {**result, "base_commit": base, "merge_tree": tree, "status": "already_contained",
                            "message": "The source commit is already contained in the target branch."}
                return {**result, "base_commit": base, "merge_tree": tree, "status": "fast_forward",
                        "message": "The target is an ancestor of the source. This merge can fast-forward."}
            _check_tree_sizes(repo, (base, left, right))
            preview = service.preview(left, right, base=base)
            return _summarize(repo, result, preview)
    except HostedIngestError:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise HostedIngestError("Repository analysis could not complete within the hosted limits.") from error


def main() -> None:
    """Serve a single job over bounded standard input and output."""
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise HostedIngestError("The repository request is too large.")
        data = json.loads(raw)
        if (not isinstance(data, dict) or set(data) != {"repository", "target", "source"}
                or not all(isinstance(value, str) for value in data.values())):
            raise HostedIngestError("Enter a repository and two branch names.")
        result = analyze_repository(**data)
        encoded = json.dumps({"result": result}, separators=(",", ":"))
        if len(encoded) >= _MAX_RESPONSE_BYTES:
            result["patch_b64"] = None
            result["message"] = "The repair patch exceeds the hosted report size limit."
            encoded = json.dumps({"result": result}, separators=(",", ":"))
        if len(encoded) >= _MAX_RESPONSE_BYTES:
            raise HostedIngestError("The analysis report exceeds the hosted size limit.")
    except HostedIngestError as error:
        encoded = json.dumps({"error": str(error)})
    except (UnicodeError, ValueError, RecursionError):
        encoded = json.dumps({"error": "Enter a repository and two branch names."})
    sys.stdout.write(encoded + "\n")


if __name__ == "__main__":
    main()
