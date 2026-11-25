"""GitHub sign-in and signed, same-origin sessions for the hosted dashboard."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from starlette.requests import Request as BrowserRequest
from starlette.responses import Response


_AUTHORIZATION = "https://github.com/login/oauth/authorize"
_TOKEN = "https://github.com/login/oauth/access_token"
_PROFILE = "https://api.github.com/user"
_CALLBACK = "/auth/github/callback"
_STATE_AGE = 600
_SESSION_AGE = 8 * 3600
_GITHUB_REPLY_LIMIT = 128 * 1024
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _github_json(url: str, *, data: dict | None = None, token: str | None = None) -> dict:
    headers = {"Accept": "application/json", "User-Agent": "MergeRisk-Hosted"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, data=urlencode(data).encode("ascii") if data is not None else None)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=8) as response:
            payload = response.read(_GITHUB_REPLY_LIMIT + 1)
        if len(payload) > _GITHUB_REPLY_LIMIT:
            raise ValueError("GitHub response too large")
        parsed = json.loads(payload)
    except (URLError, OSError, ValueError) as error:
        raise ValueError("GitHub sign-in is unavailable. Try again shortly.") from error
    if not isinstance(parsed, dict):
        raise ValueError("GitHub returned an invalid sign-in response.")
    return parsed


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class User:
    id: str
    login: str
    csrf: str


class GitHubAuth:
    def __init__(self, client_id: str, client_secret: str, session_secret: str, origin: str, *, secure: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.key = session_secret.encode("utf-8")
        if len(self.key) < 32:
            raise ValueError("Hosted sign-in requires a session secret of at least 32 bytes.")
        self.origin = origin.rstrip("/")
        self.callback_url = self.origin + _CALLBACK
        self.secure = secure
        prefix = "__Host-" if self.secure else ""
        self.session_cookie = f"{prefix}mergerisk_hosted_session"
        self.state_cookie = f"{prefix}mergerisk_hosted_oauth"

    def _sign(self, purpose: str, payload: str) -> str:
        message = f"{purpose}.{payload}".encode("ascii")
        return _b64(hmac.digest(self.key, message, "sha256"))

    def _seal(self, purpose: str, document: dict, max_age: int) -> str:
        payload = _b64(json.dumps({**document, "exp": int(time.time()) + max_age}, separators=(",", ":")).encode("ascii"))
        return f"{payload}.{self._sign(purpose, payload)}"

    def _open(self, purpose: str, value: str) -> dict | None:
        if len(value) > 2048:
            return None
        payload, _, signature = value.partition(".")
        if not _BASE64URL.fullmatch(payload) or not _BASE64URL.fullmatch(signature):
            return None
        if not hmac.compare_digest(signature, self._sign(purpose, payload)):
            return None
        try:
            document = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            if isinstance(document, dict) and document.get("exp", 0) > time.time():
                return document
        except (UnicodeError, ValueError, TypeError):
            return None
        return None

    def _set_cookie(self, response: Response, key: str, value: str, max_age: int) -> None:
        response.set_cookie(key, value, max_age=max_age, path="/", secure=self.secure, httponly=True, samesite="lax")

    def _clear_cookie(self, response: Response, key: str) -> None:
        response.delete_cookie(key, path="/", secure=self.secure, httponly=True, samesite="lax")

    def start(self, response: Response) -> str:
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        pending = self._seal("oauth", {"state": state, "verifier": verifier}, _STATE_AGE)
        self._set_cookie(response, self.state_cookie, pending, _STATE_AGE)
        return _AUTHORIZATION + "?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "scope": "",
            "state": state,
            "code_challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest()),
            "code_challenge_method": "S256",
        })

    def callback(self, request: BrowserRequest, response: Response, code: str, state: str) -> User:
        self._clear_cookie(response, self.state_cookie)
        pending = self._open("oauth", request.cookies.get(self.state_cookie, ""))
        if not pending or not _BASE64URL.fullmatch(state) or not hmac.compare_digest(state, pending["state"]):
            raise ValueError("GitHub sign-in expired or did not match this browser. Start again.")
        if not code or len(code) > 256 or not _BASE64URL.fullmatch(code):
            raise ValueError("GitHub sign-in did not return a valid code. Start again.")
        credentials = _github_json(_TOKEN, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.callback_url,
            "code": code,
            "code_verifier": pending["verifier"],
        })
        token = credentials.get("access_token")
        if not isinstance(token, str) or len(token) > 512 or not _BASE64URL.fullmatch(token):
            raise ValueError("GitHub rejected the sign-in code. Start again.")
        profile = _github_json(_PROFILE, token=token)
        identity, login = profile.get("id"), profile.get("login")
        if type(identity) is not int or identity <= 0 or not isinstance(login, str) or not _LOGIN.fullmatch(login):
            raise ValueError("GitHub returned an invalid account profile.")
        return User(str(identity), login, secrets.token_urlsafe(32))

    def start_session(self, response: Response, user: User) -> None:
        session = self._seal("session", {"id": user.id, "login": user.login, "csrf": user.csrf}, _SESSION_AGE)
        self._set_cookie(response, self.session_cookie, session, _SESSION_AGE)

    def user(self, request: BrowserRequest) -> User | None:
        session = self._open("session", request.cookies.get(self.session_cookie, ""))
        if session is None:
            return None
        return User(session["id"], session["login"], session["csrf"])

    def require_csrf(self, request: BrowserRequest, user: User) -> None:
        csrf = request.headers.get("x-csrf-token", "")
        if request.headers.get("origin") != self.origin or not _BASE64URL.fullmatch(csrf):
            raise ValueError("Invalid request origin or CSRF token.")
        if not hmac.compare_digest(csrf, user.csrf):
            raise ValueError("Invalid request origin or CSRF token.")

    def logout(self, response: Response) -> None:
        self._clear_cookie(response, self.session_cookie)
        self._clear_cookie(response, self.state_cookie)
