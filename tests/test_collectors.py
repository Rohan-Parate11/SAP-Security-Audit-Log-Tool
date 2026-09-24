"""Regression tests for sal/collectors/sm20.py (Phase B hardening).

Confirms collect_and_store() always finalizes its collection_runs row and
returns an error summary - never leaves the row stuck at "running" or lets
an exception escape - regardless of which exception type the underlying
fetch raises. Found live during Phase B testing: an unconfigured system's
config-lookup error was a plain RuntimeError, not a SapConnectionError, so
the old narrower except clause skipped finalization entirely and left a
real production row stuck at "running" forever.
"""
import sal.collectors.sm20 as sm20
from sal.storage.db import get_connection


def test_collect_and_store_finalizes_run_row_on_any_exception_type(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated non-SapConnectionError failure")

    monkeypatch.setattr(sm20, "fetch_events", boom)

    summary = sm20.collect_and_store(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
    )

    assert summary["status"] == "error"
    assert "simulated non-SapConnectionError failure" in summary["error"]

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, finished_at, error_message FROM collection_runs WHERE run_id = ?",
            (summary["run_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "error"
    assert row["finished_at"] is not None
    assert row["error_message"] == "simulated non-SapConnectionError failure"


def test_collect_and_store_still_reports_success_normally(monkeypatch):
    monkeypatch.setattr(sm20, "fetch_events", lambda *a, **kw: [])
    monkeypatch.setattr(sm20, "store_events", lambda rows, run_id: 0)

    summary = sm20.collect_and_store(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
    )

    assert summary["status"] == "success"
    assert summary["fetched"] == 0
    assert summary["inserted"] == 0

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, error_message FROM collection_runs WHERE run_id = ?",
            (summary["run_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "success"
    assert row["error_message"] is None


def test_collect_and_store_records_job_id_when_given(monkeypatch):
    monkeypatch.setattr(sm20, "fetch_events", lambda *a, **kw: [])
    monkeypatch.setattr(sm20, "store_events", lambda rows, run_id: 0)

    summary = sm20.collect_and_store(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101", job_id=42,
    )

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT job_id FROM collection_runs WHERE run_id = ?", (summary["run_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["job_id"] == 42


def test_collect_and_store_job_id_defaults_to_none(monkeypatch):
    """scripts/collect_sm20.py's CLI backfill path calls collect_and_store()
    directly, never through sal/jobs.py - job_id must stay NULL there
    (never raise for the omitted argument, and never accidentally inherit
    a stale value from some other call)."""
    monkeypatch.setattr(sm20, "fetch_events", lambda *a, **kw: [])
    monkeypatch.setattr(sm20, "store_events", lambda rows, run_id: 0)

    summary = sm20.collect_and_store(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
    )

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT job_id FROM collection_runs WHERE run_id = ?", (summary["run_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["job_id"] is None
