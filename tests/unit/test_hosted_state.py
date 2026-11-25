from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.cookies import SimpleCookie
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.requests import Request
from starlette.responses import Response

from mergerisk import hosted_auth, hosted_store


def test_owner_access_and_expired_lease_across_restart(tmp_path, monkeypatch):
    now = 100_000.0
    monkeypatch.setattr(hosted_store, "time", SimpleNamespace(time=lambda: now))
    database = tmp_path / "hosted.sqlite3"
    store = hosted_store.HostedStore(sqlite_path=database)
    running = store.submit("101", {"repository": "https://github.com/example/fixture"})
    now += 1
    queued = store.submit("102", {"repository": "https://github.com/example/fixture"})
    lease = store.claim()
    assert lease["id"] == running["id"]
    assert store.get("102", running["id"]) is None
    assert [job["id"] for job in store.list("102")] == [queued["id"]]
    assert not store.delete("102", running["id"])
    assert "lease_token" not in store.get("101", running["id"])

    restarted = hosted_store.HostedStore(sqlite_path=database)
    assert restarted.claim() is None
    now += 91
    assert not store.finish(running["id"], lease["lease_token"], result={"stale": True})
    next_job = restarted.claim()
    assert next_job["id"] == queued["id"]
    assert restarted.get("101", running["id"])["state"] == "error"
    assert restarted.finish(queued["id"], next_job["lease_token"], result={"verified": True})
    assert store.get("102", queued["id"])["result"] == {"verified": True}
    assert not store.delete("101", queued["id"])
    assert store.delete("102", queued["id"])

    now += 86_401
    assert restarted.claim() is None and restarted.list("101") == []


def test_global_queue_and_lease_limits_serialize_across_connections(tmp_path):
    database = tmp_path / "hosted.sqlite3"
    stores = [hosted_store.HostedStore(sqlite_path=database) for _ in range(2)]

    def submit(index):
        try:
            return stores[index % 2].submit(str(index), {"fixture": index})
        except OverflowError:
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        accepted = [job for job in workers.map(submit, range(8)) if job is not None]
        claimed = [job for job in workers.map(lambda store: store.claim(), stores) if job is not None]
    assert len(accepted) == 4
    assert len(claimed) == 1


def _request(cookie="", origin="", csrf=""):
    return Request({"type": "http", "headers": [
        (b"cookie", cookie.encode()),
        (b"origin", origin.encode()),
        (b"x-csrf-token", csrf.encode()),
    ]})


def _cookie_value(response, name):
    cookie = SimpleCookie()
    for line in response.headers.getlist("Set-Cookie"):
        cookie.load(line)
    return cookie[name].value


def test_oauth_state_pkce_and_per_session_csrf(monkeypatch):
    now = 100_000.0
    monkeypatch.setattr(hosted_auth, "time", SimpleNamespace(time=lambda: now))
    provider_requests = []

    def provider(url, *, data=None, token=None):
        provider_requests.append((url, data, token))
        if data:
            return {"access_token": "example_provider_token"}
        return {"id": 101, "login": "example-user"}

    monkeypatch.setattr(hosted_auth, "_github_json", provider)
    origin = "https://example.test"
    auth = hosted_auth.GitHubAuth("client", "oauth-secret", "session-secret-for-this-test-only", origin)
    start = Response()
    parameters = parse_qs(urlsplit(auth.start(start)).query, keep_blank_values=True)
    assert parameters["code_challenge_method"] == ["S256"]
    assert parameters["redirect_uri"] == [origin + "/auth/github/callback"]
    assert parameters["scope"] == [""]
    assert "Secure" in start.headers["Set-Cookie"] and "HttpOnly" in start.headers["Set-Cookie"]
    pending = f"{auth.state_cookie}={_cookie_value(start, auth.state_cookie)}"
    with pytest.raises(ValueError, match="did not match"):
        auth.callback(_request(pending), Response(), "code", "incorrect-state")
    assert not provider_requests

    callback = Response()
    user = auth.callback(_request(pending), callback, "code", parameters["state"][0])
    assert auth.session_cookie not in str(callback.headers)
    auth.start_session(callback, user)
    verifier = provider_requests[0][1]["code_verifier"]
    assert hosted_auth._b64(sha256(verifier.encode()).digest()) == parameters["code_challenge"][0]
    assert provider_requests[1] == ("https://api.github.com/user", None, "example_provider_token")
    session = _cookie_value(callback, auth.session_cookie)
    assert any(line.startswith(auth.state_cookie + "=") and "Max-Age=0" in line
               for line in callback.headers.getlist("Set-Cookie"))
    assert "example_provider_token" not in str(callback.headers)
    signed_in = f"{auth.session_cookie}={session}"
    parsed_session = auth.session(_request(signed_in))
    assert user.id == "101" and parsed_session.user == user
    assert parsed_session.token_hash == sha256(session.encode("ascii")).hexdigest()
    assert parsed_session.expires == now + 8 * 3600
    auth.require_csrf(_request(signed_in, origin, user.csrf), user)
    with pytest.raises(ValueError, match="origin or CSRF"):
        auth.require_csrf(_request(signed_in, "https://other.test", user.csrf), user)
    with pytest.raises(ValueError, match="origin or CSRF"):
        auth.require_csrf(_request(signed_in, origin, "other-session"), user)

    monkeypatch.setattr(hosted_auth, "_github_json", lambda *args, **kwargs: {
        "error": "invalid_code", "error_description": "private provider detail",
    })
    failed = Response()
    with pytest.raises(ValueError, match="GitHub rejected the sign-in code") as error:
        auth.callback(_request(pending), failed, "code", parameters["state"][0])
    assert "private provider detail" not in str(error.value)
    assert auth.session_cookie not in str(failed.headers)
    now += 28_801
    assert auth.session(_request(signed_in)) is None
