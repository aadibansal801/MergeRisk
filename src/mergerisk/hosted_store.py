"""Hosted accounts and owner-scoped reports with bounded job admission and leases."""
from __future__ import annotations

from contextlib import closing, contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid


_RETENTION = 24 * 3600
_LEASE = 90
_QUEUE_CAPACITY = 4
_PER_USER_HOURLY = 5
_DAILY_CAPACITY = 50
_MAX_REPORT_BYTES = 512 * 1024
_PUBLIC_FIELDS = "id, owner, state, request, error, created, updated"

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS hosted_accounts (
        github_id TEXT PRIMARY KEY,
        login TEXT NOT NULL,
        created DOUBLE PRECISION NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS queue_lock (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1)
    )""",
    "INSERT INTO queue_lock VALUES (1) ON CONFLICT DO NOTHING",
    """CREATE TABLE IF NOT EXISTS hosted_jobs (
        id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'complete', 'error')),
        request TEXT NOT NULL,
        result TEXT,
        error TEXT,
        created DOUBLE PRECISION NOT NULL,
        updated DOUBLE PRECISION NOT NULL,
        lease_token TEXT,
        lease_until DOUBLE PRECISION
    )""",
    "CREATE INDEX IF NOT EXISTS hosted_jobs_owner_created ON hosted_jobs (owner, created)",
    "CREATE INDEX IF NOT EXISTS hosted_jobs_state_created ON hosted_jobs (state, created)",
    """CREATE TABLE IF NOT EXISTS hosted_admissions (
        id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        created DOUBLE PRECISION NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS hosted_admissions_created ON hosted_admissions (created)",
)


class HostedStore:
    def __init__(self, database_url: str | None = None, *, sqlite_path: Path | None = None):
        if bool(database_url) == (sqlite_path is not None):
            raise ValueError("Configure exactly one hosted database.")
        self.database_url = database_url
        self.sqlite_path = sqlite_path
        if sqlite_path is not None:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect(initializing=True) as db:
            for statement in _SCHEMA:
                db.execute(statement)

    @contextmanager
    def _connect(self, *, initializing: bool = False):
        if self.sqlite_path is not None:
            with closing(sqlite3.connect(self.sqlite_path, timeout=5)) as db:
                db.row_factory = sqlite3.Row
                with db:
                    yield db
            return

        try:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Install the mergerisk[hosted] extra to use PostgreSQL.") from error
        tls = conninfo_to_dict(self.database_url)
        if tls.get("sslmode", "verify-full") != "verify-full":
            raise ValueError("Hosted PostgreSQL must verify the database server identity (sslmode=verify-full).")
        with psycopg.connect(self.database_url, row_factory=dict_row, prepare_threshold=None,
                             connect_timeout=5, sslmode="verify-full", sslrootcert=tls.get("sslrootcert", "system")) as db:
            db.execute("SET LOCAL statement_timeout = '5s'")
            db.execute("SET LOCAL lock_timeout = '3s'")
            if initializing:
                # Serializes creation when a deploy overlaps another worker starting up.
                db.execute("SELECT pg_catalog.pg_advisory_xact_lock(593240725)")
                db.execute("CREATE SCHEMA IF NOT EXISTS mergerisk_hosted")
                db.execute("REVOKE ALL ON SCHEMA mergerisk_hosted FROM PUBLIC")
            db.execute("SET LOCAL search_path TO mergerisk_hosted, pg_catalog")
            yield db

    def _execute(self, db, sql: str, params: tuple = ()):
        if self.database_url:
            sql = sql.replace("?", "%s")
        return db.execute(sql, params)

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        job = dict(row)
        job["request"] = json.loads(job["request"])
        job["result"] = json.loads(job["result"]) if job.get("result") is not None else None
        return job

    def _lock_queue(self, db) -> float:
        # Lock a shared database row before admission or a lease transition across processes.
        if self.database_url:
            db.execute("SELECT singleton FROM queue_lock WHERE singleton = 1 FOR UPDATE")
        else:
            db.execute("UPDATE queue_lock SET singleton = 1 WHERE singleton = 1")
        return time.time()

    def _sweep(self, db, now: float) -> None:
        cutoff = now - _RETENTION
        self._execute(db, "DELETE FROM hosted_admissions WHERE created <= ?", (cutoff,))
        self._execute(db, "DELETE FROM hosted_jobs WHERE created <= ?", (cutoff,))
        # A fresh fetch might resolve the selected branches to different commits.
        self._execute(db, """UPDATE hosted_jobs SET state = 'error', updated = ?,
            error = 'Analysis stopped before completion. Start a new run.', lease_token = NULL, lease_until = NULL
            WHERE state = 'running' AND lease_until <= ?""", (now, now))

    def register_account(self, github_id: str, login: str) -> None:
        """Create an account or refresh its login after GitHub verifies the identity."""
        with self._connect() as db:
            self._execute(db, """INSERT INTO hosted_accounts (github_id, login, created)
                VALUES (?, ?, ?) ON CONFLICT (github_id) DO UPDATE SET login = excluded.login""",
                          (github_id, login, time.time()))

    def submit(self, owner: str, request: dict) -> dict:
        identifier = uuid.uuid4().hex
        encoded = json.dumps(request, ensure_ascii=True, separators=(",", ":"))
        with self._connect() as db:
            now = self._lock_queue(db)
            self._sweep(db, now)
            if self._execute(db, "SELECT 1 FROM hosted_jobs WHERE owner = ? AND state IN ('queued','running') LIMIT 1",
                             (owner,)).fetchone():
                raise OverflowError("You already have an active analysis.")
            active = db.execute("SELECT COUNT(*) AS n FROM hosted_jobs WHERE state IN ('queued','running')").fetchone()["n"]
            if active >= _QUEUE_CAPACITY:
                raise OverflowError("Analysis queue is full. Try again shortly.")
            admitted = db.execute("SELECT COUNT(*) AS n FROM hosted_admissions").fetchone()["n"]
            if admitted >= _DAILY_CAPACITY:
                raise OverflowError("The beta's daily analysis limit has been reached.")
            hourly = self._execute(db, "SELECT COUNT(*) AS n FROM hosted_admissions WHERE owner = ? AND created > ?",
                                   (owner, now - 3600)).fetchone()["n"]
            if hourly >= _PER_USER_HOURLY:
                raise OverflowError("Your hourly analysis limit has been reached.")
            self._execute(db, "INSERT INTO hosted_admissions (id, owner, created) VALUES (?, ?, ?)",
                          (identifier, owner, now))
            self._execute(db, """INSERT INTO hosted_jobs (id, owner, state, request, created, updated)
                VALUES (?, ?, 'queued', ?, ?, ?)""", (identifier, owner, encoded, now, now))
        return {"id": identifier, "owner": owner, "state": "queued", "request": request, "result": None,
                "error": None, "created": now, "updated": now}

    def get(self, owner: str, identifier: str) -> dict | None:
        with self._connect() as db:
            row = self._execute(db, f"""SELECT {_PUBLIC_FIELDS}, result FROM hosted_jobs
                WHERE id = ? AND owner = ? AND created > ?""",
                                (identifier, owner, time.time() - _RETENTION)).fetchone()
        return self._decode(row)

    def list(self, owner: str) -> list[dict]:
        with self._connect() as db:
            rows = self._execute(db, f"""SELECT {_PUBLIC_FIELDS} FROM hosted_jobs
                WHERE owner = ? AND created > ? ORDER BY created DESC""", (owner, time.time() - _RETENTION)).fetchall()
        return [self._decode(row) for row in rows]

    def delete(self, owner: str, identifier: str) -> bool:
        with self._connect() as db:
            removed = self._execute(db, """DELETE FROM hosted_jobs
                WHERE id = ? AND owner = ? AND state IN ('complete','error')""", (identifier, owner))
            return removed.rowcount == 1

    def claim(self) -> dict | None:
        with self._connect() as db:
            now = time.time()
            pending = self._execute(db, """SELECT 1 FROM hosted_jobs WHERE state = 'queued'
                OR (state = 'running' AND lease_until <= ?) OR created <= ?
                UNION ALL SELECT 1 FROM hosted_admissions WHERE created <= ? LIMIT 1""",
                                    (now, now - _RETENTION, now - _RETENTION)).fetchone()
            if pending is None:
                return None
            now = self._lock_queue(db)
            self._sweep(db, now)
            if db.execute("SELECT 1 FROM hosted_jobs WHERE state = 'running' LIMIT 1").fetchone():
                return None
            row = db.execute(f"""SELECT {_PUBLIC_FIELDS} FROM hosted_jobs WHERE state = 'queued'
                ORDER BY created, id LIMIT 1""").fetchone()
            if row is None:
                return None
            token = secrets.token_urlsafe(24)
            self._execute(db, """UPDATE hosted_jobs SET state = 'running', updated = ?,
                lease_token = ?, lease_until = ? WHERE id = ?""",
                          (now, token, now + _LEASE, row["id"]))
        return {**self._decode(row), "state": "running", "updated": now, "lease_token": token}

    def heartbeat(self, identifier: str, lease_token: str) -> bool:
        with self._connect() as db:
            now = self._lock_queue(db)
            updated = self._execute(db, """UPDATE hosted_jobs SET lease_until = ? WHERE id = ? AND lease_token = ?
                AND state = 'running' AND lease_until > ? AND created > ?""",
                                    (now + _LEASE, identifier, lease_token, now, now - _RETENTION))
            return updated.rowcount == 1

    def finish(self, identifier: str, lease_token: str, *, result: dict | None = None, error: str | None = None) -> bool:
        if (result is None) == (error is None):
            raise ValueError("A finished analysis needs one result or error.")
        encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":")) if result is not None else None
        if encoded is not None and len(encoded) > _MAX_REPORT_BYTES:
            encoded, error = None, "Analysis produced more than the hosted report size limit."
        state = "error" if error is not None else "complete"
        error = error[:512] if error is not None else None
        with self._connect() as db:
            now = self._lock_queue(db)
            updated = self._execute(db, """UPDATE hosted_jobs SET state = ?, updated = ?, result = ?, error = ?,
                lease_token = NULL, lease_until = NULL WHERE id = ? AND lease_token = ? AND state = 'running'
                AND lease_until > ? AND created > ?""",
                                    (state, now, encoded, error, identifier, lease_token, now, now - _RETENTION))
            return updated.rowcount == 1
