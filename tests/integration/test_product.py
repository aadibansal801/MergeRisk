from mergerisk.git import GitScenarioAssembler, GitSnapshotReader
from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.sample import create_sample


def test_real_clean_git_merge_with_missing_import(tmp_path):
    revisions = create_sample(tmp_path)
    assembler = GitScenarioAssembler(tmp_path)
    before = assembler._run_git(["status", "--porcelain"]).stdout
    scenario = assembler.assemble("target", "source")
    assert scenario.is_clean
    result = AnalysisOrchestrator().analyze(GitSnapshotReader(tmp_path), scenario)
    assert [f.rule_id for f in result.findings] == ["MR-PY-IMPORT-001"]
    assert result.findings[0].revision_context.left == revisions["left"]
    assert assembler._run_git(["status", "--porcelain"]).stdout == before
    assert assembler.resolve_commit("HEAD") == revisions["left"]
