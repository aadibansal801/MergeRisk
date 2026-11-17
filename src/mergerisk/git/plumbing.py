"""Bounded Git plumbing with no hooks, shell, global config or inherited Git redirection."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import threading


def environment(overrides=None):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"})
    env.update(overrides or {})
    return env


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
    result = bounded_run(["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
                          "-c", f"core.attributesFile={os.devnull}", "-c", "core.quotePath=false",
                          *(part for item in config for part in ("-c", item)), "-C", str(repo), *args],
                         data=data, env=environment(env))
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace').strip()[:4000]}")
    return result


def validate_path(path: str):
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if (not path or path != normalized or PurePosixPath(path).is_absolute()
            or any(p in {"", ".", "..", ".git"} for p in parts)
            or ":" in parts[0] or "\0" in path):
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
