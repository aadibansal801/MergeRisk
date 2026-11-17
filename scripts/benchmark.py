"""Repeatable synthetic Git benchmark; Python heap peaks, not whole-process RSS."""
import argparse
import json
from pathlib import Path
import platform
import tempfile
import time
import tracemalloc

from mergerisk.analysis.pipeline import AnalysisOrchestrator
from mergerisk.git import GitScenarioAssembler, GitSnapshotReader
from mergerisk.git.plumbing import run_git
from mergerisk.sample import BASE, RIGHT, create_sample
from mergerisk.semantic.python_adapter import inspect_python, parse_python
from mergerisk.service import MergeService


def measure(call):
    inspect_python.cache_clear()
    parse_python.cache_clear()
    from mergerisk.rules.tier_a import _function_nodes
    if hasattr(_function_nodes, "cache_clear"):
        _function_nodes.cache_clear()
    tracemalloc.start()
    started = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {"seconds": round(elapsed, 4), "python_heap_peak_mib": round(peak / 1024**2, 3)}


def benchmark(sizes):
    rows = []
    for size in sizes:
        with tempfile.TemporaryDirectory(prefix="mergerisk-benchmark-") as temp:
            repo = Path(temp)
            revisions = create_sample(repo)
            run_git(repo, ["checkout", "-b", "benchmark-base", revisions["base"]])
            for i in range(size - 1):
                (repo / f"module_{i:04}.py").write_bytes(f"def helper_{i}(value=1):\n    return value\n".encode())
            run_git(repo, ["add", "."])
            run_git(repo, ["commit", "--allow-empty", "-m", "benchmark common files"])
            common = run_git(repo, ["rev-parse", "HEAD"]).stdout.decode().strip()
            run_git(repo, ["checkout", "-b", "benchmark-left"])
            (repo / "app.py").write_bytes(BASE.replace(b"import json\n", b""))
            run_git(repo, ["add", "."])
            run_git(repo, ["commit", "-m", "left"])
            run_git(repo, ["checkout", "-b", "benchmark-right", common])
            (repo / "app.py").write_bytes(RIGHT)
            run_git(repo, ["add", "."])
            run_git(repo, ["commit", "-m", "right"])
            scenario = GitScenarioAssembler(repo).assemble("benchmark-left", "benchmark-right")
            result, old = measure(lambda: AnalysisOrchestrator().analyze(GitSnapshotReader(repo), scenario))
            assert [f.rule_id for f in result.findings] == ["MR-PY-IMPORT-001"]
            preview, product = measure(lambda: MergeService(repo).preview("benchmark-left", "benchmark-right"))
            assert preview.repair.validation == "static_verified"
            rows.append({"python_files_per_revision": size, "snapshot_analysis": old, "product_preview": product})
            print(f"Measured {size} files: snapshot={old['seconds']}s product={product['seconds']}s", flush=True)
    return {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                             "git": run_git(Path.cwd(), ["--version"]).stdout.decode().strip()},
            "method": "One cold Python-cache sample per size; OS filesystem caches uncontrolled; includes tracemalloc overhead. Python heap peak excludes Git processes and OS buffers.",
            "measurements": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 50, 200])
    args = parser.parse_args()
    args.output.write_text(json.dumps(benchmark(args.sizes), indent=2) + "\n", encoding="utf-8")
