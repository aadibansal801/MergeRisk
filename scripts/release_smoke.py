"""Independent installed-wheel proof, including real HTTP routes and real Git repositories."""
import argparse
from importlib import metadata, resources
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

from fastapi.testclient import TestClient
import mergerisk
from mergerisk.dashboard import create_app
from mergerisk.git.plumbing import run_git
from mergerisk.sample import FIXED, create_sample


def smoke():
    installed = Path(mergerisk.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), "Smoke test must run from an independently installed wheel"
    assert resources.files("mergerisk").joinpath("templates/base.html").is_file()
    assert resources.files("mergerisk").joinpath("static/app.js").is_file()
    with tempfile.TemporaryDirectory(prefix="mergerisk-wheel-smoke-") as directory:
        root = Path(directory)
        safe, unsafe = root / "safe", root / "unsafe"
        revisions = create_sample(safe)
        create_sample(unsafe, unsafe=True)
        access_token = secrets.token_urlsafe(32)
        app = create_app(root / "state", access_token=access_token)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            response = client.get("/", params={"access": access_token})
            assert response.status_code == 200
            csrf = re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)
            headers = {"X-CSRF-Token": csrf}

            def analyze(repo):
                registered = client.post("/api/repositories", json={"path": str(repo)}, headers=headers)
                assert registered.status_code == 201, registered.text
                started = client.post("/api/runs", json={"repo_id": registered.json()["id"], "left": "target", "right": "source"}, headers=headers)
                assert started.status_code == 202, started.text
                id = started.json()["id"]
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    run = client.get("/api/runs/" + id).json()
                    if run["state"] not in {"queued", "running"}:
                        assert run["state"] == "complete", run
                        return id, run
                    time.sleep(0.03)
                raise AssertionError("Wheel analysis timed out")

            id, result = analyze(safe)
            assert client.get("/runs/" + id).status_code == 200
            assert result["result"]["validation"] == "static_verified"
            assert result["result"]["repairs"][0]["diff"].count("+import json") == 1
            expected = {"expected": result["result"]["fingerprint"], "version": result["version"]}
            created = client.post(f"/api/runs/{id}/commit", json=expected, headers=headers)
            assert created.status_code == 200, created.text
            artifact = created.json()
            assert artifact["parents"] == [revisions["left"], revisions["right"]]
            assert run_git(safe, ["rev-parse", artifact["commit"] + "^{tree}"]).stdout.decode().strip() == artifact["tree"]
            assert run_git(safe, ["show", artifact["commit"] + ":app.py"]).stdout == FIXED
            assert run_git(safe, ["rev-parse", "HEAD"]).stdout.decode().strip() == revisions["left"]
            updated = client.get(f"/api/runs/{id}").json()
            applied = client.post(f"/api/runs/{id}/apply",
                                  json={"expected": updated["result"]["fingerprint"], "version": updated["version"], "confirm": True}, headers=headers)
            assert applied.status_code == 200, applied.text
            artifact = applied.json()
            assert (safe / "app.py").read_bytes() == FIXED
            unsafe_id, refused = analyze(unsafe)
            refusal = client.post(f"/api/runs/{unsafe_id}/commit",
                                  json={"expected": refused["result"]["fingerprint"], "version": refused["version"]}, headers=headers)
            assert refusal.status_code == 400
            assert not run_git(unsafe, ["for-each-ref", "refs/mergerisk/"]).stdout
            assert client.get("/history").status_code == 200
        cli = subprocess.run([sys.executable, "-m", "mergerisk", "merge", "--repo", str(unsafe),
                              "--left", "target", "--right", "source", "--format", "json"],
                             capture_output=True, text=True, timeout=30)
        assert cli.returncode == 3, cli.stdout + cli.stderr
    return {"version": metadata.version("mergerisk"), "installed_package": str(installed),
            "bundled_assets": True, "actual_http_routes": True, "safe_artifact": artifact,
            "exact_repaired_bytes": True, "parent_and_tree_identity": True,
            "explicit_apply": True, "unsafe_commit_refused": True, "installed_cli_refusal_exit": cli.returncode}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(smoke(), indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
