"""Regression tests for sal/rules/export.py (use case #8) - sensitive
table access and data export detection. This module had no direct test
coverage before this file; written alongside a real severity change
(display-only table access and uncorrelated exports downgraded from
Medium to Low, requested directly - "have we configured any findings
under low category?" / "go with option b") rather than shipping that
change untested.
"""
from datetime import datetime, timedelta, timezone

import sal.rules.export as export_rule
from sal.catalogues import add_sensitive_table
from sal.storage.db import get_connection


def _insert_event(user_id: str, msg_code: str, param1=None, param2=None, param3=None,
                   when: datetime | None = None, system_id="S23", client="100",
                   counter: int = 1) -> str:
    ts = (when or datetime.now(timezone.utc)).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (source_system, client, instance, log_tstmp, counter, "
            "event_timestamp, user_id, msg_code, param1, param2, param3, inserted_at) "
            "VALUES (?, ?, 'X', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (system_id, client, ts, counter, ts, user_id, msg_code, param1, param2, param3, ts),
        )
        conn.commit()
    finally:
        conn.close()
    return ts


# ---- sensitive_table_access ------------------------------------------------

def test_display_access_is_low_severity():
    add_sensitive_table("USR02")
    _insert_event("U1", "DU9", param1="USR02", param2="03")  # 03 = display

    findings = export_rule.detect_sensitive_table_access()
    assert len(findings) == 1
    assert findings[0]["rule"] == "sensitive_table_access"
    assert findings[0]["severity"] == "Low"


def test_change_or_delete_access_is_high_severity():
    add_sensitive_table("USR02")
    _insert_event("U1", "DU9", param1="USR02", param2="02", counter=1)  # 02 = change
    _insert_event("U1", "DU9", param1="USR02", param2="06", counter=2)  # 06 = delete

    findings = export_rule.detect_sensitive_table_access()
    assert len(findings) == 2
    assert all(f["severity"] == "High" for f in findings)


def test_non_sensitive_table_is_never_flagged():
    add_sensitive_table("USR02")  # USR02 sensitive, ZFOO is not in this test's catalogue
    _insert_event("U1", "DU9", param1="ZFOO", param2="03")

    assert export_rule.detect_sensitive_table_access() == []


def test_empty_sensitive_tables_catalogue_produces_no_findings():
    _insert_event("U1", "DU9", param1="USR02", param2="03")

    assert export_rule.detect_sensitive_table_access() == []


# ---- data_export / sensitive_data_export -----------------------------------

def test_uncorrelated_export_is_low_severity_data_export():
    _insert_event("U1", "AUY", param1="1024", param3="/tmp/out.csv")

    findings = export_rule.detect_data_exports()
    assert len(findings) == 1
    assert findings[0]["rule"] == "data_export"
    assert findings[0]["severity"] == "Low"


def test_export_correlated_with_prior_sensitive_access_is_high_severity():
    add_sensitive_table("USR02")
    accessed_at = datetime.now(timezone.utc)
    _insert_event("U1", "DU9", param1="USR02", param2="03", when=accessed_at, counter=1)
    _insert_event("U1", "AUY", param1="1024", param3="/tmp/out.csv",
                  when=accessed_at + timedelta(minutes=5), counter=2)

    findings = export_rule.detect_data_exports()
    assert len(findings) == 1
    assert findings[0]["rule"] == "sensitive_data_export"
    assert findings[0]["severity"] == "High"
    assert findings[0]["evidence"]["correlated_table"] == "USR02"


def test_export_outside_correlation_window_falls_back_to_low_data_export():
    add_sensitive_table("USR02")
    accessed_at = datetime.now(timezone.utc)
    _insert_event("U1", "DU9", param1="USR02", param2="03", when=accessed_at, counter=1)
    _insert_event("U1", "AUY", param1="1024", param3="/tmp/out.csv",
                  when=accessed_at + timedelta(minutes=20), counter=2)  # past the 15-min window

    findings = export_rule.detect_data_exports()
    assert len(findings) == 1
    assert findings[0]["rule"] == "data_export"
    assert findings[0]["severity"] == "Low"
