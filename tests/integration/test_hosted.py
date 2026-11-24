from __future__ import annotations

import base64
import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from mergerisk import hosted_auth
from mergerisk.hosted import create_app
from mergerisk.hosted_auth import GitHubAuth
from mergerisk.hosted_store import HostedStore


ORIGIN = "https://beta.example.test"


def _as_user(client, auth, identifier, login):
    client.cookies.set(auth.session_cookie, auth._seal("session", {
        "id": identifier, "login": login, "csrf": "qa-csrf",
    }, 600), domain=urlsplit(ORIGIN).hostname)
    return {"Origin": ORIGIN, "X-CSRF-Token": "qa-csrf"}


def test_hosted_oauth_callback_and_invite(monkeypatch, tmp_path):
    auth = GitHubAuth("test-client", "test-secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "beta.sqlite3")
    app = create_app(store=store, auth=auth, origin=ORIGIN, allowed_users={"1"})
    monkeypatch.setattr(hosted_auth, "_github_json", lambda url, **kwargs: (
        {"access_token": "sample-token"} if url.endswith("access_token") else {"id": 1, "login": "alice"}
    ))

    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        home = client.get("/")
        assert "Sign in with GitHub" in home.text
        assert home.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in home.headers["Content-Security-Policy"]
        login = client.get("/auth/github")
        provider = urlsplit(login.headers["Location"])
        assert provider.hostname == "github.com"
        failed = client.get("/auth/github/callback", params={"code": "code", "state": "old-state"})
        assert failed.headers["Location"] == "/?login=failed"
        assert auth.state_cookie not in client.cookies

        login = client.get("/auth/github")
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        callback = client.get("/auth/github/callback", params={"code": "code", "state": state})
        assert callback.headers["Location"] == "/"
        assert "httponly" in callback.headers["Set-Cookie"].lower()
        assert "Analyze a merge" in client.get("/").text

    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as outsider:
        _as_user(outsider, auth, "3", "uninvited")
        assert outsider.get("/api/jobs").status_code == 401
        assert outsider.get("/").text.count("Sign in with GitHub") == 1


def test_hosted_queue_report_download_and_two_account_ownership(tmp_path):
    sample_patch = b"diff --git a/app.py b/app.py\n"
    auth = GitHubAuth("test-client", "test-secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "beta.sqlite3")
    app = create_app(store=store, auth=auth, origin=ORIGIN, allowed_users={"1", "2"}, analyzer=lambda data: {
        "result": {"repository": data["repository"], "status": "findings_present", "validation": "static_verified",
                   "patch_b64": base64.b64encode(sample_patch).decode("ascii"), "findings": []},
    })
    payload = {"repository": "https://github.com/example/repository", "target": "main", "source": "feature"}
    with TestClient(app, base_url=ORIGIN) as first:
        assert first.get("/api/jobs").status_code == 401
        headers = _as_user(first, auth, "1", "alice")
        assert first.post("/api/jobs", json=payload).status_code == 403
        assert first.post("/api/jobs", json={**payload, "source": "main"}, headers=headers).status_code == 422
        queued = first.post("/api/jobs", json=payload, headers=headers)
        assert queued.status_code == 202, queued.text
        path = f"/api/jobs/{queued.json()['id']}"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = first.get(path).json()
            if detail["state"] == "complete":
                break
            time.sleep(0.02)
        assert detail["state"] == "complete", detail
        assert detail["has_patch"]
        assert "patch_b64" not in detail["result"]
        assert first.get(path + "/patch").content == sample_patch

        second = TestClient(app, base_url=ORIGIN)
        other_headers = _as_user(second, auth, "2", "bob")
        assert second.get("/api/jobs").json() == []
        assert second.get(path).status_code == 404
        assert second.get(path + "/patch").status_code == 404
        assert second.delete(path, headers=other_headers).status_code == 404
        assert first.delete(path, headers=headers).status_code == 204
        assert first.get(path).status_code == 404
        assert first.post("/auth/logout", headers=headers).status_code == 204
        assert first.get("/api/jobs").status_code == 401
