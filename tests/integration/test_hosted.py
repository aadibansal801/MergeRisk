from __future__ import annotations

import base64
from types import SimpleNamespace
import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from mergerisk import hosted_auth, hosted_catalog
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


def test_idle_worker_removes_only_expired_session_revocations(tmp_path, monkeypatch):
    now = 100_000
    monkeypatch.setattr(hosted_store, "time", SimpleNamespace(time=lambda: now))
    monkeypatch.setattr("mergerisk.hosted._MAINTENANCE_SECONDS", 0.02)
    store = HostedStore(sqlite_path=tmp_path / "revocations.sqlite3")
    store.revoke_session("expired-test-hash", now - 1)
    store.revoke_session("active-test-hash", now + 300)
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and store.is_session_revoked("expired-test-hash"):
            time.sleep(0.02)
        assert not store.is_session_revoked("expired-test-hash")
        assert store.is_session_revoked("active-test-hash")


def _as_user(client, auth, identifier, login, *, csrf="qa-csrf"):
    client.cookies.set(auth.session_cookie, auth._seal("session", {
        "id": identifier, "login": login, "csrf": csrf,
    }, 600), domain=urlsplit(ORIGIN).hostname)
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def test_logout_revocation_persists_and_is_per_session(tmp_path):
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    database = tmp_path / "revocations.sqlite3"
    store = HostedStore(sqlite_path=database)
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as first:
        other = TestClient(app, base_url=ORIGIN)
        _as_user(other, auth, "42", "alice", csrf="other-browser")
        headers = _as_user(first, auth, "42", "alice", csrf="first-browser")
        issued_session = first.cookies[auth.session_cookie]
        assert first.get("/api/jobs").status_code == 200
        assert first.post("/auth/logout").status_code == 403
        assert first.post("/auth/logout", headers=headers).status_code == 204
        assert auth.session_cookie not in first.cookies
        assert other.get("/api/jobs").status_code == 200
        other.close()

    reopened_store = HostedStore(sqlite_path=database)
    restarted = create_app(store=reopened_store, auth=auth, origin=ORIGIN)
    with TestClient(restarted, base_url=ORIGIN) as client:
        client.cookies.set(auth.session_cookie, issued_session, domain=urlsplit(ORIGIN).hostname)
        assert client.get("/api/jobs").status_code == 401
        assert "Sign in with GitHub" in client.get("/").text


def test_session_database_errors_do_not_authorize_requests_or_confirm_logout(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError("test storage failure")

    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "revocations.sqlite3")
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = _as_user(client, auth, "42", "alice")
        with monkeypatch.context() as failure:
            failure.setattr(store, "is_session_revoked", unavailable)
            assert client.get("/api/jobs").status_code == 503
        with monkeypatch.context() as failure:
            failure.setattr(store, "revoke_session", unavailable)
            assert client.post("/auth/logout", headers=headers).status_code == 503
            assert auth.session_cookie in client.cookies
        assert client.post("/auth/logout", headers=headers).status_code == 204


def test_catalog_uses_the_signed_in_login_and_lists_only_supported_public_refs(tmp_path, monkeypatch):
    lookups = []

    def provider_page(resource, page, cache_window):
        lookups.append((resource, page))
        if resource == "users/alice/repos":
            return [
                {"full_name": "Alice/Example", "private": False, "default_branch": "main"},
                {"full_name": "alice/hidden", "private": True},
            ], True
        if resource == "repos/a-team/project/branches":
            return [{"name": "main"}, {"name": "feature/cleanup"}, {"name": "main~1"}], False
        raise hosted_catalog.CatalogError("GitHub is limiting repository lookups. Try again shortly.")

    monkeypatch.setattr(hosted_catalog, "_fetch_page", provider_page)
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    store = HostedStore(sqlite_path=tmp_path / "catalog.sqlite3")
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/github/repositories").status_code == 401
        assert client.get("/api/github/branches", params={"repository": "https://github.com/a-team/project"}).status_code == 401
        _as_user(client, auth, "42", "alice")
        result = client.get("/api/github/repositories", params={"page": 2}).json()
        assert result == {"items": [{"name": "alice/example", "url": "https://github.com/alice/example",
                                    "default_branch": "main"}], "has_more": True}
        result = client.get("/api/github/branches", params={"repository": "https://github.com/A-Team/Project/"}).json()
        assert result == {"repository": "https://github.com/a-team/project",
                          "items": ["main", "feature/cleanup"], "has_more": False}
        assert client.get("/api/github/branches", params={"repository": "https://example.test/team/project"}).status_code == 422
        assert lookups == [("users/alice/repos", 2), ("repos/a-team/project/branches", 1)]
        unavailable = client.get("/api/github/branches", params={"repository": "https://github.com/a-team/other"})
        assert unavailable.status_code == 502
        assert "limiting repository lookups" in unavailable.json()["detail"]


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
