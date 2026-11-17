"""One immutable candidate/repair/Git workflow for both CLI and dashboard."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import json
import tempfile
import uuid

from mergerisk.analysis.inventory import RepositoryInventory
from mergerisk.analysis.pipeline import AnalysisConfig, AnalysisOrchestrator
from mergerisk.domain.results import AnalysisResult, AnalysisStatus
from mergerisk.domain.revisions import RevisionContext
from mergerisk.git import GitScenario, GitScenarioAssembler
from mergerisk.git.plumbing import read_blobs, run_git, tree_entries
from mergerisk.repair import RepairResult, decode_source, digest, repair_candidate, static_defects, text_versions


@dataclass
class MergePreview:
    scenario: GitScenario
    original: AnalysisResult | None
    repair: RepairResult | None
    versions: dict[str, dict[str, bytes]]
    preexisting: list[dict]
    fingerprint: str

    def to_dict(self, *, include_sources=False):
        result = {"scenario": asdict(self.scenario), "fingerprint": self.fingerprint,
                  "merge_status": "textually_clean" if self.scenario.is_clean else "textual_conflict",
                  "diagnosis": "findings_present" if self.original and self.original.findings else "no_supported_findings",
                  "analysis": self.original.to_dict() if self.original else None,
                  "fixed_analysis": self.repair.analysis.to_dict() if self.repair else None,
                  "repairs": [p.to_dict() for p in self.repair.plans] if self.repair else [],
                  "validation": self.repair.validation if self.repair else "validation_unavailable",
                  "checks": self.repair.checks if self.repair else [],
                  "rejection": self.repair.rejection if self.repair else None,
                  "runtime": {"status": "validation_unavailable", "reason": "Static-only analysis; repository code was not executed."},
                  "preexisting": self.preexisting}
        if include_sources:
            files = {}
            versions = {**self.versions}
            if self.repair:
                versions["fixed"] = self.repair.candidate
            for role, sources in versions.items():
                for path, data in sources.items():
                    try:
                        text = decode_source(data)
                    except (UnicodeError, SyntaxError):
                        text = "[Unsupported source encoding]"
                    files.setdefault(path, {})[role] = text
            result["files"] = files
        return result


class MergeService:
    def __init__(self, repo: Path):
        self.assembler = GitScenarioAssembler(Path(repo))
        root = run_git(self.assembler.repo_path, ["rev-parse", "--show-toplevel"]).stdout.decode("utf-8", "surrogateescape").strip()
        self.repo = Path(root).resolve()
        if self.repo != self.assembler.repo_path:
            raise ValueError("Select the repository root, not a subdirectory")
        self._blobs: dict[str, bytes] = {}

    def _sources(self, revision):
        entries = tree_entries(self.repo, revision)
        selected = {p: v for p, v in entries.items() if p.endswith(".py") and v[0] in {"100644", "100755"}
                    and RepositoryInventory._ignore_reason(p, list(AnalysisConfig().ignore_patterns)) is None}
        missing = {oid for _, _, oid in selected.values()} - self._blobs.keys()
        self._blobs.update(read_blobs(self.repo, missing))
        if sum(len(b) for b in self._blobs.values()) > 64 * 1024 * 1024:
            raise ValueError("Four-version source exceeds 64 MiB limit")
        return {p: self._blobs[oid] for p, (_, _, oid) in selected.items()}, entries

    def preview(self, left: str, right: str, *, base=None, accepted=None, cancel=None, progress=None):
        def checkpoint(message):
            if cancel and cancel.is_set():
                raise InterruptedError("Analysis cancelled")
            if progress:
                progress(message)
        checkpoint("Resolving branches and Git merge tree")
        scenario = self.assembler.assemble(left, right, base)
        identity = digest(json.dumps(asdict(scenario), sort_keys=True).encode())
        if not scenario.is_clean:
            return MergePreview(scenario, None, None, {}, [], identity)
        versions, entries = {}, {}
        for role, revision in (("base", scenario.base_commit), ("left", scenario.left_commit),
                               ("right", scenario.right_commit), ("merge", scenario.merge_tree)):
            checkpoint(f"Reading immutable {role} snapshot")
            versions[role], entries[role] = self._sources(revision)
        context = RevisionContext(scenario.base_commit, scenario.left_commit, scenario.right_commit, scenario.merge_tree)
        sources = text_versions(versions)
        checkpoint("Resolving Python references and branch provenance")
        analysis = AnalysisOrchestrator().analyze_sources(*(sources[r] for r in ("base", "left", "right", "merge")), context)
        unsupported = len(versions["merge"]) - len(sources["merge"])
        special = sum(v[0] not in {"100644", "100755"} for v in entries["merge"].values())
        if unsupported or special:
            analysis = replace(analysis, status=AnalysisStatus.PARTIAL,
                               coverage=replace(analysis.coverage, files_unsupported=analysis.coverage.files_unsupported + unsupported + special),
                               notes=analysis.notes + [f"{unsupported} undecodable source files and {special} symlink/submodule entries not analyzed."])
        analysis = replace(analysis, coverage=replace(analysis.coverage, files_skipped=len(entries["merge"]) - len(versions["merge"])),
                           manifest={**analysis.manifest, "git_version": scenario.git_version})
        preexisting = []
        for role in ("base", "left", "right"):
            checkpoint(f"Recording {role} static defects")
            preexisting.extend({"role": role, "kind": k, "path": p, "detail": d} for k, p, d in sorted(static_defects(sources[role])))
        checkpoint("Planning exact edits and validating the candidate")
        repair = repair_candidate(versions, context, analysis, accepted)
        if analysis.coverage.files_unsupported:
            repair.analysis = replace(repair.analysis, status=AnalysisStatus.PARTIAL, coverage=replace(repair.analysis.coverage,
                                      files_unsupported=max(analysis.coverage.files_unsupported, repair.analysis.coverage.files_unsupported)))
        identity = digest((identity + json.dumps([p.to_dict() for p in repair.plans], sort_keys=True)).encode())
        checkpoint("Complete")
        return MergePreview(scenario, analysis, repair, versions, preexisting, identity)

    def create_commit(self, preview: MergePreview, *, expected: str, allow_partial=False):
        if expected != preview.fingerprint:
            raise ValueError("Stale preview fingerprint; analyze again")
        if not preview.scenario.is_clean or not preview.repair:
            raise ValueError("Textual conflicts must be resolved with Git before creating a commit")
        repair, scenario = preview.repair, preview.scenario
        accepted = {p.id for p in repair.plans if p.tier == "SUGGEST" and p.status == "static_verified"}
        verified = self.preview(scenario.left_commit, scenario.right_commit, accepted=accepted)
        if (verified.fingerprint != expected or verified.repair is None
                or verified.repair.candidate != repair.candidate
                or verified.versions != preview.versions):
            raise ValueError("Stale or modified candidate; recompute the preview")
        repair = verified.repair
        if repair.rejection or repair.analysis.findings:
            raise ValueError("Unresolved blocking findings or invalid repairs; merge commit refused")
        if repair.analysis.status != AnalysisStatus.SUCCESS and not allow_partial:
            raise ValueError("Coverage is partial; explicitly acknowledge its limitations before committing")
        if scenario.left_commit == scenario.right_commit:
            raise ValueError("Both revisions are identical; no merge commit is necessary")
        entries = tree_entries(self.repo, scenario.merge_tree)
        # The private index never touches the user's index or worktree.
        with tempfile.TemporaryDirectory(prefix="mergerisk-index-") as temp:
            env = {"GIT_INDEX_FILE": str(Path(temp) / "index")}
            run_git(self.repo, ["read-tree", scenario.merge_tree], env=env)
            records = bytearray()
            for path, data in sorted(repair.candidate.items()):
                if data == preview.versions["merge"].get(path):
                    continue
                mode, kind, _ = entries[path]
                if mode not in {"100644", "100755"} or kind != "blob":
                    raise ValueError("Repairs may only change regular tracked files")
                oid = run_git(self.repo, ["hash-object", "-w", "--stdin"], data=data).stdout.strip()
                records.extend(mode.encode() + b" " + oid + b"\t" + path.encode("utf-8", "surrogateescape") + b"\0")
            if records:
                run_git(self.repo, ["update-index", "-z", "--index-info"], data=bytes(records), env=env)
            tree = run_git(self.repo, ["write-tree"], env=env).stdout.decode().strip()
        message = f"MergeRisk: verified candidate merge\n\nStatic validation: {repair.validation}\nCoverage: {repair.analysis.status.value}\nPreview: {preview.fingerprint}\n"
        commit = run_git(self.repo, ["commit-tree", tree, "-p", scenario.left_commit, "-p", scenario.right_commit], data=message.encode()).stdout.decode().strip()
        ref = "refs/mergerisk/" + uuid.uuid4().hex
        run_git(self.repo, ["update-ref", ref, commit, "0" * len(commit)])
        parents = run_git(self.repo, ["rev-list", "--parents", "-n", "1", commit]).stdout.decode().split()
        actual_tree = run_git(self.repo, ["rev-parse", f"{commit}^{{tree}}"]).stdout.decode().strip()
        if parents != [commit, scenario.left_commit, scenario.right_commit] or actual_tree != tree:
            raise RuntimeError("Created commit identities do not match the approved candidate")
        return {"commit": commit, "tree": tree, "parents": parents[1:], "ref": ref,
                "next_steps": [f"git show {ref}", f"git merge --ff-only {ref}"], "applied": False}

    def apply(self, artifact: dict, *, expected_head: str):
        commit, ref = artifact["commit"], artifact["ref"]
        if not ref.startswith("refs/mergerisk/") or self.assembler.resolve_commit(ref) != commit:
            raise ValueError("Artifact reference is stale or unrecognized")
        branch = run_git(self.repo, ["symbolic-ref", "-q", "HEAD"], check=False)
        if branch.returncode:
            raise ValueError("Detached HEAD: check out the target branch before applying")
        current = self.assembler.resolve_commit("HEAD")
        parents = run_git(self.repo, ["rev-list", "--parents", "-n", "1", commit]).stdout.decode().split()
        if current != expected_head or len(parents) != 3 or parents[1] != expected_head:
            raise ValueError("HEAD must exactly match the analyzed left SHA")
        status = run_git(self.repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored"]).stdout
        if status:
            raise ValueError("Worktree/index must be clean, including untracked and ignored files")
        if any(mode not in {"100644", "100755"} for mode, _, _ in tree_entries(self.repo, commit).values()):
            raise ValueError("Applying symlink or submodule trees is unsupported")
        filters = run_git(self.repo, ["config", "--local", "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"], check=False)
        if filters.returncode == 0:
            raise ValueError("Configured external content filters prevent safe automatic checkout")
        # Git performs its checked fast-forward, index locking and ref compare-and-swap.
        run_git(self.repo, ["merge", "--ff-only", "--no-edit", "--no-verify", commit])
        if self.assembler.resolve_commit("HEAD") != commit or run_git(self.repo, ["symbolic-ref", "HEAD"]).stdout != branch.stdout:
            raise RuntimeError("Concurrent checkout change detected after fast-forward; inspect Git reflog")
        artifact["applied"] = True
        return artifact
