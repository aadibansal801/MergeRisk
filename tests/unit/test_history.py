import sqlite3

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
