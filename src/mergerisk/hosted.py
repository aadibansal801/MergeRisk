"""Authenticated, read-only web beta for public GitHub repositories."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mergerisk import hosted_admin, hosted_catalog
from mergerisk.hosted_auth import GitHubAuth
from mergerisk.hosted_ingest import parse_repository_url, validate_branch
from mergerisk.hosted_store import HostedStore


_LOG = logging.getLogger(__name__)
_ASSETS = Path(__file__).parent
_MAX_REPORT_BYTES = 512 * 1024
_WORKER_SECONDS = 150
_HEARTBEAT_SECONDS = 5
_MAINTENANCE_SECONDS = 60


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=255)


def _run_analysis(payload):
    # Service secrets and inherited Git configuration stay in the API process.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "LANG"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    with tempfile.TemporaryDirectory(prefix="mergerisk-hosted-job-") as work:
        env.update(TMPDIR=work, TEMP=work, TMP=work)
        process = subprocess.Popen(
            [sys.executable, "-I", "-m", "mergerisk.hosted_ingest"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, start_new_session=os.name == "posix",
        )
        try:
            output, _ = process.communicate(json.dumps(payload).encode("ascii"), timeout=_WORKER_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.communicate()
            return {"error": "Analysis exceeded the time limit. Try a smaller repository."}
    if process.returncode or not output or len(output) > _MAX_REPORT_BYTES:
        return {"error": "Analysis ended before a report was available."}
    try:
        answer = json.loads(output)
        if isinstance(answer, dict):
            if set(answer) == {"result"} and isinstance(answer["result"], dict):
                return answer
            if set(answer) == {"error"} and isinstance(answer["error"], str):
                return answer
    except ValueError:
        pass
    return {"error": "Analysis ended before a report was available."}


async def _worker(store, analyzer, wake, stop):
    while not stop.is_set():
        try:
            await asyncio.wait_for(wake.wait(), timeout=_MAINTENANCE_SECONDS)
        except asyncio.TimeoutError:
            pass
        wake.clear()
        if stop.is_set():
            break
        try:
            job = await asyncio.to_thread(store.claim)
            if job is not None:
                job_id, lease = job["id"], job["lease_token"]
                task = asyncio.create_task(asyncio.to_thread(analyzer, job["request"]))
                while not task.done():
                    await asyncio.wait({task}, timeout=_HEARTBEAT_SECONDS)
                    if not task.done():
                        try:
                            await asyncio.to_thread(store.heartbeat, job_id, lease)
                        except Exception:
                            # Keep supervising this job while the database reconnects.
                            _LOG.warning("Hosted job heartbeat could not reach the database")
                try:
                    answer = await task
                except Exception:
                    _LOG.warning("Hosted analysis failed for job %s", job_id)
                    answer = {"error": "Analysis ended before a report was available."}
                await asyncio.to_thread(store.finish, job_id, lease, **answer)
                wake.set()
        except Exception:
            _LOG.warning("Hosted job processing was interrupted by a storage or worker failure")


def _origin(value):
    parts = urlsplit(value)
    canonical = parts.hostname + (f":{parts.port}" if parts.port else "") if parts.hostname else ""
    if parts.scheme != "https" or not canonical or value != f"https://{canonical}":
        raise ValueError("MERGERISK_ORIGIN must be the canonical HTTPS origin without a trailing slash")
    return value, parts.hostname


def _configured():
    names = ("ORIGIN", "DATABASE_URL", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "SESSION_SECRET")
    settings = {name: os.environ.get("MERGERISK_" + name, "") for name in names}
    missing = ["MERGERISK_" + name for name, value in settings.items() if not value]
    if missing:
        raise ValueError("Missing hosted settings: " + ", ".join(missing))
    origin, _ = _origin(settings["ORIGIN"])
    store = HostedStore(settings["DATABASE_URL"])
    auth = GitHubAuth(settings["GITHUB_CLIENT_ID"], settings["GITHUB_CLIENT_SECRET"], settings["SESSION_SECRET"], origin)
    return store, auth, origin


def _public_job(job, *, detail=False):
    result = job.get("result") or {}
    data = {key: job[key] for key in ("id", "state", "request", "error", "created", "updated") if key in job}
    data["has_patch"] = bool(result.get("patch_b64"))
    if detail:
        data["result"] = {key: value for key, value in result.items() if key != "patch_b64"}
    return data


def create_app(*, store=None, auth=None, origin=None, analyzer=_run_analysis):
    if store is None and auth is None:
        store, auth, origin = _configured()
    if store is None or auth is None or origin is None:
        raise ValueError("Hosted app requires a store, authentication, and origin")
    _, host = _origin(origin)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        wake = asyncio.Event()
        wake.set()
        app.state.wake = wake
        task = asyncio.create_task(_worker(store, analyzer, wake, stop))
        try:
            yield
        finally:
            stop.set()
            wake.set()
            await task

    app = FastAPI(title="MergeRisk", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host], www_redirect=False)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' https://api.github.com; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    app.mount("/assets", StaticFiles(directory=_ASSETS / "static"), name="assets")
    templates = Jinja2Templates(directory=_ASSETS / "templates")

    def current(request, *, required=True, write=False):
        session = auth.session(request)
        if session is not None:
            try:
                if store.is_session_revoked(session.token_hash):
                    session = None
            except Exception as error:
                _LOG.warning("Hosted session verification could not reach the database")
                raise HTTPException(503, "Sign-in verification is unavailable. Try again shortly.") from error
        if session is None:
            if required:
                raise HTTPException(401, "Sign in with GitHub to use MergeRisk.")
            return None
        if write:
            try:
                auth.require_csrf(request, session.user)
            except ValueError as error:
                raise HTTPException(403, "Request could not be verified.") from error
        return session

    def owned_job(owner, job_id):
        if len(job_id) > 64:
            raise HTTPException(404, "Analysis not found.")
        job = store.get(owner, job_id)
        if job is None:
            raise HTTPException(404, "Analysis not found.")
        return job

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def home(request: Request, login: str = ""):
        session = current(request, required=False)
        return templates.TemplateResponse(request, "hosted.html", {
            "user": session.user if session is not None else None,
            "login_error": login == "failed",
        })

    @app.get("/auth/github")
    def login():
        response = RedirectResponse("/", 303)
        response.headers["Location"] = auth.start(response)
        return response

    @app.get("/auth/github/callback")
    def callback(request: Request, code: str = "", state: str = ""):
        response = RedirectResponse("/", 303)
        try:
            user = auth.callback(request, response, code, state)
        except (ValueError, OSError):
            response.headers["Location"] = "/?login=failed"
            return response
        try:
            store.register_account(user.id, user.login)
        except Exception:
            _LOG.warning("Hosted sign-in could not save the account")
            response.headers["Location"] = "/?login=failed"
            return response
        try:
            store.record_event(user.id, user.login, "login")
        except Exception:
            _LOG.warning("Hosted sign-in could not record usage")
        auth.start_session(response, user)
        return response

    @app.post("/auth/logout")
    def logout(request: Request):
        session = current(request, write=True)
        try:
            store.revoke_session(session.token_hash, session.expires)
        except Exception as error:
            _LOG.warning("Hosted sign-out could not save the session revocation")
            raise HTTPException(503, "Sign-out could not be completed. Try again shortly.") from error
        response = Response(status_code=204)
        auth.logout(response)
        return response

    @app.get("/api/github/repositories")
    def github_repositories(request: Request, page: int = Query(1, ge=1, le=1000)):
        login = current(request).user.login
        try:
            return hosted_catalog.repositories(login, page)
        except hosted_catalog.CatalogError as error:
            raise HTTPException(502, str(error)) from error

    @app.get("/api/github/branches")
    def github_branches(request: Request, repository: str = Query(max_length=256),
                        page: int = Query(1, ge=1, le=1000)):
        current(request)
        try:
            slug = parse_repository_url(repository)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        try:
            return {"repository": f"https://github.com/{slug}", **hosted_catalog.branches(slug, page)}
        except hosted_catalog.CatalogError as error:
            raise HTTPException(502, str(error)) from error

    @app.post("/api/jobs", status_code=202)
    async def submit(request: Request):
        session = await asyncio.to_thread(current, request, write=True)
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            raise HTTPException(415, "Send the analysis form as JSON.")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 4096:
                raise HTTPException(413, "Analysis inputs exceed the size limit.")
            body.extend(chunk)
        try:
            item = RunInput.model_validate_json(body)
            payload = {"repository": parse_repository_url(item.repository), "target": validate_branch(item.target),
                       "source": validate_branch(item.source)}
            if payload["target"] == payload["source"]:
                raise ValueError("Choose two different branches.")
        except ValidationError as error:
            raise HTTPException(422, "Provide a GitHub repository URL and two branch names.") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        try:
            job = await asyncio.to_thread(store.submit, session.user.id, payload)
        except OverflowError as error:
            raise HTTPException(429, str(error)) from error
        try:
            await asyncio.to_thread(store.record_event, session.user.id, session.user.login, "analysis",
                                    payload["repository"])
        except Exception:
            _LOG.warning("Hosted analysis could not record usage")
        request.app.state.wake.set()
        return _public_job(job)

    @app.get("/api/jobs")
    async def jobs(request: Request):
        session = await asyncio.to_thread(current, request)
        request.app.state.wake.set()
        return [_public_job(job) for job in await asyncio.to_thread(store.list, session.user.id)]

    @app.get("/api/jobs/{job_id}")
    async def job(request: Request, job_id: str):
        session = await asyncio.to_thread(current, request)
        request.app.state.wake.set()
        return _public_job(await asyncio.to_thread(owned_job, session.user.id, job_id), detail=True)

    @app.get("/api/jobs/{job_id}/patch")
    def patch(request: Request, job_id: str):
        job = owned_job(current(request).user.id, job_id)
        patch_data = (job.get("result") or {}).get("patch_b64")
        if not patch_data:
            raise HTTPException(404, "This analysis has no verified patch.")
        return Response(base64.b64decode(patch_data, validate=True), media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="mergerisk.patch"'})

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete(request: Request, job_id: str):
        user = current(request, write=True).user
        owned_job(user.id, job_id)
        if not store.delete(user.id, job_id):
            raise HTTPException(409, "Wait for the analysis to finish before deleting it.")
        return Response(status_code=204)

    hosted_admin.mount(app, store, auth, templates)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app, factory=True, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=False, server_header=False, access_log=False)
