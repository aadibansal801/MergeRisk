"""Local SQLite history and bounded, cancellable background analysis."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
import uuid

from mergerisk.service import MergeService


def now():
    return datetime.now(timezone.utc).isoformat()


def private_state_directory(directory: Path) -> Path:
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        info = directory.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError("Dashboard state must be owned by you and writable only by you.")
    return directory


def _protect_database(path: Path) -> None:
    if os.name != "posix":
        return
    for name in (path.name, path.name + "-wal", path.name + "-shm", path.name + "-journal"):
        try:
            flags = os.O_RDWR | os.O_CREAT if name == path.name else os.O_RDONLY
            fd = os.open(path.with_name(name), flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        except FileNotFoundError:
            continue
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                raise ValueError("Dashboard database files must be regular files owned only by you.")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)


class History:
    def __init__(self, directory: Path):
        self.directory = private_state_directory(directory)
        self.path = self.directory / "history.sqlite3"
        _protect_database(self.path)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    created TEXT NOT NULL, runtime TEXT);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, created TEXT NOT NULL,
                    updated TEXT NOT NULL, state TEXT NOT NULL, progress TEXT NOT NULL,
                    request TEXT NOT NULL, result TEXT, error TEXT, version INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, created TEXT NOT NULL,
                    kind TEXT NOT NULL, details TEXT NOT NULL);
                UPDATE runs SET state='error', error='Server stopped before completion; start a new analysis.',
                    progress='Interrupted by server restart' WHERE state IN ('queued','running','cancelling','validating');
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def repositories(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM repositories ORDER BY created DESC")]

    def repository(self, id, *, validate=True):
        with self.connect() as db:
            row = db.execute("SELECT * FROM repositories WHERE id=?", (id,)).fetchone()
        if not row:
            raise LookupError("Repository is not registered")
        result = dict(row)
        path = Path(result["path"])
        if validate:
            validate_repository_path(path)
        return result

    def register(self, path: Path):
        path = validate_repository_path(path)
        service = MergeService(path)
        # Resolve HEAD now to reject unborn repositories with no analyzable revisions.
        service.assembler.resolve_commit("HEAD")
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO repositories VALUES (?,?,?,?,NULL)",
                       (identifier, str(path), path.name, now()))
            row = db.execute("SELECT id FROM repositories WHERE path=?", (str(path),)).fetchone()
        return row["id"]

    def runtime(self, id, config):
        self.repository(id)
        with self.connect() as db:
            db.execute("UPDATE repositories SET runtime=? WHERE id=?", (json.dumps(config) if config else None, id))

    def runs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""
                SELECT runs.id,repo_id,runs.created,updated,state,progress,request,error,version,repositories.name
                FROM runs LEFT JOIN repositories ON repositories.id=runs.repo_id ORDER BY runs.created DESC LIMIT 500
            """)]

    def run(self, id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (id,)).fetchone()
            actions = [dict(r) for r in db.execute("SELECT * FROM actions WHERE run_id=? ORDER BY id", (id,))]
        if not row:
            raise LookupError("Analysis not found")
        result = dict(row)
        result["request"] = json.loads(result["request"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        result["actions"] = actions
        return result

    def update(self, id, state, progress, *, result=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE runs SET state=?,progress=?,updated=?,result=COALESCE(?,result),error=?,version=version+1 WHERE id=?",
                       (state, progress, now(), json.dumps(result, ensure_ascii=True) if result is not None else None, error, id))

    def action(self, id, kind, details):
        with self.connect() as db:
            db.execute("INSERT INTO actions(run_id,created,kind,details) VALUES (?,?,?,?)",
                       (id, now(), kind, json.dumps(details, ensure_ascii=True)))

    def delete(self, id):
        run = self.run(id)
        if run["state"] in {"queued", "running", "cancelling", "validating"}:
            raise ValueError("Cancel and wait before deleting an active run")
        with self.connect() as db:
            db.execute("DELETE FROM actions WHERE run_id=?", (id,))
            db.execute("DELETE FROM runs WHERE id=?", (id,))

    def storage_used(self):
        with self.connect() as db:
            size = db.execute("PRAGMA page_size").fetchone()[0]
            pages = db.execute("PRAGMA page_count").fetchone()[0] - db.execute("PRAGMA freelist_count").fetchone()[0]
        return size * pages


def validate_repository_path(path: Path):
    if not path.is_absolute():
        raise ValueError("Repository path must be absolute")
    if ".." in path.parts:
        raise ValueError("Repository path cannot contain traversal components")
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ValueError("Repository paths through symlinks or junctions are not allowed")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute() or not resolved.is_dir():
        raise ValueError("Use a canonical repository directory without traversal")
    return resolved


class Jobs:
    def __init__(self, history: History, capacity=4):
        self.history = history
        self.capacity = threading.BoundedSemaphore(capacity)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mergerisk")
        self.events: dict[str, threading.Event] = {}
        self.lock = threading.RLock()
        self.mutations = threading.Lock()

    def submit(self, repo_id, left, right):
        self.history.repository(repo_id)
        if self.history.storage_used() > 256 * 1024 * 1024 or len(self.history.runs()) >= 500:
            raise ValueError("History limit reached; export and delete older runs")
        if not self.capacity.acquire(blocking=False):
            raise OverflowError("Analysis queue is full (one running, three queued)")
        id = uuid.uuid4().hex
        try:
            with self.history.connect() as db:
                db.execute("INSERT INTO runs(id,repo_id,created,updated,state,progress,request) VALUES (?,?,?,?,?,?,?)",
                           (id, repo_id, now(), now(), "queued", "Waiting for analysis slot", json.dumps({"left": left, "right": right})))
            with self.lock:
                self.events[id] = threading.Event()
            self.pool.submit(self._work, id)
        except BaseException:
            with self.lock:
                self.events.pop(id, None)
            self.capacity.release()
            raise
        return id

    def _work(self, id):
        with self.lock:
            cancel = self.events[id]
        try:
            run = self.history.run(id)
            repo = self.history.repository(run["repo_id"])
            self.history.update(id, "running", "Starting immutable analysis")
            service = MergeService(Path(repo["path"]))
            preview = service.preview(run["request"]["left"], run["request"]["right"], cancel=cancel,
                                      progress=lambda p: self.history.update(id, "running", p))
            result = preview.to_dict(include_sources=True)
            result["accepted"], result["rejected"] = [], []
            with self.lock:
                if cancel.is_set():
                    raise InterruptedError("Analysis cancelled")
                self.history.update(id, "complete", "Analysis complete", result=result)
                self.events.pop(id, None)
        except InterruptedError:
            with self.lock:
                self.history.update(id, "cancelled", "Cancelled; checkout and refs unchanged")
                self.events.pop(id, None)
        except Exception as error:
            # Worker failures are persisted and visible, never reported as successful jobs.
            with self.lock:
                self.history.update(id, "error", "Analysis failed", error=str(error))
                self.events.pop(id, None)
        finally:
            with self.lock:
                self.events.pop(id, None)
            self.capacity.release()

    def cancel(self, id):
        with self.lock:
            event = self.events.get(id)
            if not event:
                raise ValueError("Analysis is no longer running")
            event.set()
            self.history.update(id, "cancelling", "Cancellation requested; waiting for a safe checkpoint")

    def close(self):
        with self.lock:
            for event in self.events.values():
                event.set()
        self.pool.shutdown(wait=True, cancel_futures=False)
