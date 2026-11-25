"""Admin dashboard (/admin): password sign-in, super_admin/admin roles and portal usage statistics."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mergerisk.hosted_auth import Session, User


_LOG = logging.getLogger(__name__)
SUPER_ADMIN = "super_admin"
ADMIN = "admin"
_SESSION_AGE = 4 * 3600
_LOCKOUT_FAILURES = 5
_LOCKOUT_WINDOW = 15 * 60
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
_DAY = 86400


# --- passwords -------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1,
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return scheme == "scrypt" and hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def check_password_strength(password: str) -> None:
    if (len(password) < 8 or len(password) > 128 or not re.search(r"[a-z]", password)
            or not re.search(r"[A-Z]", password) or not re.search(r"\d", password)
            or not re.search(r"[^A-Za-z0-9]", password)):
        raise ValueError("Use 8-128 characters with upper and lower case letters, a number and a symbol.")


# --- storage ---------------------------------------------------------------------------------

class AdminStore:
    """Admin accounts and usage queries over the shared hosted database."""

    def __init__(self, store):
        self.store = store

    def _q(self, sql, params=()):
        with self.store._connect() as db:
            return [dict(row) for row in self.store._execute(db, sql, params).fetchall()]

    def _run(self, sql, params=()):
        with self.store._connect() as db:
            return self.store._execute(db, sql, params).rowcount

    def create(self, email: str, password: str, role: str, created_by: str | None) -> dict:
        email = normalize_email(email)
        check_password_strength(password)
        if self.by_email(email) is not None:
            raise ValueError("An admin with that email already exists.")
        record = {"id": uuid.uuid4().hex, "email": email, "role": role, "created": time.time(),
                  "created_by": created_by}
        self._run("""INSERT INTO admin_accounts (id, email, password_hash, role, created, created_by)
            VALUES (?, ?, ?, ?, ?, ?)""", (record["id"], email, hash_password(password), role, record["created"],
                                           created_by))
        return record

    def by_email(self, email: str):
        rows = self._q("SELECT * FROM admin_accounts WHERE email = ?", (email,))
        return rows[0] if rows else None

    def by_id(self, identifier: str):
        rows = self._q("SELECT * FROM admin_accounts WHERE id = ?", (identifier,))
        return rows[0] if rows else None

    def list(self) -> list[dict]:
        return self._q("""SELECT a.id, a.email, a.role, a.created, b.email AS created_by
            FROM admin_accounts a LEFT JOIN admin_accounts b ON b.id = a.created_by
            ORDER BY a.role DESC, a.created""")

    def remove(self, identifier: str) -> bool:
        return self._run("DELETE FROM admin_accounts WHERE id = ? AND role = ?", (identifier, ADMIN)) == 1

    def set_password(self, identifier: str, password: str) -> None:
        check_password_strength(password)
        self._run("UPDATE admin_accounts SET password_hash = ? WHERE id = ?", (hash_password(password), identifier))

    def ensure_super_admin(self, email: str, password: str) -> bool:
        """Create the super admin if absent; never overwrites an existing password."""
        if self.by_email(normalize_email(email)) is not None:
            return False
        self.create(email, password, SUPER_ADMIN, None)
        return True

    # Sign-in throttling: failed attempts per email within a sliding window.
    def locked_out(self, email: str) -> bool:
        now = time.time()
        self._run("DELETE FROM admin_login_failures WHERE created <= ?", (now - _LOCKOUT_WINDOW,))
        rows = self._q("SELECT COUNT(*) AS n FROM admin_login_failures WHERE email = ? AND created > ?",
                       (email, now - _LOCKOUT_WINDOW))
        return rows[0]["n"] >= _LOCKOUT_FAILURES

    def record_failure(self, email: str) -> None:
        self._run("INSERT INTO admin_login_failures (id, email, created) VALUES (?, ?, ?)",
                  (uuid.uuid4().hex, email[:254], time.time()))

    def clear_failures(self, email: str) -> None:
        self._run("DELETE FROM admin_login_failures WHERE email = ?", (email,))

    # Usage statistics.
    def stats(self, days: int) -> dict:
        now = time.time()
        since = now - days * _DAY
        scalar = lambda sql, params=(): self._q(sql, params)[0]["n"]  # noqa: E731
        totals = {
            "users": scalar("SELECT COUNT(*) AS n FROM hosted_accounts"),
            "logins": scalar("SELECT COUNT(*) AS n FROM hosted_usage_events WHERE kind = 'login'"),
            "analyses": scalar("SELECT COUNT(*) AS n FROM hosted_usage_events WHERE kind = 'analysis'"),
            "new_users": scalar("SELECT COUNT(*) AS n FROM hosted_accounts WHERE created > ?", (since,)),
            "active_users": scalar("SELECT COUNT(DISTINCT github_id) AS n FROM hosted_usage_events WHERE created > ?",
                                   (since,)),
            "period_logins": scalar("""SELECT COUNT(*) AS n FROM hosted_usage_events
                WHERE kind = 'login' AND created > ?""", (since,)),
            "period_analyses": scalar("""SELECT COUNT(*) AS n FROM hosted_usage_events
                WHERE kind = 'analysis' AND created > ?""", (since,)),
        }
        users = self._q("""SELECT a.github_id, a.login, a.created AS joined,
                COUNT(CASE WHEN e.kind = 'login' THEN 1 END) AS logins,
                COUNT(CASE WHEN e.kind = 'analysis' THEN 1 END) AS analyses,
                MAX(e.created) AS last_active
            FROM hosted_accounts a LEFT JOIN hosted_usage_events e ON e.github_id = a.github_id
            GROUP BY a.github_id, a.login, a.created
            ORDER BY analyses DESC, logins DESC, a.created DESC LIMIT 500""")
        repositories = self._q("""SELECT repository, COUNT(*) AS runs, COUNT(DISTINCT github_id) AS users
            FROM hosted_usage_events WHERE kind = 'analysis' AND repository IS NOT NULL AND created > ?
            GROUP BY repository ORDER BY runs DESC, repository LIMIT 10""", (since,))
        daily = {}
        for offset in range(days):
            daily[time.strftime("%Y-%m-%d", time.gmtime(now - (days - 1 - offset) * _DAY))] = {
                "logins": 0, "analyses": 0, "users": set()}
        for event in self._q("SELECT github_id, kind, created FROM hosted_usage_events WHERE created > ?", (since,)):
            bucket = daily.get(time.strftime("%Y-%m-%d", time.gmtime(event["created"])))
            if bucket is not None:
                bucket["logins" if event["kind"] == "login" else "analyses"] += 1
                bucket["users"].add(event["github_id"])
        series = [{"date": day, "logins": value["logins"], "analyses": value["analyses"],
                   "users": len(value["users"])} for day, value in daily.items()]
        return {"days": days, "totals": totals, "series": series, "users": users, "repositories": repositories}

    def activity(self, limit: int, github_id: str | None = None) -> list[dict]:
        if github_id:
            return self._q(f"""SELECT github_id, login, kind, repository, created FROM hosted_usage_events
                WHERE github_id = ? ORDER BY created DESC LIMIT {int(limit)}""", (github_id,))
        return self._q(f"""SELECT github_id, login, kind, repository, created FROM hosted_usage_events
            ORDER BY created DESC LIMIT {int(limit)}""")


# --- HTTP ------------------------------------------------------------------------------------

class _LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class _NewAdminInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class _PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: str = Field(min_length=1, max_length=128)
    current: str | None = Field(default=None, max_length=128)


def mount(app, store, auth, templates) -> AdminStore:
    admins = AdminStore(store)
    cookie = ("__Host-" if auth.secure else "") + "mergerisk_admin_session"

    email, password = os.environ.get("MERGERISK_SEED_SUPERADMIN_EMAIL"), os.environ.get("MERGERISK_SEED_SUPERADMIN_PASSWORD")
    if email and password:
        try:
            if admins.ensure_super_admin(email, password):
                _LOG.warning("Seeded the super admin account")
        except Exception as error:
            _LOG.warning("Could not seed the super admin account: %s", error)

    def session_of(request):
        token = request.cookies.get(cookie, "")
        document = auth._open("admin", token)
        if document is None or not isinstance(document.get("id"), str):
            return None
        return Session(User(document["id"], "", document.get("csrf", "")),
                       hashlib.sha256(token.encode("ascii")).hexdigest(), document["exp"])

    def current(request, *, write=False, super_only=False, required=True):
        session = session_of(request)
        admin = None
        if session is not None:
            try:
                if store.is_session_revoked(session.token_hash):
                    session = None
                else:
                    admin = admins.by_id(session.user.id)  # removal takes effect immediately
            except Exception as error:
                raise HTTPException(503, "Sign-in verification is unavailable. Try again shortly.") from error
        if session is None or admin is None:
            if required:
                raise HTTPException(401, "Sign in to the admin dashboard.")
            return None, None
        if write:
            try:
                auth.require_csrf(request, session.user)
            except ValueError as error:
                raise HTTPException(403, "Request could not be verified.") from error
        if super_only and admin["role"] != SUPER_ADMIN:
            raise HTTPException(403, "Only a super admin can do that.")
        return session, admin

    async def body(request, model):
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            raise HTTPException(415, "Send JSON.")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, "Request is too large.")
        try:
            return model.model_validate_json(bytes(raw))
        except ValidationError as error:
            raise HTTPException(422, "Check the submitted fields.") from error

    def public(admin):
        return {"id": admin["id"], "email": admin["email"], "role": admin["role"]}

    @app.get("/admin/login")
    def login_page(request: Request):
        _, admin = current(request, required=False)
        if admin is not None:
            return RedirectResponse("/admin", 303)
        return templates.TemplateResponse(request, "admin.html", {"admin": None})

    @app.get("/admin")
    def dashboard(request: Request):
        session, admin = current(request, required=False)
        if admin is None:
            return RedirectResponse("/admin/login", 303)
        return templates.TemplateResponse(request, "admin.html", {"admin": public(admin), "csrf": session.user.csrf})

    @app.post("/admin/api/login")
    async def login(request: Request):
        if request.headers.get("origin") != auth.origin:
            raise HTTPException(403, "Request could not be verified.")
        item = await body(request, _LoginInput)
        address = item.email.strip().lower()[:254]
        if await asyncio_thread(admins.locked_out, address):
            raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
        admin = await asyncio_thread(admins.by_email, address)
        valid = await asyncio_thread(verify_password, item.password, admin["password_hash"] if admin else _DUMMY_HASH)
        if admin is None or not valid:
            await asyncio_thread(admins.record_failure, address)
            raise HTTPException(401, "Email or password is incorrect.")
        await asyncio_thread(admins.clear_failures, address)
        response = Response(status_code=204)
        token = auth._seal("admin", {"id": admin["id"], "csrf": secrets.token_urlsafe(32)}, _SESSION_AGE)
        auth._set_cookie(response, cookie, token, _SESSION_AGE)
        return response

    @app.post("/admin/api/logout")
    def logout(request: Request):
        session, _ = current(request, write=True)
        store.revoke_session(session.token_hash, session.expires)
        response = Response(status_code=204)
        auth._clear_cookie(response, cookie)
        return response

    @app.get("/admin/api/me")
    def me(request: Request):
        return public(current(request)[1])

    @app.get("/admin/api/stats")
    def stats(request: Request, days: int = Query(30, ge=1, le=90)):
        current(request)
        return admins.stats(days)

    @app.get("/admin/api/activity")
    def activity(request: Request, github_id: str = Query("", max_length=32), limit: int = Query(100, ge=1, le=500)):
        current(request)
        return admins.activity(limit, github_id or None)

    @app.get("/admin/api/admins")
    def list_admins(request: Request):
        current(request, super_only=True)
        return admins.list()

    @app.post("/admin/api/admins", status_code=201)
    async def add_admin(request: Request):
        _, admin = current(request, write=True, super_only=True)
        item = await body(request, _NewAdminInput)
        try:
            created = admins.create(item.email, item.password, ADMIN, admin["id"])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"id": created["id"], "email": created["email"], "role": ADMIN}

    @app.delete("/admin/api/admins/{identifier}", status_code=204)
    def remove_admin(request: Request, identifier: str):
        current(request, write=True, super_only=True)
        if len(identifier) > 64 or not admins.remove(identifier):
            raise HTTPException(404, "Admin not found (a super admin cannot be removed).")
        return Response(status_code=204)

    @app.post("/admin/api/admins/{identifier}/password", status_code=204)
    async def reset_password(request: Request, identifier: str):
        current(request, write=True, super_only=True)
        item = await body(request, _PasswordInput)
        target = admins.by_id(identifier) if len(identifier) <= 64 else None
        if target is None or target["role"] != ADMIN:
            raise HTTPException(404, "Admin not found.")
        try:
            admins.set_password(identifier, item.password)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return Response(status_code=204)

    @app.post("/admin/api/password", status_code=204)
    async def change_own_password(request: Request):
        _, admin = current(request, write=True)
        item = await body(request, _PasswordInput)
        if not item.current or not verify_password(item.current, admin["password_hash"]):
            raise HTTPException(403, "Current password is incorrect.")
        try:
            admins.set_password(admin["id"], item.password)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return Response(status_code=204)

    return admins


async def asyncio_thread(function, *args):
    return await asyncio.to_thread(function, *args)


# --- command line: python -m mergerisk.hosted_admin seed --email ... --password ... -------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mergerisk.hosted_admin", description="Admin account maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="create the super admin if it does not exist")
    seed.add_argument("--email", required=True)
    seed.add_argument("--password", default=os.environ.get("MERGERISK_SEED_SUPERADMIN_PASSWORD"))
    seed.add_argument("--sqlite", help="SQLite file (default: PostgreSQL from MERGERISK_DATABASE_URL)")
    args = parser.parse_args(argv)
    if not args.password:
        parser.error("--password (or MERGERISK_SEED_SUPERADMIN_PASSWORD) is required")
    from pathlib import Path
    from mergerisk.hosted_store import HostedStore
    store = (HostedStore(sqlite_path=Path(args.sqlite)) if args.sqlite
             else HostedStore(os.environ["MERGERISK_DATABASE_URL"]))
    created = AdminStore(store).ensure_super_admin(args.email, args.password)
    print("Super admin created." if created else "Super admin already exists; password unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
