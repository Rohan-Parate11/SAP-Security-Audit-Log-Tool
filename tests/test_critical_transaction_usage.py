"""Regression tests for sal/rules/critical_transaction_usage.py.

Requested directly: "I want that all the critical transactions be always
be marked as finding even if they are a part of user's role or profile
assignment." Unlike sal/rules/out_of_context_transaction.py, this rule
calls no role/profile lookup at all - there is nothing to monkeypatch,
and that absence is itself the point: it must fire on every matching
event unconditionally, first occurrence or five-hundredth, authorized or
not.
"""
from datetime import datetime, timezone

import sal.rules.critical_transaction_usage as critical_usage
from sal.catalogues import add_critical_transaction
from sal.storage.db import get_connection


def _insert_au3_event(user_id: str, tcode: str, system_id="S23", client="100",
                       counter: int = 1) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (source_system, client, instance, log_tstmp, counter, "
            "event_timestamp, user_id, msg_code, transaction_code, inserted_at) "
            "VALUES (?, ?, 'X', ?, ?, ?, ?, 'AU3', ?, ?)",
            (system_id, client, ts, counter, ts, user_id, tcode, ts),
        )
        conn.commit()
    finally:
        conn.close()
    return ts


def test_critical_transaction_run_produces_a_high_severity_finding():
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")

    findings = critical_usage.detect_critical_transaction_usage()
    assert len(findings) == 1
    assert findings[0]["rule"] == "critical_transaction_usage"
    assert findings[0]["severity"] == "High"
    assert findings[0]["user_id"] == "U1"
    assert findings[0]["evidence"]["transaction_code"] == "SU01"
    assert "SU01" in findings[0]["summary"]


def test_fires_on_every_occurrence_not_just_the_first():
    """The defining difference from first_time_transaction.py's
    first_time_sensitive_transaction (which never fires twice for the
    same user+tcode): three runs of the same critical tcode by the same
    user must produce three separate findings here, not one."""
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01", counter=1)
    _insert_au3_event("U1", "SU01", counter=2)
    _insert_au3_event("U1", "SU01", counter=3)

    findings = critical_usage.detect_critical_transaction_usage()
    assert len(findings) == 3
    assert all(f["rule"] == "critical_transaction_usage" for f in findings)


def test_fires_with_no_role_or_profile_check_at_all(monkeypatch):
    """Confirms there's genuinely no authorization gate here - even if
    sal.role_context were to report full coverage for this exact tcode,
    this rule doesn't call it, so it can't be suppressed by it. Patching
    a function this module never imports/calls and asserting the finding
    still appears is the proof this rule is unconditional, not just
    "currently passing because no role data exists"."""
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    import sal.role_context as role_context
    monkeypatch.setattr(role_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SU01"})

    findings = critical_usage.detect_critical_transaction_usage()
    assert len(findings) == 1


def test_multiple_users_each_get_their_own_finding():
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    _insert_au3_event("U2", "SU01")

    findings = critical_usage.detect_critical_transaction_usage()
    assert {f["user_id"] for f in findings} == {"U1", "U2"}


def test_non_critical_transaction_is_never_flagged():
    add_critical_transaction("SU01")  # SU01 critical, SE38 is not in this test's catalogue
    _insert_au3_event("U1", "SE38")

    assert critical_usage.detect_critical_transaction_usage() == []


def test_empty_critical_transactions_catalogue_produces_no_findings():
    _insert_au3_event("U1", "SU01")

    assert critical_usage.detect_critical_transaction_usage() == []
