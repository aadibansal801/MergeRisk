from __future__ import annotations

from fastapi.testclient import TestClient

from mergerisk import hosted_admin
from mergerisk.hosted import create_app
from mergerisk.hosted_auth import GitHubAuth
from mergerisk.hosted_store import HostedStore


ORIGIN = "https://beta.example.test"
SUPER = ("hghai_be24@thapar.edu", "Qwer@1234")


def _setup(tmp_path):
    store = HostedStore(sqlite_path=tmp_path / "admin.sqlite3")
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    app = create_app(store=store, auth=auth, origin=ORIGIN)
    assert hosted_admin.AdminStore(store).ensure_super_admin(*SUPER)
    return store, app


def _sign_in(client, email, password):
    response = client.post("/admin/api/login", json={"email": email, "password": password}, headers={"Origin": ORIGIN})
    assert response.status_code == 204, response.text
    page = client.get("/admin")
    marker = 'name="csrf-token" content="'
    token = page.text.split(marker, 1)[1].split('"', 1)[0]
    return {"Origin": ORIGIN, "X-CSRF-Token": token}


def test_admin_routes_require_sign_in(tmp_path):
    _, app = _setup(tmp_path)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        assert client.get("/admin").headers["location"] == "/admin/login"
        assert client.get("/admin/login").status_code == 200
        for path in ("/admin/api/stats", "/admin/api/admins", "/admin/api/me", "/admin/api/activity"):
            assert client.get(path).status_code == 401


def test_login_rejects_bad_credentials_and_locks_out(tmp_path):
    _, app = _setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        origin = {"Origin": ORIGIN}
        assert client.post("/admin/api/login", json={"email": SUPER[0], "password": "x"}).status_code == 403
        for _ in range(5):
            assert client.post("/admin/api/login", json={"email": SUPER[0], "password": "wrong"},
                               headers=origin).status_code == 401
        # Even the right password is refused while locked out.
        assert client.post("/admin/api/login", json={"email": SUPER[0], "password": SUPER[1]},
                           headers=origin).status_code == 429
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post("/admin/api/login", json={"email": "nobody@example.com", "password": "Aa1!aaaa"},
                           headers={"Origin": ORIGIN}).status_code == 401


def test_super_admin_manages_admins_and_admin_cannot(tmp_path):
    store, app = _setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as boss:
        headers = _sign_in(boss, SUPER[0].upper(), SUPER[1])  # email is case-insensitive
        assert boss.get("/admin/api/me").json()["role"] == "super_admin"
        assert boss.post("/admin/api/admins", json={"email": "a@x.org", "password": "weak"},
                         headers=headers).status_code == 422
        assert boss.post("/admin/api/admins", json={"email": "a@x.org", "password": "Abcdef1!"}).status_code == 403
        created = boss.post("/admin/api/admins", json={"email": "A@x.org", "password": "Abcdef1!"}, headers=headers)
        assert created.status_code == 201
        assert boss.post("/admin/api/admins", json={"email": "a@x.org", "password": "Abcdef1!"},
                         headers=headers).status_code == 422
        admin_id = created.json()["id"]

        with TestClient(app, base_url=ORIGIN) as staff:
            staff_headers = _sign_in(staff, "a@x.org", "Abcdef1!")
            assert staff.get("/admin/api/stats").status_code == 200
            assert staff.get("/admin/api/admins").status_code == 403
            assert staff.post("/admin/api/admins", json={"email": "b@x.org", "password": "Abcdef1!"},
                              headers=staff_headers).status_code == 403
            # Wrong current password cannot change it; the right one can.
            assert staff.post("/admin/api/password", json={"current": "nope", "password": "Newpass1!"},
                              headers=staff_headers).status_code == 403
            assert staff.post("/admin/api/password", json={"current": "Abcdef1!", "password": "Newpass1!"},
                              headers=staff_headers).status_code == 204

            assert boss.delete(f"/admin/api/admins/{admin_id}", headers=headers).status_code == 204
            # Removal ends the existing session immediately.
            assert staff.get("/admin/api/stats").status_code == 401

        supers = [item for item in boss.get("/admin/api/admins").json() if item["role"] == "super_admin"]
        assert boss.delete(f"/admin/api/admins/{supers[0]['id']}", headers=headers).status_code == 404

        assert boss.post("/admin/api/logout", headers=headers).status_code == 204
        assert boss.get("/admin/api/me").status_code == 401


def test_seed_is_idempotent_and_keeps_password(tmp_path):
    store, _ = _setup(tmp_path)
    admins = hosted_admin.AdminStore(store)
    assert admins.ensure_super_admin(SUPER[0], "Different1!") is False
    assert hosted_admin.verify_password(SUPER[1], admins.by_email(SUPER[0])["password_hash"])


def test_usage_statistics_count_users_and_runs(tmp_path):
    store, app = _setup(tmp_path)
    store.register_account("1", "alice")
    store.register_account("2", "bob")
    store.register_account("3", "idle")
    for _ in range(2):
        store.record_event("1", "alice", "login")
    store.record_event("2", "bob", "login")
    store.record_event("1", "alice", "analysis", "octo/repo")
    store.record_event("1", "alice", "analysis", "octo/repo")
    store.record_event("2", "bob", "analysis", "octo/other")
    with TestClient(app, base_url=ORIGIN) as client:
        _sign_in(client, *SUPER)
        stats = client.get("/admin/api/stats?days=7").json()
        assert stats["totals"]["users"] == 3
        assert stats["totals"]["analyses"] == 3 and stats["totals"]["logins"] == 3
        assert stats["totals"]["active_users"] == 2
        users = {user["login"]: user for user in stats["users"]}
        assert (users["alice"]["logins"], users["alice"]["analyses"]) == (2, 2)
        assert (users["idle"]["logins"], users["idle"]["analyses"]) == (0, 0) and users["idle"]["last_active"] is None
        assert stats["repositories"][0] == {"repository": "octo/repo", "runs": 2, "users": 1}
        assert len(stats["series"]) == 7 and sum(day["analyses"] for day in stats["series"]) == 3
        assert len(client.get("/admin/api/activity").json()) == 6
        assert len(client.get("/admin/api/activity?github_id=2").json()) == 2
        assert client.get("/admin/api/stats?days=1000").status_code == 422


def test_portal_actions_are_recorded(tmp_path):
    store, app = _setup(tmp_path)
    auth = GitHubAuth("client", "secret", "x" * 48, ORIGIN)
    app = create_app(store=store, auth=auth, origin=ORIGIN, analyzer=lambda payload: {"error": "stub"})
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set(auth.session_cookie, auth._seal("session", {"id": "9", "login": "carol", "csrf": "tok"}, 600),
                           domain="beta.example.test")
        response = client.post("/api/jobs", json={"repository": "https://github.com/octo/repo", "target": "main",
                                                  "source": "dev"}, headers={"Origin": ORIGIN, "X-CSRF-Token": "tok"})
        assert response.status_code == 202, response.text
    events = hosted_admin.AdminStore(store).activity(10, "9")
    assert [(e["kind"], e["repository"]) for e in events] == [("analysis", "octo/repo")]


def test_admin_assets_are_served(tmp_path):
    _, app = _setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        for name in ("admin.js", "admin-login.js", "admin.css"):
            assert client.get(f"/assets/{name}").status_code == 200
