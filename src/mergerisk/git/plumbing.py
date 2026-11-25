"""Bounded Git plumbing with no hooks, shell, global config or inherited Git redirection."""
from __future__ import annotations

import os
import queue
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import threading


def environment(overrides=None):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1"})
    env.update(overrides or {})
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
    return env


def installed_tool(name: str, repo: Path | None = None) -> str | None:
    """Use an installed executable without implicit current-directory search."""
    filename = name + ".exe" if os.name == "nt" else name
    cwd = Path.cwd().resolve()
    root = repo.resolve() if repo is not None else None
    for entry in os.get_exec_path():
        directory = Path(entry.strip('"') if os.name == "nt" else entry)
        if not directory.is_absolute():
            continue
        path = shutil.which(str(directory / filename))
        if path:
            executable = Path(path).resolve()
            if executable.parent != cwd and (root is None or not executable.is_relative_to(root)):
                return str(executable)
    return None


def _git(repo):
    git = installed_tool("git", repo)
    if git is None:
        raise FileNotFoundError("Git executable was not found on the installed PATH.")
    return git


def bounded_run(argv, *, data: bytes = b"", env=None, timeout=30, limit=64 * 1024 * 1024):
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("Command input exceeds 64 MiB limit")
    output = [bytearray(), bytearray()]
    exceeded = threading.Event()
    with tempfile.TemporaryFile() as stdin:
        stdin.write(data)
        stdin.seek(0)
        process = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

        def drain(stream, target):
            while chunk := stream.read(65536):
                if len(target) + len(chunk) > limit:
                    exceeded.set()
                    process.kill()
                    break
                target.extend(chunk)
            stream.close()

        threads = [threading.Thread(target=drain, args=(stream, target), daemon=True)
                   for stream, target in zip((process.stdout, process.stderr), output)]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise RuntimeError(f"Command timed out after {timeout}s") from error
        finally:
            for thread in threads:
                thread.join(timeout=2)
        if exceeded.is_set():
            raise RuntimeError(f"Command output exceeds {limit} byte limit")
    return subprocess.CompletedProcess(argv, process.returncode, bytes(output[0]), bytes(output[1]))


def run_git(repo: Path, args, *, data=b"", env=None, check=True, config=()):
    result = bounded_run([_git(repo), "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
                          "-c", f"core.attributesFile={os.devnull}", "-c", "core.quotePath=false",
                          "-c", "merge.verifySignatures=false", "-c", "commit.gpgSign=false",
                          *(part for item in config for part in ("-c", item)), "-C", str(repo), *args],
                         data=data, env=environment(env))
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace').strip()[:4000]}")
    return result


def git_identity(repo: Path):
    # Read only identity values from normal Git config; never use that config to execute an operation.
    env = environment()
    env.pop("GIT_CONFIG_GLOBAL", None)
    values = {}
    for field in ("name", "email"):
        result = bounded_run([_git(repo), "-C", str(repo), "config", "--includes", "--get", "user." + field], env=env, limit=16384)
        value = result.stdout.decode("utf-8", "strict").strip()
        if result.returncode or not value or any(c in value for c in "\0\r\n"):
            raise ValueError("Git author identity is missing or invalid. Configure git user.name and user.email before creating a commit.")
        values["GIT_AUTHOR_" + field.upper()] = value
        values["GIT_COMMITTER_" + field.upper()] = value
    return values


def validate_path(path: str):
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if (not path or path != normalized or PurePosixPath(path).is_absolute()
            or any(p in {"", ".", ".."} or p.rstrip(" .").casefold() == ".git" for p in parts)
            or any(c in path for c in "\0\r\n:")):
        raise ValueError("Unsafe repository-relative path")


def tree_entries(repo, revision):
    output = run_git(repo, ["ls-tree", "-rz", revision]).stdout
    entries = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        path = raw_path.decode("utf-8", "surrogateescape")
        validate_path(path)
        entries[path] = (mode, kind, oid)
    if len(entries) > 10000:
        raise ValueError("Repository exceeds 10,000 tracked entries limit")
    return entries


def read_blobs(repo, oids):
    unique = sorted(set(oids))
    if not unique:
        return {}
    # Inspect sizes before reading payloads; one batch process for immutable blobs.
    sizes = run_git(repo, ["cat-file", "--batch-check"], data="".join(s + "\n" for s in unique).encode()).stdout
    total = 0
    for line in sizes.splitlines():
        _, kind, size = line.split()
        if kind != b"blob" or int(size) > 2 * 1024 * 1024:
            raise ValueError("Unsupported blob type or file larger than 2 MiB")
        total += int(size)
    if total > 32 * 1024 * 1024:
        raise ValueError("Snapshot source exceeds 32 MiB limit")
    output = run_git(repo, ["cat-file", "--batch"], data="".join(s + "\n" for s in unique).encode()).stdout
    offset, result = 0, {}
    for oid in unique:
        end = output.index(b"\n", offset)
        actual, kind, size = output[offset:end].split()
        if actual.decode() != oid or kind != b"blob":
            raise RuntimeError("Unexpected batch object identity")
        start, length = end + 1, int(size)
        result[oid] = output[start:start + length]
        offset = start + length + 1
    if offset != len(output):
        raise RuntimeError("Malformed Git batch response")
    return result


class PreparedRefUpdate:
    """Hold Git's compare-and-swap branch lock while a checked checkout is updated."""
    def __init__(self, repo: Path, branch: str, new: str, old: str):
        if not branch.startswith("refs/heads/") or any(c in branch for c in "\0\n\r "):
            raise ValueError("Expected a full local branch reference")
        self.repo, self.branch, self.new, self.old = repo, branch, new, old
        self.process = None
        self.lines = queue.Queue(maxsize=8)
        self.committed = False
        self.reader = None

    def _send(self, command, expected):
        self.process.stdin.write((command + "\n").encode("utf-8"))
        self.process.stdin.flush()
        try:
            line = self.lines.get(timeout=10)
        except queue.Empty as error:
            raise RuntimeError("Git reference transaction timed out") from error
        if line.strip() != expected:
            raise RuntimeError("Git refused the expected branch update; references are stale or locked")

    def __enter__(self):
        self.process = subprocess.Popen([_git(self.repo), "-c", f"core.hooksPath={os.devnull}", "-C", str(self.repo),
                                         "update-ref", "-m", "MergeRisk checked fast-forward", "--stdin"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment(), bufsize=0)

        def read():
            while line := self.process.stdout.readline(4096):
                self.lines.put(line)
            self.lines.put(b"")
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self._send("start", b"start: ok")
            self.process.stdin.write(f"update {self.branch} {self.new} {self.old}\n".encode())
            self._send("prepare", b"prepare: ok")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def commit(self):
        self._send("commit", b"commit: ok")
        self.committed = True

    def __exit__(self, *exc):
        try:
            if self.process.poll() is None and not self.committed:
                try:
                    self.process.stdin.write(b"abort\n")
                except OSError:
                    pass  # The failed Git process has already closed its input.
        finally:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.reader.join(timeout=2)
            self.process.stdout.close()
