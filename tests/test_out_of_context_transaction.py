"""Regression tests for sal/rules/out_of_context_transaction.py (use case #14).

authorized_tcodes_for_user()/latest_refresh()/directly_assigned_profiles()
are monkeypatched throughout - these tests target the rule's own logic
(three-state role coverage, plus the directly-assigned-profile note added
on top of it), not sal/role_context.py's own storage/live-RFC logic (see
tests/test_role_context.py for that). Every test monkeypatches
directly_assigned_profiles even when it isn't the thing under test, since
otherwise it would attempt a real SAP RFC connection during the rule's
enrichment step.
"""
from datetime import datetime, timezone

import sal.rules.out_of_context_transaction as out_of_context
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


def test_covered_by_current_role_produces_no_finding(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SU01"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    assert out_of_context.detect_out_of_context_transactions() == []
    assert out_of_context.detect_out_of_context_no_role_data() == []


def test_role_exists_but_does_not_cover_tcode_is_out_of_context(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(
        out_of_context, "latest_refresh",
        lambda *a, **kw: {"status": "success", "run_at": "2026-09-10T01:00:00+00:00"},
    )
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert findings[0]["rule"] == "out_of_context_transaction"
    assert findings[0]["severity"] == "High"
    assert findings[0]["evidence"]["no_role_data"] is False
    assert "not currently assigned via any of their SAP roles" in findings[0]["summary"]
    assert "2026-09-10T01:00:00+00:00" in findings[0]["summary"]
    assert findings[0]["evidence"]["has_broad_access_profile"] is False
    assert findings[0]["evidence"]["directly_assigned_profiles"] == []

    # Must not also appear under the no-role-data rule
    assert out_of_context.detect_out_of_context_no_role_data() == []


def test_zero_role_rows_is_a_distinct_no_role_data_finding(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    assert out_of_context.detect_out_of_context_transactions() == []

    findings = out_of_context.detect_out_of_context_no_role_data()
    assert len(findings) == 1
    assert findings[0]["rule"] == "out_of_context_no_role_data"
    assert findings[0]["evidence"]["no_role_data"] is True
    assert "currently has no SAP role assignments on record" in findings[0]["summary"]


def test_non_critical_transaction_is_never_flagged(monkeypatch):
    add_critical_transaction("SU01")  # SU01 critical, SE38 is not in this test's catalogue
    _insert_au3_event("U1", "SE38")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    assert out_of_context.detect_out_of_context_transactions() == []
    assert out_of_context.detect_out_of_context_no_role_data() == []


def test_empty_critical_transactions_catalogue_produces_no_findings(monkeypatch):
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    assert out_of_context.detect_out_of_context_transactions() == []
    assert out_of_context.detect_out_of_context_no_role_data() == []


def test_the_audit_drift_scenario_old_event_flagged_after_role_removed(monkeypatch):
    """Owner-confirmed audit scenario (2026-09-10): a user ran a critical
    transaction weeks ago while still covered; the role has since been
    removed. The event stays in `events` (nothing about it changes), so
    re-evaluating the rule with today's (now role-less) authorization
    state must surface it as a finding - this is the whole point of
    checking current authorization against retained history, not just
    newly-collected events.
    """
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")  # the historical event, unrelated to when the role was removed
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: None)
    monkeypatch.setattr(
        out_of_context, "latest_refresh",
        lambda *a, **kw: {"status": "success", "run_at": "2026-09-10T01:00:00+00:00"},
    )
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: ([], None))

    findings = out_of_context.detect_out_of_context_no_role_data()
    assert len(findings) == 1
    assert findings[0]["user_id"] == "U1"
    assert findings[0]["evidence"]["transaction_code"] == "SU01"


# ---- Directly-assigned profile enrichment (requested directly: a role-only
# ---- finding shouldn't require a separate manual lookup to notice a
# ---- directly-assigned profile - especially SAP_ALL/SAP_NEW - might also
# ---- be granting the same access) --------------------------------------

def test_out_of_context_finding_notes_possible_direct_profile_coverage(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", lambda *a, **kw: (["Z_CUSTOM"], None))

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert findings[0]["evidence"]["directly_assigned_profiles"] == ["Z_CUSTOM"]
    assert findings[0]["evidence"]["has_broad_access_profile"] is False
    assert "directly to their user master record" in findings[0]["summary"]


def test_out_of_context_finding_flags_sap_all_directly_assigned(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(
        out_of_context, "directly_assigned_profiles", lambda *a, **kw: (["SAP_ALL", "Z_OTHER"], None)
    )

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert findings[0]["evidence"]["has_broad_access_profile"] is True
    assert findings[0]["evidence"]["directly_assigned_profiles"] == ["SAP_ALL", "Z_OTHER"]
    assert "SAP_ALL" in findings[0]["summary"]
    assert "far broader access" in findings[0]["summary"]


def test_out_of_context_finding_handles_profile_lookup_failure_gracefully(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(
        out_of_context, "directly_assigned_profiles", lambda *a, **kw: (None, "Timed out after 30s waiting for SAP")
    )

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert findings[0]["evidence"]["directly_assigned_profiles"] is None
    assert findings[0]["evidence"]["directly_assigned_profiles_error"] == "Timed out after 30s waiting for SAP"
    assert findings[0]["evidence"]["has_broad_access_profile"] is False
    assert "could not check" in findings[0]["summary"]


def test_role_generated_t_dash_profiles_are_excluded_from_the_flag(monkeypatch):
    """Requested directly after a live finding flagged a T-* profile as
    "directly assigned" when it was actually just the auto-generated
    profile for a role the user legitimately holds - SUSR_GET_PROFILES_OF_USER_RFC
    can't tell the two apart, so this excludes anything matching SAP's own
    T-* naming convention for PFCG-generated profiles."""
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(
        out_of_context, "directly_assigned_profiles",
        lambda *a, **kw: (["T-A1B2C3D4", "T-DEADBEEF"], None),
    )

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert findings[0]["evidence"]["directly_assigned_profiles"] == []
    assert findings[0]["evidence"]["has_broad_access_profile"] is False
    assert "T-A1B2C3D4" not in findings[0]["summary"]


def test_t_dash_profiles_do_not_hide_a_genuinely_direct_profile(monkeypatch):
    add_critical_transaction("SU01")
    _insert_au3_event("U1", "SU01")
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: {"SE16N"})
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(
        out_of_context, "directly_assigned_profiles",
        lambda *a, **kw: (["T-A1B2C3D4", "SAP_ALL", "Z_CUSTOM_DIRECT"], None),
    )

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 1
    assert set(findings[0]["evidence"]["directly_assigned_profiles"]) == {"SAP_ALL", "Z_CUSTOM_DIRECT"}
    assert findings[0]["evidence"]["has_broad_access_profile"] is True
    assert "SAP_ALL" in findings[0]["summary"]


def test_profile_lookup_is_cached_per_user_within_one_detect_call(monkeypatch):
    """sync_findings() re-evaluates every retained event on every run - if
    two critical-transaction events belong to the same user, the live
    profile RFC call must fire once for that user, not once per event."""
    add_critical_transaction("SU01")
    add_critical_transaction("SE16N")
    _insert_au3_event("U1", "SU01", counter=1)
    _insert_au3_event("U1", "SE16N", counter=2)
    monkeypatch.setattr(out_of_context, "authorized_tcodes_for_user", lambda *a, **kw: set())
    monkeypatch.setattr(out_of_context, "latest_refresh", lambda *a, **kw: None)

    calls = []

    def _fake_lookup(system_id, user_id):
        calls.append(user_id)
        return [], None

    monkeypatch.setattr(out_of_context, "directly_assigned_profiles", _fake_lookup)

    findings = out_of_context.detect_out_of_context_transactions()
    assert len(findings) == 2
    assert calls == ["U1"]  # one live lookup, reused for the second event
