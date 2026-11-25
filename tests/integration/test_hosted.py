from __future__ import annotations

import base64
from types import SimpleNamespace
import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from mergerisk import hosted_auth
from mergerisk.hosted import create_app
from mergerisk.hosted_auth import GitHubAuth
from mergerisk.hosted_store import HostedStore
from mergerisk import hosted_store


ORIGIN = "https://beta.example.test"


def test_idle_hosted_worker_physically_removes_expired_reports(tmp_path, monkeypatch):
    now = 100_000
    monkeypatch.setattr(hosted_store, "time", SimpleNamespace(time=lambda: now))
    monkeypatch.setattr("mergerisk.hosted._MAINTENANCE_SECONDS", 0.02)
    store = HostedStore(sqlite_path=tmp_path / "idle.sqlite3")
    store.submit("1", {"repository": "example/sample"})
    job = store.claim()
    assert store.finish(job["id"], job["lease_token"], result={"message": "synthetic report"})
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN):
        now += hosted_store._RETENTION + 1
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with store._connect() as db:
                if db.execute("SELECT COUNT(*) FROM hosted_jobs").fetchone()[0] == 0:
                    break
            time.sleep(0.02)
        else:
            raise AssertionError("Expired row remained in the database without incoming requests")


def _as_user(client, auth, identifier, login):
    client.cookies.set(auth.session_cookie, auth._seal("session", {
        "id": identifier, "login": login, "csrf": "qa-csrf",
    }, 600), domain=urlsplit(ORIGIN).hostname)
    return {"Origin": ORIGIN, "X-CSRF-Token": "qa-csrf"}


def test_hosted_oauth_signs_up_and_reuses_account_for_same_github_id(monkeypatch, tmp_path):
    auth = GitHubAuth("test-client", "test-secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "beta.sqlite3")
    for name, value in {
        "ORIGIN": ORIGIN, "DATABASE_URL": "test-store", "GITHUB_CLIENT_ID": "test-client",
        "GITHUB_CLIENT_SECRET": "test-secret", "SESSION_SECRET": "x" * 48,
    }.items():
        monkeypatch.setenv(f"MERGERISK_{name}", value)
    monkeypatch.delenv("MERGERISK_BETA_GITHUB_IDS", raising=False)
    monkeypatch.setattr("mergerisk.hosted.HostedStore", lambda url: store)
    app = create_app(analyzer=lambda _: {"result": {"status": "no_supported_findings"}})
    profile = {"id": 42, "login": "first-login"}
    monkeypatch.setattr(hosted_auth, "_github_json", lambda url, **kwargs: (
        {"access_token": "sample-token"} if url.endswith("access_token") else dict(profile)
    ))

    def oauth_callback(client):
        login = client.get("/auth/github")
        state = parse_qs(urlsplit(login.headers["Location"]).query)["state"][0]
        return client.get("/auth/github/callback", params={"code": "code", "state": state})

    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        home = client.get("/")
        assert "Sign in with GitHub" in home.text
        assert "first sign-in creates a free MergeRisk account" in home.text
        assert home.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in home.headers["Content-Security-Policy"]
        login = client.get("/auth/github")
        provider = urlsplit(login.headers["Location"])
        assert provider.hostname == "github.com"
        failed = client.get("/auth/github/callback", params={"code": "code", "state": "old-state"})
        assert failed.headers["Location"] == "/?login=failed"
        assert auth.state_cookie not in client.cookies
        with store._connect() as db:
            assert db.execute("SELECT COUNT(*) FROM hosted_accounts").fetchone()[0] == 0

        callback = oauth_callback(client)
        assert callback.headers["Location"] == "/"
        assert "httponly" in callback.headers["Set-Cookie"].lower()
        assert "Analyze a merge" in client.get("/").text
        with store._connect() as db:
            account = tuple(db.execute("SELECT github_id, login, created FROM hosted_accounts").fetchone())
        assert account[:2] == ("42", "first-login")

        session = auth._open("session", client.cookies[auth.session_cookie])
        queued = client.post("/api/jobs", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf"]}, json={
            "repository": "https://github.com/example/repository", "target": "main", "source": "feature",
        })
        assert queued.status_code == 202
        report_path = f"/api/jobs/{queued.json()['id']}"

        client.cookies.clear()
        profile["login"] = "renamed-login"
        assert oauth_callback(client).headers["Location"] == "/"
        assert "renamed-login" in client.get("/").text
        assert client.get(report_path).status_code == 200
        with store._connect() as db:
            assert [tuple(row) for row in db.execute("SELECT github_id, login, created FROM hosted_accounts")] == [
                ("42", "renamed-login", account[2]),
            ]

        # A provider-verified identity gets a session only after the account is saved.
        client.cookies.clear()
        with monkeypatch.context() as failing:
            def unavailable(*args):
                raise OSError("test storage failure")

            failing.setattr(store, "register_account", unavailable)
            assert oauth_callback(client).headers["Location"] == "/?login=failed"
            assert client.get("/api/jobs").status_code == 401


def test_hosted_queue_report_download_and_two_account_ownership(tmp_path):
    sample_patch = b"diff --git a/app.py b/app.py\n"
    auth = GitHubAuth("test-client", "test-secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "beta.sqlite3")
    app = create_app(store=store, auth=auth, origin=ORIGIN, analyzer=lambda data: {
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
