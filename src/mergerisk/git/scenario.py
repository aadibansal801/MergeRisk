"""Assemble immutable Git merge scenarios without touching checkout state."""

from __future__ import annotations

import re
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from .plumbing import environment as git_environment, run_git


_TIMEOUT_SECONDS = 30
_OBJECT_ID_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_VERSION_PATTERN = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


class GitCommandError(RuntimeError):
    """A Git command failed or exceeded its execution limit."""


class UnresolvedParentError(ValueError):
    """The requested revisions do not have a resolvable common parent."""


class GitVersionError(RuntimeError):
    """The installed Git version cannot create a candidate merge tree."""


@dataclass(frozen=True)
class GitScenario:
    """Resolved base, branch heads, and merge-tree outcome."""

    base_commit: str
    left_commit: str
    right_commit: str
    merge_tree: str | None
    is_clean: bool
    conflict_files: list[str]
    git_version: str


class GitScenarioAssembler:
    """Resolve revisions and create merge trees using read-only Git plumbing."""

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.expanduser().resolve()
        if not self.repo_path.is_dir():
            raise ValueError(f"repository path is not a directory: {self.repo_path}")
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0 or result.stdout.strip() != "true":
            detail = result.stderr.strip() or "path is not inside a Git working tree"
            raise ValueError(f"not a Git working tree at {self.repo_path}: {detail}")
        version_result = self._run_git(["--version"])
        self.git_version = version_result.stdout.strip()
        match = _VERSION_PATTERN.search(self.git_version)
        if match is None:
            raise GitVersionError(f"could not parse Git version: {self.git_version!r}")
        self._version = tuple(int(part or 0) for part in match.groups())
        if self._version < (2, 43, 0):
            raise GitVersionError("Git 2.43 or newer is required for the authoritative merge-tree workflow")

    def _run_git(
        self,
        arguments: list[str],
        check: bool = True,
        *,
        environment: dict[str, str] | None = None,
        config_overrides: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a bounded Git command and retain stderr for useful diagnostics."""
        try:
            raw = run_git(self.repo_path, arguments, check=False, env=environment, config=config_overrides or ())
            result = subprocess.CompletedProcess(raw.args, raw.returncode,
                                                 raw.stdout.decode("utf-8", "surrogateescape"),
                                                 raw.stderr.decode("utf-8", "surrogateescape"))
        except subprocess.TimeoutExpired as error:
            raise GitCommandError(
                f"Git command timed out after {_TIMEOUT_SECONDS}s: {arguments!r}"
            ) from error
        except OSError as error:
            raise GitCommandError(f"could not execute Git: {error}") from error
        except RuntimeError as error:
            # bounded_run reports timeouts and output-limit overruns as RuntimeError.
            raise GitCommandError(f"{error}: {arguments!r}") from error
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
        return result

    def resolve_commit(self, rev: str) -> str:
        """Resolve a commitish to a full Git object identifier."""
        if not rev or "\x00" in rev:
            raise ValueError("revision must be a non-empty Git revision expression")
        result = self._run_git(["rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"])
        commit = result.stdout.strip().lower()
        if _OBJECT_ID_PATTERN.fullmatch(commit) is None:
            raise GitCommandError(f"revision did not resolve to a full SHA-1 or SHA-256 commit: {rev!r}")
        return commit

    def compute_merge_base(self, left: str, right: str) -> str:
        """Return the unique merge base of two resolved revisions."""
        left_commit = self.resolve_commit(left)
        right_commit = self.resolve_commit(right)
        result = self._run_git(["merge-base", "--all", left_commit, right_commit], check=False)
        if result.returncode == 1 and not result.stdout.strip():
            raise UnresolvedParentError(f"no merge base exists between {left!r} and {right!r}")
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git merge-base failed ({result.returncode}): {detail}")
        bases = sorted(set(line.strip().lower() for line in result.stdout.splitlines() if line.strip()))
        if len(bases) != 1:
            raise UnresolvedParentError(
                f"multiple merge bases exist between {left!r} and {right!r}; criss-cross merges are unsupported"
            )
        if _OBJECT_ID_PATTERN.fullmatch(bases[0]) is None:
            raise GitCommandError(f"git merge-base returned an invalid commit identifier: {bases[0]!r}")
        return bases[0]

    def create_candidate_tree(self, base: str, left: str, right: str) -> tuple[str | None, bool, list[str]]:
        """Compute the candidate tree with merge-tree, without updating refs or index."""
        base_commit = self.resolve_commit(base)
        left_commit = self.resolve_commit(left)
        right_commit = self.resolve_commit(right)
        safe_environment, safe_overrides = self._safe_merge_environment()
        result = self._run_git(
            [
                "merge-tree", "--write-tree", "--messages", "--name-only", "-z",
                f"--merge-base={base_commit}", left_commit, right_commit,
            ],
            check=False,
            environment=safe_environment,
            config_overrides=safe_overrides,
        )
        if result.returncode not in (0, 1):
            detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
            raise GitCommandError(f"git merge-tree failed ({result.returncode}): {detail}")

        output_parts = result.stdout.split("\x00")
        first = output_parts[0].strip() if output_parts else ""
        merge_tree = first if _OBJECT_ID_PATTERN.fullmatch(first) else None
        is_clean = result.returncode == 0
        conflict_files: list[str] = []
        if not is_clean:
            # With -z the conflicted paths (of every conflict kind, e.g. modify/delete) follow the tree ID
            # up to the first empty field; message text is only a fallback.
            for part in output_parts[1:]:
                if not part:
                    break
                conflict_files.append(part)
            conflict_files = sorted(set(conflict_files)) or self._parse_conflict_files_from_messages(result.stdout)
        return merge_tree, is_clean, conflict_files

    def _safe_merge_environment(self) -> tuple[dict[str, str], list[str]]:
        """Prevent configured external merge drivers from executing during analysis."""
        environment = git_environment()
        for key in tuple(environment):
            if key in {"GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}:
                environment.pop(key, None)
            elif key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
                environment.pop(key, None)
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_CONFIG_GLOBAL"] = os.devnull

        configured = self._run_git(
            ["config", "--includes", "--name-only", "--get-regexp", r"^merge\..*\.driver$"],
            check=False,
            environment=environment,
        )
        if configured.returncode not in (0, 1):
            detail = configured.stderr.strip() or "could not inspect local merge-driver configuration"
            raise GitCommandError(detail)
        overrides: list[str] = ["merge.renormalize=false"]
        for key in configured.stdout.splitlines():
            if not re.fullmatch(r"merge\.[A-Za-z0-9._-]+\.driver", key, flags=re.IGNORECASE):
                raise GitCommandError(f"cannot safely disable configured merge driver key: {key!r}")
            overrides.append(f"{key}=")
        return environment, overrides



    @staticmethod
    def _parse_conflict_files_from_messages(output: str) -> list[str]:
        """Fallback parser for merge-tree conflict messages on older Git releases."""
        conflicts: set[str] = set()
        for line in output.splitlines():
            marker = "Merge conflict in "
            if marker in line:
                conflicts.add(line.split(marker, 1)[1].strip())
        return sorted(conflicts)

    def assemble(
        self,
        left_rev: str,
        right_rev: str,
        explicit_base: str | None = None,
    ) -> GitScenario:
        """Resolve both heads and their base, then create the candidate merge tree."""
        left_commit = self.resolve_commit(left_rev)
        right_commit = self.resolve_commit(right_rev)
        computed_base = self.compute_merge_base(left_commit, right_commit)
        base_commit = self.resolve_commit(explicit_base) if explicit_base is not None else computed_base
        if explicit_base is not None and base_commit != computed_base:
            raise ValueError(
                f"explicit base {explicit_base!r} is not the selected merge base of {left_rev!r} and {right_rev!r}"
            )
        merge_tree, is_clean, conflict_files = self.create_candidate_tree(
            base_commit, left_commit, right_commit,
        )
        return GitScenario(
            base_commit=base_commit,
            left_commit=left_commit,
            right_commit=right_commit,
            merge_tree=merge_tree,
            is_clean=is_clean,
            conflict_files=conflict_files,
            git_version=self.git_version,
        )
