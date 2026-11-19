"""Release-only TCP verification against the separately started installed dashboard."""
import hashlib
import json
from pathlib import Path
import re
import time

import httpx
from mergerisk.git.plumbing import run_git
from mergerisk.sample import create_sample, FIXED

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "run.json").read_text())
WORK = Path(CONFIG["work"]) / "http-repositories"
WORK.mkdir()
BASE_URL = "http://127.0.0.1:18765"
events = []
summary = {"passed": False, "base_url": BASE_URL}


def snapshot(repo):
    return {
        "head": run_git(repo, ["rev-parse", "HEAD"]).stdout.decode().strip(),
        "refs": run_git(repo, ["show-ref"]).stdout.decode(),
        "index": hashlib.sha256((repo / ".git/index").read_bytes()).hexdigest(),
        "source": hashlib.sha256((repo / "app.py").read_bytes()).hexdigest(),
        "config": hashlib.sha256((repo / ".git/config").read_bytes()).hexdigest(),
    }


try:
    with httpx.Client(base_url=BASE_URL, timeout=35) as client:
        def request(method, path, expected=200, **kwargs):
            start = time.perf_counter()
            response = client.request(method, path, **kwargs)
            events.append({"method": method, "path": path, "status": response.status_code,
                           "seconds": round(time.perf_counter() - start, 4)})
            assert response.status_code == expected, (method, path, response.status_code, response.text[:1000])
            return response

        home = request("GET", "/")
        csrf = re.search(r'name="csrf-token" content="([^"]+)"', home.text).group(1)
        headers = {"X-CSRF-Token": csrf}
        request("POST", "/api/runs", 403, json={})
        request("POST", "/api/runs", 403, json={}, headers={**headers, "Origin": "https://evil.example"})
        request("GET", "/", 400, headers={"Host": "evil.example"})
        request("POST", "/api/repositories", 413, content="x" * 17000,
                headers={**headers, "Content-Type": "application/json"})
        with httpx.Client(base_url=BASE_URL, timeout=5) as unauthenticated:
            assert unauthenticated.get("/api/repositories").status_code == 401

        safe, unsafe = WORK / "safe", WORK / "unsafe"
        revisions = create_sample(safe)
        create_sample(unsafe, unsafe=True)
        run_git(unsafe, ["checkout", "source"])
        with (unsafe / "app.py").open("ab") as stream:
            stream.write(b"\n# <script>window.release_probe=1</script>\n")
        run_git(unsafe, ["add", "app.py"])
        run_git(unsafe, ["commit", "-m", "known-safe escaping fixture"])
        run_git(unsafe, ["checkout", "target"])

        def register(repo):
            return request("POST", "/api/repositories", 201, json={"path": str(repo)}, headers=headers).json()["id"]

        safe_id, unsafe_id = register(safe), register(unsafe)
        request("GET", "/api/repositories/" + "0" * 32 + "/branches", 404)
        request("POST", "/api/repositories", 400,
                json={"path": str(safe / ".." / safe.name)}, headers=headers)
        for path in ("/", "/new?repo=" + safe_id, "/history", "/learn", "/settings", "/static/app.js", "/static/app.css"):
            request("GET", path)
        branches = request("GET", f"/api/repositories/{safe_id}/branches").json()
        assert {b["name"] for b in branches["branches"]} == {"target", "source"}

        def wait(id):
            deadline = time.monotonic() + 30
            states = []
            while time.monotonic() < deadline:
                run = request("GET", "/api/runs/" + id).json()
                if not states or states[-1] != run["state"]:
                    states.append(run["state"])
                if run["state"] not in {"queued", "running", "cancelling", "validating"}:
                    return run, states
                time.sleep(0.05)
            raise AssertionError("Live HTTP job timed out")

        def start(repo_id, left="target", right="source"):
            id = request("POST", "/api/runs", 202, json={"repo_id": repo_id, "left": left, "right": right},
                         headers=headers).json()["id"]
            run, states = wait(id)
            assert run["state"] == "complete", run
            return id, run, states

        def expected(run):
            return {"expected": run["result"]["fingerprint"], "version": run["version"]}

        before = snapshot(safe)
        id, run, states = start(safe_id)
        assert snapshot(safe) == before, "Analysis changed refs/index/source/config"
        result = run["result"]
        assert result["validation"] == "static_verified"
        assert [f["rule_id"] for f in result["analysis"]["findings"]] == ["MR-PY-IMPORT-001"]
        assert result["repairs"][0]["edits"] == [{"start": 0, "end": 0, "before": "", "after": "import json\n"}]
        assert result["files"]["app.py"]["fixed"].encode() == FIXED
        request("GET", "/runs/" + id)
        request("POST", f"/api/runs/{id}/review", json={**expected(run), "accepted": [], "rejected": []}, headers=headers)
        request("POST", f"/api/runs/{id}/commit", 409, json=expected(run), headers=headers)
        run = request("GET", f"/api/runs/{id}").json()
        artifact = request("POST", f"/api/runs/{id}/commit", json=expected(run), headers=headers).json()
        after_commit = snapshot(safe)
        assert {k:v for k,v in before.items() if k != "refs"} == {k:v for k,v in after_commit.items() if k != "refs"}
        assert artifact["parents"] == [revisions["left"], revisions["right"]]
        assert run_git(safe, ["show", artifact["commit"] + ":app.py"]).stdout == FIXED
        assert run_git(safe, ["rev-parse", artifact["commit"] + "^{tree}"]).stdout.decode().strip() == artifact["tree"]
        run = request("GET", f"/api/runs/{id}").json()
        sentinel = safe / "unique work.txt"
        sentinel.write_bytes(b"verification-owned untracked bytes")
        request("POST", f"/api/runs/{id}/apply", 400, json={**expected(run), "confirm": True}, headers=headers)
        assert snapshot(safe) == after_commit and sentinel.read_bytes() == b"verification-owned untracked bytes"
        sentinel.unlink()  # Only this known synthetic test file is removed.
        artifact = request("POST", f"/api/runs/{id}/apply",
                           json={**expected(run), "confirm": True}, headers=headers).json()
        assert artifact["applied"] and (safe / "app.py").read_bytes() == FIXED
        assert snapshot(safe)["head"] == artifact["commit"]
        exported = request("GET", f"/api/runs/{id}/export").json()
        assert exported["result"]["artifact"]["applied"]

        unsafe_before = snapshot(unsafe)
        unsafe_run, refused, _ = start(unsafe_id)
        request("POST", f"/api/runs/{unsafe_run}/commit", 400, json=expected(refused), headers=headers)
        assert snapshot(unsafe) == unsafe_before
        assert refused["result"]["files"]["app.py"]["fixed"] == refused["result"]["files"]["app.py"]["merge"]
        assert not any(p["tier"] == "AUTO" for p in refused["result"]["repairs"])
        escaped = request("GET", "/runs/" + unsafe_run).text
        assert "<script>window.release_probe" not in escaped and "&lt;script&gt;window.release_probe" in escaped
        request("POST", f"/api/repositories/{unsafe_id}/settings",
                json={"image": "sha256:" + "a"*64, "command": ["python", "-m", "pytest"], "timeout": 1}, headers=headers)
        unavailable = request("POST", f"/api/runs/{unsafe_run}/verify", json=expected(refused), headers=headers).json()
        assert unavailable["status"] == "validation_unavailable"
        request("POST", f"/api/repositories/{unsafe_id}/settings",
                json={"image": "", "command": [], "timeout": 30}, headers=headers)

        cancelled_id = request("POST", "/api/runs", 202,
                               json={"repo_id": safe_id, "left": "target", "right": "source"}, headers=headers).json()["id"]
        request("POST", f"/api/runs/{cancelled_id}/cancel", json={}, headers=headers)
        cancelled, _ = wait(cancelled_id)
        assert cancelled["state"] == "cancelled"
        request("POST", f"/api/runs/{cancelled_id}/delete",
                json={"expected": hashlib.sha256(cancelled_id.encode()).hexdigest(), "version": cancelled["version"]}, headers=headers)
        request("GET", f"/api/runs/{cancelled_id}", 404)

        # A real suggestion requires review; keep exact expression/comment bytes.
        rename = WORK / "rename"
        create_sample(rename)
        baseline = b"def old_name(x):\n return x\n\n# unchanged context\n\n# extra functions\n"
        (rename / "app.py").write_bytes(baseline)
        run_git(rename, ["add", "app.py"]); run_git(rename, ["commit", "-m", "rename baseline"])
        base = run_git(rename, ["rev-parse", "HEAD"]).stdout.decode().strip()
        run_git(rename, ["checkout", "-b", "review-target"])
        (rename / "app.py").write_bytes(baseline.replace(b"old_name", b"new_name"))
        run_git(rename, ["add", "app.py"]); run_git(rename, ["commit", "-m", "rename"])
        run_git(rename, ["checkout", "-b", "review-source", base])
        (rename / "app.py").write_bytes(baseline + b"\ndef caller():\n return old_name( 1 +  2 ) # keep\n")
        run_git(rename, ["add", "app.py"]); run_git(rename, ["commit", "-m", "caller"])
        run_git(rename, ["checkout", "review-target"])
        rename_id = register(rename)
        review_id, review, _ = start(rename_id, "review-target", "review-source")
        plan = next(p for p in review["result"]["repairs"] if p["tier"] == "SUGGEST")
        request("POST", f"/api/runs/{review_id}/review",
                json={**expected(review), "accepted": [], "rejected": [plan["id"]]}, headers=headers)
        review = request("GET", f"/api/runs/{review_id}").json()
        request("POST", f"/api/runs/{review_id}/commit", 400, json=expected(review), headers=headers)
        request("POST", f"/api/runs/{review_id}/review",
                json={**expected(review), "accepted": [plan["id"]], "rejected": []}, headers=headers)
        accepted = request("GET", f"/api/runs/{review_id}").json()
        assert not accepted["result"]["fixed_analysis"]["findings"]
        assert "return new_name( 1 +  2 ) # keep" in accepted["result"]["files"]["app.py"]["fixed"]
        assert (rename / "app.py").read_bytes() == baseline.replace(b"old_name", b"new_name")
        request("GET", "/history")
        summary.update(passed=True, safe_run=id, unsafe_run=unsafe_run, suggestion_run=review_id,
                       progress_states=states, artifact=artifact, read_only_snapshot_equal=True,
                       commit_checkout_unchanged=True, dirty_apply_preserved_bytes=True,
                       unsafe_fix_refused=True, suggestions_rejected_then_explicitly_accepted=True,
                       csrf_origin_host_auth_xss_traversal_limits=True, cancellation=True,
                       runtime_unavailable=unavailable["reason"], requests=len(events))
finally:
    (HERE / "live-http.json").write_text(json.dumps({"summary": summary, "requests": events}, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
