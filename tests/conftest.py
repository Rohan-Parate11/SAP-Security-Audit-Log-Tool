"""Shared fixtures for the SAL test suite.

Redirects sal.storage.db at a throwaway sqlite file per test so these tests
never touch data/sal.db - the real, ~111K-event pilot database.
"""
import pytest

from sal.storage import db as db_module


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test_sal.db")
    db_module.init_schema()
    yield
