import sqlite3
import os
import stat

import pytest

from mergerisk.history import History


def test_history_transactions_close_the_connection(tmp_path):
    history = History(tmp_path)
    with history.connect() as db:
        assert db.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")


def test_history_transactions_rollback_and_close_on_error(tmp_path):
    history = History(tmp_path)
    with pytest.raises(RuntimeError, match="abort"):
        with history.connect() as db:
            db.execute("INSERT INTO repositories VALUES ('id','path','name','now',NULL)")
            raise RuntimeError("abort")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    assert history.repositories() == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_history_creation_and_existing_database_permissions(tmp_path):
    directory = tmp_path / "state"
    store = History(directory)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    store.path.chmod(0o644)
    History(directory)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
