"""Loopback-only packaged dashboard; every operation uses the shared merge service."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from mergerisk.git.plumbing import run_git
from mergerisk.history import History, Jobs
from mergerisk.rules.catalog import RULES
from mergerisk.service import MergeService
from mergerisk.repair import digest
from mergerisk.verification import RuntimeConfig, verify_runtime

ASSETS = Path(__file__).parent


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RepositoryInput(Input):
    path: str = Field(min_length=1, max_length=4096)


class AnalysisInput(Input):
    repo_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    left: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00\r\n]+$")
    right: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00\r\n]+$")


class ExpectedInput(Input):
    expected: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: int = Field(ge=0)


class ReviewInput(ExpectedInput):
    accepted: list[str] = Field(default_factory=list, max_length=100)
    rejected: list[str] = Field(default_factory=list, max_length=100)


class CommitInput(ExpectedInput):
    allow_partial: bool = False


class ApplyInput(ExpectedInput):
    confirm: bool


class SettingsInput(Input):
    image: str = ""
    command: list[str] = Field(default_factory=list, max_length=32)
    timeout: int = Field(default=30, ge=1, le=120)


def create_app(state_dir: Path | None = None, *, capacity=4):
    history = History(state_dir or Path.home() / ".mergerisk")
    jobs = Jobs(history, capacity)
    session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="MergeRisk", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.history, app.state.jobs = history, jobs
    templates = Jinja2Templates(directory=str(ASSETS / "templates"))
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.url.hostname not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Only loopback hosts are allowed"}, status_code=400)
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.headers.get('host')}"
        if origin and origin != expected_origin:
            return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
        authenticated = secrets.compare_digest(request.cookies.get("mergerisk_session", ""), session)
        public = request.url.path == "/" or request.url.path.startswith("/static/")
        if not authenticated and not (request.method == "GET" and public):
            return JSONResponse({"detail": "Open the dashboard home page to establish a local session"}, status_code=401)
        if request.method not in {"GET", "HEAD"}:
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                return JSONResponse({"detail": "Missing or invalid CSRF token"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Use application/json"}, status_code=415)
            length = request.headers.get("content-length", "")
            if not length.isdecimal() or int(length) > 16384:
                return JSONResponse({"detail": "Request body limit is 16 KiB"}, status_code=413)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({"detail": "Request body limit is 16 KiB"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "Cross-Origin-Resource-Policy": "same-origin", "Cache-Control": "no-store"})
        if request.url.path == "/" and request.method == "GET":
            response.set_cookie("mergerisk_session", session, httponly=True, samesite="strict", secure=False)
        return response

    @app.exception_handler(LookupError)
    async def not_found(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(RuntimeError)
    async def failed(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(OSError)
    async def filesystem_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    def page(request, name, **context):
        return templates.TemplateResponse(request=request, name=name, context={
            "csrf": csrf, "page": name, "repositories": history.repositories(), "rules": RULES, **context})

    @app.get("/", response_class=HTMLResponse)
    def repositories_page(request: Request):
        return page(request, "repositories.html", runs=history.runs())

    @app.get("/new", response_class=HTMLResponse)
    def new_page(request: Request, repo: str = ""):
        return page(request, "new.html", selected_repo=repo)

    @app.get("/history", response_class=HTMLResponse)
    def history_page(request: Request):
        return page(request, "history.html", runs=history.runs())

    @app.get("/learn", response_class=HTMLResponse)
    def learn_page(request: Request):
        return page(request, "learn.html")

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        repos = history.repositories()
        for repo in repos:
            repo["runtime_config"] = json.loads(repo["runtime"]) if repo["runtime"] else None
        return page(request, "settings.html", configured_repos=repos, state_directory=str(history.directory))

    @app.get("/runs/{id}", response_class=HTMLResponse)
    def result_page(request: Request, id: str):
        run = history.run(id)
        return page(request, "result.html", run=run, repo=history.repository(run["repo_id"], validate=False),
                    fallback_fingerprint=digest(id.encode()))

    @app.get("/api/repositories")
    def repositories_api():
        return history.repositories()

    @app.post("/api/repositories", status_code=201)
    def add_repository(data: RepositoryInput):
        identifier = history.register(Path(data.path))
        return {"id": identifier, "redirect": "/new?repo=" + identifier}

    @app.get("/api/repositories/{id}/branches")
    def branches_api(id: str):
        repo = history.repository(id)
        service = MergeService(Path(repo["path"]))
        output = run_git(service.repo, ["for-each-ref", "--format=%(refname:short)%00%(objectname)", "refs/heads/"]).stdout
        branches = []
        for line in output.splitlines():
            name, sha = line.split(b"\0")
            branches.append({"name": name.decode("utf-8", "replace"), "sha": sha.decode()})
        return {"branches": branches, "head": service.assembler.resolve_commit("HEAD"),
                "health": "shallow" if run_git(service.repo, ["rev-parse", "--is-shallow-repository"]).stdout.strip() == b"true" else "ready"}

    @app.post("/api/repositories/{id}/settings")
    def settings_api(id: str, data: SettingsInput):
        config = None
        if data.image or data.command:
            checked = RuntimeConfig(data.image, tuple(data.command), data.timeout)
            config = {"image": checked.image, "command": list(checked.command), "timeout": checked.timeout}
        history.runtime(id, config)
        return {"saved": True}

    @app.post("/api/runs", status_code=202)
    def start_analysis(data: AnalysisInput):
        try:
            id = jobs.submit(data.repo_id, data.left, data.right)
        except OverflowError as error:
            raise HTTPException(429, str(error)) from error
        return {"id": id, "redirect": "/runs/" + id}

    @app.get("/api/runs/{id}")
    def run_api(id: str):
        return history.run(id)

    @app.get("/api/runs/{id}/export")
    def export_api(id: str):
        return JSONResponse(history.run(id), headers={"Content-Disposition": f'attachment; filename="mergerisk-{id[:32]}.json"'})

    @app.post("/api/runs/{id}/cancel")
    def cancel_api(id: str):
        history.run(id)
        jobs.cancel(id)
        history.action(id, "cancel", {})
        return {"cancelled": True}

    def checked_run(id, data):
        run = history.run(id)
        if run["state"] != "complete" or not run["result"]:
            raise HTTPException(409, "Wait for a complete analysis")
        if run["version"] != data.version or run["result"]["fingerprint"] != data.expected:
            raise HTTPException(409, "Stale request; reload the latest result")
        return run, history.repository(run["repo_id"])

    def current_preview(run, repo, accepted=None):
        old = run["result"]
        service = MergeService(Path(repo["path"]))
        for role in ("left", "right"):
            if service.assembler.resolve_commit(run["request"][role]) != old["scenario"][role + "_commit"]:
                raise HTTPException(409, "Branch changed since analysis; start a new merge")
        preview = service.preview(old["scenario"]["left_commit"], old["scenario"]["right_commit"],
                                  accepted=set(old.get("accepted", []) if accepted is None else accepted))
        return service, preview

    @app.post("/api/runs/{id}/review")
    def review_api(id: str, data: ReviewInput):
        with jobs.mutations:
            run, repo = checked_run(id, data)
            if run["result"].get("artifact"):
                raise HTTPException(409, "A commit already exists; start a new analysis to change repairs")
            suggestions = {p["id"] for p in run["result"]["repairs"] if p["tier"] == "SUGGEST"}
            if (set(data.accepted) & set(data.rejected) or (set(data.accepted) | set(data.rejected)) - suggestions):
                raise ValueError("Invalid or stale suggestion choices")
            _, preview = current_preview(run, repo, data.accepted)
            result = preview.to_dict(include_sources=True)
            result.update(accepted=data.accepted, rejected=data.rejected)
            history.update(id, "complete", "Review saved and statically checked", result=result)
            history.action(id, "review", {"accepted": data.accepted, "rejected": data.rejected})
        return {"saved": True}

    @app.post("/api/runs/{id}/commit")
    def commit_api(id: str, data: CommitInput):
        with jobs.mutations:
            run, repo = checked_run(id, data)
            if run["result"].get("artifact"):
                raise HTTPException(409, "This preview already has a commit")
            runtime = run["result"].get("runtime", {})
            if repo["runtime"] and (runtime.get("status") != "runtime_verified"
                                    or runtime.get("configuration") != json.loads(repo["runtime"])):
                raise ValueError("Current configured runtime checks must pass before commit creation")
            service, preview = current_preview(run, repo)
            artifact = service.create_commit(preview, expected=data.expected, allow_partial=data.allow_partial)
            result = run["result"]
            result["artifact"] = artifact
            history.update(id, "complete", "Immutable merge commit created; checkout unchanged", result=result)
            history.action(id, "commit", artifact)
        return artifact

    @app.post("/api/runs/{id}/apply")
    def apply_api(id: str, data: ApplyInput):
        if not data.confirm:
            raise ValueError("Explicit fast-forward confirmation is required")
        with jobs.mutations:
            run, repo = checked_run(id, data)
            artifact = run["result"].get("artifact")
            if not artifact or artifact.get("applied"):
                raise ValueError("Create a merge commit first; an applied artifact cannot be applied twice")
            service = MergeService(Path(repo["path"]))
            service.apply(artifact, expected_head=run["result"]["scenario"]["left_commit"])
            history.update(id, "complete", "Target branch fast-forwarded", result=run["result"])
            history.action(id, "apply", artifact)
        return artifact

    @app.post("/api/runs/{id}/verify")
    def verify_api(id: str, data: ExpectedInput):
        # One bounded runner at a time. It runs only configured, immutable containers.
        if not jobs.capacity.acquire(blocking=False):
            raise HTTPException(429, "Verification queue is full")
        try:
            with jobs.mutations:
                run, repo = checked_run(id, data)
                if not repo["runtime"]:
                    raise ValueError("Configure an immutable Docker image and command in Settings first")
                service, preview = current_preview(run, repo)
                config = json.loads(repo["runtime"])
                result = run["result"]
                result["runtime"] = verify_runtime(service, preview, RuntimeConfig(config["image"], tuple(config["command"]), config["timeout"]))
                result["runtime"]["configuration"] = config
                history.update(id, "complete", "Runtime verification finished", result=result)
                history.action(id, "verify", result["runtime"])
                return result["runtime"]
        finally:
            jobs.capacity.release()

    @app.post("/api/runs/{id}/delete")
    def delete_api(id: str, data: ExpectedInput):
        with jobs.mutations:
            run = history.run(id)
            token = run["result"]["fingerprint"] if run["result"] else digest(id.encode())
            if run["version"] != data.version or token != data.expected:
                raise HTTPException(409, "Stale request; reload the latest result")
            history.delete(id)
        return {"redirect": "/history"}

    return app


def serve(port=8765, state_dir=None):
    import uvicorn
    directory = (state_dir or Path.home() / ".mergerisk").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "instance.lock").open("a+b") as lock:
        lock.write(b"\0")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Another dashboard is already using this state directory") from error
        print(f"MergeRisk dashboard: http://127.0.0.1:{port}")
        uvicorn.run(create_app(directory), host="127.0.0.1", port=port, proxy_headers=False, server_header=False)
