"""Regression tests for sal/storage/db.py's init_schema() memoization.

init_schema() used to re-run the full CREATE TABLE/INDEX script plus several
PRAGMA table_info() migration checks on a brand-new sqlite3 connection every
single time it was called - and it's called at the top of ~28 read/write
functions across the codebase, several of which fan out into dozens of calls
per single request (see sal/web/api.py's dashboard()). It's now memoized on
DB_PATH so repeated calls for the same path are a no-op after the first real
run - these tests pin that behavior and the two correctness gotchas that
memoization has to respect:

1. tests/conftest.py's isolated_db fixture points DB_PATH at a fresh tmp_path
   file per test function and calls init_schema() itself - so the cache must
   key on DB_PATH's *current value*, not a bare "did this ever run" flag, or
   every test after the first would get a table-less DB.
2. scripts/collect_sm20.py is a standalone CLI entrypoint that never goes
   through sal/web/__init__.py's create_app() - a fresh data/sal.db must
   still get its schema created the first time init_schema() sees that path.
"""
import sqlite3
import threading
import time

from sal.storage import db as db_module


def test_init_schema_is_a_noop_for_a_path_already_initialized(monkeypatch):
    # tests/conftest.py's isolated_db autouse fixture already called
    # init_schema() once for the current (per-test) DB_PATH before this test
    # body runs, so the module-level cache should already be primed for it.
    assert db_module._schema_ready_for == db_module.DB_PATH

    # sqlite3.Connection is a C extension type and can't be monkeypatched
    # directly (setattr on the class raises TypeError), so spy on
    # _ensure_column() instead - a plain Python function that init_schema()
    # only reaches if it actually runs the real CREATE/migration pass.
    calls = []
    monkeypatch.setattr(
        db_module, "_ensure_column",
        lambda *a, **kw: calls.append(1),
    )

    db_module.init_schema()  # same DB_PATH as isolated_db already initialized

    assert calls == []  # short-circuited - no redundant migration pass re-run


def test_init_schema_reruns_for_a_genuinely_new_db_path(monkeypatch, tmp_path):
    # Simulates both gotchas at once: a DB_PATH this process has never seen
    # (mirrors scripts/collect_sm20.py's fresh-database case) that also
    # differs from whatever isolated_db most recently initialized (mirrors
    # conftest.py moving DB_PATH to a new tmp_path every test function).
    new_path = tmp_path / "brand_new_sal.db"
    assert db_module._schema_ready_for != new_path
    monkeypatch.setattr(db_module, "DB_PATH", new_path)

    db_module.init_schema()

    assert db_module._schema_ready_for == new_path
    conn = db_module.get_connection()
    try:
        tables = {
            row["name"] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert {"events", "findings", "collection_runs", "systems"} <= tables


def test_init_schema_does_not_cache_a_failed_run(monkeypatch, tmp_path):
    """If a migration statement blew up partway through, the path must not
    be marked ready - the next call should retry rather than silently
    treating a half-initialized database as done.
    """
    new_path = tmp_path / "will_fail_sal.db"
    monkeypatch.setattr(db_module, "DB_PATH", new_path)

    def boom(self, table, column, coltype):
        raise sqlite3.OperationalError("simulated failure")

    monkeypatch.setattr(db_module, "_ensure_column", boom)

    try:
        db_module.init_schema()
    except sqlite3.OperationalError:
        pass

    assert db_module._schema_ready_for != new_path


def test_get_connection_waits_out_a_concurrent_writer_instead_of_erroring():
    """Regression: sync_findings() holds one uncommitted write transaction
    open for its whole run (no incremental commits, and documented
    elsewhere at ~98s for a full day's re-evaluation). Every route in this
    app - including a plain GET, via its own audit.record() call at the
    end - also writes, on its own separate connection. Two writers can't
    both hold SQLite's RESERVED/EXCLUSIVE lock at once: with Python's
    sqlite3 default 5s busy timeout, a second writer racing a sync/refresh/
    purge that runs anywhere near that long raised an uncaught "database is
    locked" OperationalError, surfacing to the browser as an unexplained
    500 (found via a UAT report of an intermittent failure while
    navigating/switching themes - it just happened to coincide with a sync
    or refresh still running). Confirmed NOT a reader-vs-writer issue first:
    a plain SELECT sees the pre-transaction on-disk snapshot instantly in
    SQLite's default rollback-journal mode, no wait at all - it's writer-
    vs-writer contention. get_connection() now passes a much longer
    timeout - this pins that a second writer blocked for longer than the
    *old* 5s default now waits it out instead of erroring.
    """
    setup = db_module.get_connection()
    setup.execute("CREATE TABLE IF NOT EXISTS _lock_regression_test (id INTEGER)")
    setup.commit()
    setup.close()

    release_after = 5.5  # longer than sqlite3's old 5s default busy timeout
    # sqlite3.Connection objects can't cross threads (check_same_thread),
    # so the first writer opens and holds its own connection entirely
    # inside the background thread - the only thing shared with the main
    # thread is writer_ready, which gates the second writer until the
    # first one's lock is actually held.
    writer_ready = threading.Event()

    def hold_write_lock_then_release():
        writer = db_module.get_connection()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO _lock_regression_test VALUES (1)")  # uncommitted - holds the lock
        writer_ready.set()
        time.sleep(release_after)
        writer.commit()
        writer.close()

    t = threading.Thread(target=hold_write_lock_then_release)
    t.start()
    try:
        writer_ready.wait(timeout=5)
        started = time.monotonic()
        second_writer = db_module.get_connection()
        try:
            second_writer.execute("BEGIN IMMEDIATE")  # must wait for the first writer's lock
            second_writer.execute("INSERT INTO _lock_regression_test VALUES (2)")
            second_writer.commit()
        finally:
            second_writer.close()
        elapsed = time.monotonic() - started
    finally:
        t.join()

    assert elapsed >= release_after - 0.1  # actually waited for the lock, not a lucky race

    verify = db_module.get_connection()
    try:
        rows = verify.execute("SELECT id FROM _lock_regression_test ORDER BY id").fetchall()
    finally:
        verify.close()
    assert [r["id"] for r in rows] == [1, 2]  # both writes landed
