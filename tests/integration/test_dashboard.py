import json
from pathlib import Path
import re
import threading
import time

from fastapi.testclient import TestClient
import pytest

from mergerisk.dashboard import create_app
from mergerisk.git.plumbing import run_git
from mergerisk.sample import create_sample, FIXED
from mergerisk.service import MergeService


def session(client):
    page = client.get("/")
    assert page.status_code == 200
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
    return {"X-CSRF-Token": token}


def wait(client, id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        run = client.get("/api/runs/" + id).json()
        if run["state"] not in {"queued", "running", "cancelling", "validating"}:
            return run
        time.sleep(0.03)
    raise AssertionError("Analysis did not finish")


def expected(run):
    return {"expected": run["result"]["fingerprint"], "version": run["version"]}


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "sample repo ü"
    create_sample(repo)
    app = create_app(tmp_path / "state")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = session(client)
        response = client.post("/api/repositories", json={"path": str(repo)}, headers=headers)
        assert response.status_code == 201, response.text
        yield client, headers, response.json()["id"], repo, app


def start(client, headers, repo):
    response = client.post("/api/runs", json={"repo_id": repo, "left": "target", "right": "source"}, headers=headers)
    assert response.status_code == 202, response.text
    id = response.json()["id"]
    return id, wait(client, id)


def test_full_http_flow_commit_apply_export_and_persist(setup):
    client, headers, repo_id, repo, app = setup
    assert client.get(f"/api/repositories/{repo_id}/branches").json()["health"] == "ready"
    for path in ["/new?repo=" + repo_id, "/history", "/learn", "/settings", "/static/app.js", "/static/app.css"]:
        assert client.get(path).status_code == 200
    id, run = start(client, headers, repo_id)
    assert run["state"] == "complete", run
    assert run["result"]["validation"] == "static_verified"
    assert client.get("/runs/" + id).status_code == 200
    assert "import json" in client.get("/runs/" + id).text
    assert client.get(f"/api/runs/{id}/export").json()["result"]["fingerprint"] == run["result"]["fingerprint"]
    reviewed = client.post(f"/api/runs/{id}/review", json={**expected(run), "accepted": [], "rejected": []}, headers=headers)
    assert reviewed.status_code == 200, reviewed.text
    assert client.post(f"/api/runs/{id}/commit", json=expected(run), headers=headers).status_code == 409
    run = client.get(f"/api/runs/{id}").json()
    commit = client.post(f"/api/runs/{id}/commit", json=expected(run), headers=headers)
    assert commit.status_code == 200, commit.text
    artifact = commit.json()
    assert run_git(repo, ["rev-parse", "HEAD"]).stdout.decode().strip() == run["result"]["scenario"]["left_commit"]
    assert run_git(repo, ["show", artifact["commit"] + ":app.py"]).stdout == FIXED
    assert client.post(f"/api/runs/{id}/commit", json=expected(run), headers=headers).status_code == 409
    run = client.get(f"/api/runs/{id}").json()
    assert client.post(f"/api/runs/{id}/apply", json={**expected(run), "confirm": False}, headers=headers).status_code == 400
    applied = client.post(f"/api/runs/{id}/apply", json={**expected(run), "confirm": True}, headers=headers)
    assert applied.status_code == 200, applied.text
    assert (repo / "app.py").read_bytes() == FIXED
    assert len(app.state.history.run(id)["actions"]) == 3


def test_auth_csrf_origin_host_and_body_limits(setup):
    client, headers, repo_id, repo, app = setup
    assert client.post("/api/runs", json={}).status_code == 403
    assert client.post("/api/runs", json={}, headers={**headers, "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/repositories", content="x" * 17000, headers={**headers, "Content-Type": "application/json"}).status_code == 413
    assert client.post("/api/runs", content="x", headers=headers).status_code == 415
    client.cookies.clear()
    assert client.get("/api/repositories").status_code == 401


def test_unregistered_traversal_extra_fields_and_settings(setup):
    client, headers, repo_id, repo, app = setup
    assert client.get("/api/repositories/" + "0" * 32 + "/branches").status_code == 404
    response = client.post("/api/repositories", json={"path": str(repo / ".." / repo.name)}, headers=headers)
    assert response.status_code == 400
    assert client.post("/api/repositories", json={"path": str(repo), "execute": "evil"}, headers=headers).status_code == 422
    assert client.post(f"/api/repositories/{repo_id}/settings", json={"image": "python:latest", "command": ["python"]}, headers=headers).status_code == 400
    assert client.post(f"/api/repositories/{repo_id}/settings", json={"image": "", "command": [], "timeout": 20}, headers=headers).status_code == 200
    id, run = start(client, headers, repo_id)
    assert client.post(f"/api/runs/{id}/review", json={**expected(run), "accepted": ["stale"]}, headers=headers).status_code == 400
    assert client.post(f"/api/runs/{id}/verify", json=expected(run), headers=headers).status_code == 400
    assert client.post(f"/api/runs/{id}/delete", json=expected(run), headers=headers).status_code == 200
    assert client.get(f"/api/runs/{id}").status_code == 404


def test_source_xss_is_escaped(setup):
    client, headers, repo_id, repo, app = setup
    run_git(repo, ["checkout", "source"])
    with (repo / "app.py").open("ab") as stream:
        stream.write(b"\n# <script>alert('source')</script>\n")
    run_git(repo, ["add", "app.py"])
    run_git(repo, ["commit", "-m", "hostile source comment"])
    run_git(repo, ["checkout", "target"])
    id, run = start(client, headers, repo_id)
    response = client.get("/runs/" + id)
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_branch_movement_refuses_stale_commit(setup):
    client, headers, repo_id, repo, app = setup
    id, run = start(client, headers, repo_id)
    run_git(repo, ["commit", "--allow-empty", "-m", "target moved"])
    response = client.post(f"/api/runs/{id}/commit", json=expected(run), headers=headers)
    assert response.status_code == 409
    assert not run_git(repo, ["for-each-ref", "refs/mergerisk/"]).stdout


def test_bounded_jobs_and_cancellation(setup, monkeypatch):
    client, headers, repo_id, repo, app = setup
    entered = threading.Event()
    gate = threading.Event()

    def blocked(self, left, right, *, cancel, progress, **kwargs):
        entered.set()
        gate.wait(timeout=5)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        raise AssertionError("Expected cancellation")

    monkeypatch.setattr(MergeService, "preview", blocked)
    ids = []
    try:
        for _ in range(4):
            response = client.post("/api/runs", json={"repo_id": repo_id, "left": "target", "right": "source"}, headers=headers)
            assert response.status_code == 202
            ids.append(response.json()["id"])
        assert entered.wait(5)
        assert client.post("/api/runs", json={"repo_id": repo_id, "left": "target", "right": "source"}, headers=headers).status_code == 429
        for id in ids:
            assert client.post(f"/api/runs/{id}/cancel", json={}, headers=headers).status_code == 200
    finally:
        gate.set()
    for id in ids:
        assert wait(client, id)["state"] == "cancelled"


def test_history_survives_restart(setup):
    client, headers, repo_id, repo, app = setup
    id, run = start(client, headers, repo_id)
    restored = create_app(app.state.history.directory)
    with TestClient(restored, base_url="http://127.0.0.1") as second:
        session(second)
        assert second.get(f"/api/runs/{id}").json()["result"]["fingerprint"] == run["result"]["fingerprint"]
        assert second.get("/history").status_code == 200
