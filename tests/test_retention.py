"""Regression tests for sal/retention.py (data retention purge)."""
from datetime import datetime, timedelta, timezone

import sal.retention as retention
from sal.storage.db import get_connection


def _findings_ts(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _events_ts(days_ago: float) -> str:
    # Matches sal/collectors/sm20.py's event_timestamp() shape exactly
    # ("YYYY-MM-DD HH:MM:SS", no "T", no offset) - a mismatched shape here
    # once made every same-day row look eligible regardless of time-of-day.
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _insert_event(event_timestamp: str, counter: int = 1) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (source_system, client, instance, log_tstmp, counter, "
            "event_timestamp, inserted_at) VALUES ('S23', '100', 'X', ?, ?, ?, ?)",
            (event_timestamp, counter, event_timestamp, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_finding(finding_key: str, first_seen_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO findings (finding_key, rule_key, rule_label, severity, detected_at, "
            "summary, first_seen_at, last_seen_at) VALUES (?, 'r1', 'Rule 1', 'Low', ?, 's', ?, ?)",
            (finding_key, first_seen_at, first_seen_at, first_seen_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_preview_purge_counts_only_rows_past_retention():
    _insert_event(_events_ts(400), counter=1)  # past 365-day events retention
    _insert_event(_events_ts(10), counter=2)  # within retention
    _insert_finding("f-old", _findings_ts(365 * 8))  # past 7-year findings retention
    _insert_finding("f-new", _findings_ts(30))  # within retention

    preview = retention.preview_purge()

    assert preview["events_eligible"] == 1
    assert preview["findings_eligible"] == 1
    assert preview["events_retention_days"] == 365
    assert preview["findings_retention_days"] == 365 * 7


def test_preview_purge_keeps_event_on_the_cutoff_date_but_after_cutoff_time():
    # Regression for the format-mismatch bug: a naive "YYYY-MM-DD HH:MM:SS"
    # row on the same calendar date as the cutoff, but timestamped later in
    # the day, must NOT be treated as past-retention just because a lexical
    # string comparison used mismatched formats.
    events_cutoff, _ = retention._cutoffs()
    cutoff_dt = datetime.strptime(events_cutoff, "%Y-%m-%d %H:%M:%S")
    still_within_retention = (cutoff_dt + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    _insert_event(still_within_retention, counter=1)

    preview = retention.preview_purge()

    assert preview["events_eligible"] == 0


def test_run_purge_deletes_only_eligible_rows_and_logs_run():
    _insert_event(_events_ts(400), counter=1)
    _insert_event(_events_ts(10), counter=2)
    _insert_finding("f-old", _findings_ts(365 * 8))
    _insert_finding("f-new", _findings_ts(30))

    result = retention.run_purge(actor="tester")

    assert result["events_deleted"] == 1
    assert result["findings_deleted"] == 1

    conn = get_connection()
    try:
        remaining_events = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
        remaining_findings = conn.execute(
            "SELECT finding_key FROM findings"
        ).fetchall()
    finally:
        conn.close()

    assert remaining_events == 1
    assert [r["finding_key"] for r in remaining_findings] == ["f-new"]

    runs = retention.list_purge_runs()
    assert len(runs) == 1
    assert runs[0]["actor"] == "tester"
    assert runs[0]["events_deleted"] == 1
    assert runs[0]["findings_deleted"] == 1


def test_run_purge_with_nothing_eligible_still_logs_an_empty_run():
    _insert_event(_events_ts(10), counter=1)

    result = retention.run_purge(actor="system")

    assert result["events_deleted"] == 0
    assert result["findings_deleted"] == 0
    runs = retention.list_purge_runs()
    assert len(runs) == 1
    assert runs[0]["events_deleted"] == 0


def test_run_purge_does_not_touch_finding_whitelist():
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO finding_whitelist (rule_key, reason, created_by, created_at, expires_at) "
            "VALUES ('r1', 'reason', 'tester', ?, ?)",
            (_findings_ts(400), _findings_ts(-30)),
        )
        conn.commit()
    finally:
        conn.close()

    retention.run_purge(actor="system")

    conn = get_connection()
    try:
        remaining = conn.execute("SELECT COUNT(*) c FROM finding_whitelist").fetchone()["c"]
    finally:
        conn.close()
    assert remaining == 1


def test_list_purge_runs_orders_most_recent_first():
    retention.run_purge(actor="first")
    retention.run_purge(actor="second")

    runs = retention.list_purge_runs()
    assert [r["actor"] for r in runs] == ["second", "first"]
