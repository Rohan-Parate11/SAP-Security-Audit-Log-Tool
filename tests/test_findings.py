"""Regression tests for sal/findings.py (Blueprint v2 Phase A).

Exercises finding identity, sync idempotency, disposition, and whitelist
suppression against a throwaway sqlite db (see conftest.py) using synthetic
finding dicts rather than real SAP data - these tests target the
persistence/workflow layer sync_findings() sits on top of, not the
detection rules themselves, so run_all_rules() is monkeypatched to return
fixed input.
"""
from datetime import datetime, timedelta, timezone

import sal.findings as findings_svc


def _finding(rule_key="test_rule", severity="High", user_id="U1",
             detected_at="2026-09-01T08:00:00+00:00", summary="synthetic finding",
             evidence=None, source_system="S23", client="100"):
    return {
        "rule_key": rule_key,
        "rule_label": rule_key.replace("_", " ").title(),
        "severity": severity,
        "source_system": source_system,
        "client": client,
        "user_id": user_id,
        "detected_at": detected_at,
        "summary": summary,
        "evidence": evidence or {},
    }


def test_finding_key_ignores_volatile_evidence_but_not_other_fields():
    base = _finding(evidence={"baseline_mean": 1.0, "ip": "10.0.0.1"})
    same_baseline_shifted = _finding(evidence={"baseline_mean": 9.9, "ip": "10.0.0.1"})
    different_ip = _finding(evidence={"baseline_mean": 1.0, "ip": "10.0.0.2"})

    assert findings_svc._finding_key(base) == findings_svc._finding_key(same_baseline_shifted)
    assert findings_svc._finding_key(base) != findings_svc._finding_key(different_ip)


def test_finding_key_ignores_role_refresh_checked_at():
    # Regression: out_of_context_transaction.py's evidence includes the
    # role-context refresh timestamp it was checked against, which changes
    # every day the refresh job runs even when the underlying condition
    # hasn't. Without this exclusion, sync_findings() would silently
    # create a brand-new "open" finding every day and discard whatever
    # disposition an analyst already made - caught by python-reviewer.
    day1 = _finding(rule_key="out_of_context_transaction",
                     evidence={"transaction_code": "SU01", "role_refresh_checked_at": "2026-09-09T01:00:00+00:00"})
    day2 = _finding(rule_key="out_of_context_transaction",
                     evidence={"transaction_code": "SU01", "role_refresh_checked_at": "2026-09-10T01:00:00+00:00"})
    different_tcode = _finding(rule_key="out_of_context_transaction",
                                evidence={"transaction_code": "PFCG", "role_refresh_checked_at": "2026-09-09T01:00:00+00:00"})

    assert findings_svc._finding_key(day1) == findings_svc._finding_key(day2)
    assert findings_svc._finding_key(day1) != findings_svc._finding_key(different_tcode)


def test_finding_key_ignores_directly_assigned_profile_fields():
    # Regression (FIND-07, UAT Round 2 retest): a user's directly-assigned
    # SAP profiles are a live, per-lookup value, not part of what makes this
    # finding "the same finding" - it can legitimately change (a profile
    # revoked), or, as happened here, the same underlying profile list gets
    # filtered differently after a code fix (T-* PFCG-generated profiles
    # excluded from the flag). Without this exclusion, sync_findings() would
    # spawn a brand-new "open" finding every time this shifted, rather than
    # refreshing the existing one (see the evidence-refresh test below).
    day1 = _finding(rule_key="out_of_context_transaction",
                     evidence={"transaction_code": "SU01",
                               "directly_assigned_profiles": ["T-1234ABCD", "SAP_ALL"],
                               "directly_assigned_profiles_error": None,
                               "has_broad_access_profile": True})
    day2_after_fix = _finding(rule_key="out_of_context_transaction",
                               evidence={"transaction_code": "SU01",
                                         "directly_assigned_profiles": ["SAP_ALL"],
                                         "directly_assigned_profiles_error": None,
                                         "has_broad_access_profile": True})
    different_tcode = _finding(rule_key="out_of_context_transaction",
                                evidence={"transaction_code": "PFCG",
                                          "directly_assigned_profiles": ["SAP_ALL"],
                                          "directly_assigned_profiles_error": None,
                                          "has_broad_access_profile": True})

    assert findings_svc._finding_key(day1) == findings_svc._finding_key(day2_after_fix)
    assert findings_svc._finding_key(day1) != findings_svc._finding_key(different_tcode)


def test_sync_findings_is_idempotent(monkeypatch):
    computed = [_finding(rule_key="login_time", user_id="U1"),
                _finding(rule_key="new_source", user_id="U2")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)

    first = findings_svc.sync_findings(system_id="S23", client="100")
    assert first == {"computed": 2, "new": 2}

    second = findings_svc.sync_findings(system_id="S23", client="100")
    assert second == {"computed": 2, "new": 0}

    total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert total == 2
    assert all(item["status"] == "open" for item in items)


def test_sync_findings_refreshes_evidence_and_summary_for_an_already_open_finding(monkeypatch):
    # Regression (FIND-07, UAT Round 2 retest): a finding already stored
    # before a code fix changed one of its volatile evidence fields must
    # pick up the corrected value on the next sync, not stay frozen at
    # whatever was first inserted - the real bug was an out-of-context
    # finding computed before the "T-* profiles are role-generated, not
    # directly assigned" fix kept showing the stale, T-*-including evidence
    # forever, since its finding_key never changed (directly_assigned_
    # profiles is denylisted from identity) but its stored evidence_json/
    # summary were never touched again either.
    stale = _finding(rule_key="out_of_context_transaction", user_id="U1",
                      summary="U1 ran SU01; also has T-1234ABCD and SAP_ALL directly assigned",
                      evidence={"transaction_code": "SU01",
                                "directly_assigned_profiles": ["T-1234ABCD", "SAP_ALL"],
                                "has_broad_access_profile": True})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [stale])
    first = findings_svc.sync_findings(system_id="S23", client="100")
    assert first == {"computed": 1, "new": 1}

    corrected = _finding(rule_key="out_of_context_transaction", user_id="U1",
                          summary="U1 ran SU01; also has SAP_ALL directly assigned",
                          evidence={"transaction_code": "SU01",
                                    "directly_assigned_profiles": ["SAP_ALL"],
                                    "has_broad_access_profile": True})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [corrected])
    second = findings_svc.sync_findings(system_id="S23", client="100")
    # Same finding_key (directly_assigned_profiles is denylisted from
    # identity) - no new row, just a refresh of the existing one.
    assert second == {"computed": 1, "new": 0}

    total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert total == 1
    assert items[0]["evidence"]["directly_assigned_profiles"] == ["SAP_ALL"]
    assert "T-1234ABCD" not in items[0]["summary"]


def test_sync_findings_refreshes_severity_for_an_already_open_finding(monkeypatch):
    # Regression: severity isn't part of finding_key's identity hash either
    # (same as summary/evidence_json above), so a rule-code change to what
    # severity a given finding_key computes to - e.g. sensitive_table_
    # access/data_export's real Medium-to-Low reclassification (2026-09-15,
    # "go with option b") - must reach an already-open finding on its next
    # sync, not just brand-new findings computed after the code changed.
    before = _finding(rule_key="data_export", user_id="U1", severity="Medium",
                       evidence={"bytes": "1024"})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [before])
    findings_svc.sync_findings(system_id="S23", client="100")
    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["severity"] == "Medium"

    after = _finding(rule_key="data_export", user_id="U1", severity="Low",
                      evidence={"bytes": "1024"})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [after])
    second = findings_svc.sync_findings(system_id="S23", client="100")
    assert second == {"computed": 1, "new": 0}  # same finding_key, no new row

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["severity"] == "Low"


def test_sync_findings_never_rewrites_evidence_for_a_terminal_disposition(monkeypatch):
    # Regression: a security-reviewer pass on the evidence-refresh fix above
    # caught that the first version refreshed summary/evidence_json
    # unconditionally, regardless of status - meaning a true_positive or
    # false_positive finding's evidence (what an analyst's actual disposition
    # decision was based on) could silently change out from under them on
    # every later collection job. Only 'open'/'whitelisted' findings are
    # eligible for the refresh; a terminal disposition must freeze both
    # fields exactly as they were at disposition time.
    stale = _finding(rule_key="out_of_context_transaction", user_id="U1", severity="High",
                      summary="U1 ran SU01; also has T-1234ABCD and SAP_ALL directly assigned",
                      evidence={"transaction_code": "SU01",
                                "directly_assigned_profiles": ["T-1234ABCD", "SAP_ALL"]})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [stale])
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    key = items[0]["finding_key"]
    assert findings_svc.dispose_finding(key, "true_positive", actor="qa_analyst") is True

    corrected = _finding(rule_key="out_of_context_transaction", user_id="U1", severity="Low",
                          summary="U1 ran SU01; also has SAP_ALL directly assigned",
                          evidence={"transaction_code": "SU01",
                                    "directly_assigned_profiles": ["SAP_ALL"]})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [corrected])
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "true_positive"
    assert items[0]["severity"] == "High"  # frozen at disposition time, not downgraded to Low
    assert items[0]["evidence"]["directly_assigned_profiles"] == ["T-1234ABCD", "SAP_ALL"]
    assert "T-1234ABCD" in items[0]["summary"]


def test_list_findings_accepts_multiple_values_and_user_id_contains(monkeypatch):
    """Excel-style column-header filters check multiple boxes at once for
    Severity/Rule/Status, and free-text-search for User - both new
    capabilities on top of the existing single-value filtering."""
    computed = [
        _finding(rule_key="login_time", severity="High", user_id="ALICE"),
        _finding(rule_key="new_source", severity="Medium", user_id="BOB"),
        _finding(rule_key="login_attack", severity="Low", user_id="CAROL"),
    ]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    total, items = findings_svc.list_findings(system_id="S23", client="100", severity=["High", "Low"])
    assert total == 2
    assert {i["severity"] for i in items} == {"High", "Low"}

    total, _items = findings_svc.list_findings(system_id="S23", client="100", rule=["login_time"])
    assert total == 1

    # A single string (not a list) must still work exactly as before.
    total, _items = findings_svc.list_findings(system_id="S23", client="100", severity="Medium")
    assert total == 1

    total, items = findings_svc.list_findings(system_id="S23", client="100", user_id="ali")
    assert total == 1
    assert items[0]["user_id"] == "ALICE"


def test_list_findings_by_finding_key_ignores_scope_and_other_filters(monkeypatch):
    # Regression: requested directly - the Activity page only ever showed
    # the opaque finding_key hash for a disposed finding, with no way back
    # to the actual finding. finding_key is a complete, unique identifier
    # on its own, so a lookup by it must work even if the caller's current
    # system/client selection (or any other filter) doesn't happen to
    # match - otherwise a link from Activity could silently return nothing.
    computed = [_finding(rule_key="login_time", severity="High", user_id="ALICE",
                          source_system="S23", client="100")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")
    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    key = items[0]["finding_key"]

    total, items = findings_svc.list_findings(
        finding_key=key, system_id="WRONG_SYS", client="999",
        rule=["new_source"], severity=["Low"], status=["false_positive"], user_id="nobody",
    )
    assert total == 1
    assert items[0]["finding_key"] == key
    assert items[0]["user_id"] == "ALICE"

    total, _items = findings_svc.list_findings(finding_key="does-not-exist")
    assert total == 0


def test_dispose_finding_persists_reason_and_actor(monkeypatch):
    computed = [_finding(rule_key="login_attack", user_id="U3")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    key = items[0]["finding_key"]

    ok = findings_svc.dispose_finding(
        key, "false_positive", actor="qa_analyst",
        reason_code="known_service_account", notes="expected batch job login",
    )
    assert ok is True

    _total, items = findings_svc.list_findings(status="false_positive")
    assert len(items) == 1
    assert items[0]["disposed_by"] == "qa_analyst"
    assert items[0]["reason_code"] == "known_service_account"
    assert items[0]["analyst_notes"] == "expected batch job login"
    assert items[0]["disposed_at"] is not None


def test_active_whitelist_suppresses_matching_finding(monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    findings_svc.add_whitelist(
        rule_key="shared_ip", reason="shared kiosk terminal", created_by="qa_analyst",
        expires_at=future, user_id="U4",
    )

    computed = [_finding(rule_key="shared_ip", user_id="U4")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "whitelisted"


def test_whitelist_added_after_finding_already_exists_still_suppresses_it(monkeypatch):
    """An analyst who whitelists something already flagged expects it to stop
    being open, not just prevent flagging future occurrences - the initial
    implementation only applied the whitelist check at INSERT time, so a
    whitelist entry created after the finding already existed silently did
    nothing on re-sync. Confirmed against real data during Phase A close-out
    (2026-09-09) before this fix.
    """
    computed = [_finding(rule_key="shared_ip", user_id="U7")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "open"

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    findings_svc.add_whitelist(
        rule_key="shared_ip", reason="added after the fact", created_by="qa_analyst",
        expires_at=future, user_id="U7",
    )
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "whitelisted"


def test_retroactive_whitelist_does_not_override_existing_disposition(monkeypatch):
    computed = [_finding(rule_key="shared_ip", user_id="U8")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    key = items[0]["finding_key"]
    findings_svc.dispose_finding(key, "true_positive", actor="qa_analyst",
                                  reason_code="confirmed_incident")

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    findings_svc.add_whitelist(
        rule_key="shared_ip", reason="unrelated later whitelist", created_by="qa_analyst",
        expires_at=future, user_id="U8",
    )
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "true_positive"


def test_expired_whitelist_does_not_suppress(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    findings_svc.add_whitelist(
        rule_key="shared_ip", reason="temporary exception, already expired",
        created_by="qa_analyst", expires_at=past, user_id="U5",
    )

    computed = [_finding(rule_key="shared_ip", user_id="U5")]
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: computed)
    findings_svc.sync_findings(system_id="S23", client="100")

    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert items[0]["status"] == "open"


def test_backfill_reshaped_incident_boundary_creates_separate_finding_not_silent_merge(monkeypatch):
    """Pins the accepted-for-v1 instability documented in findings.py's module
    docstring: if a later collection backfills an event between two
    previously-adjacent ones, an incident-grouping rule's boundary timestamp
    (part of the identity hash) can shift. That does not silently merge into
    the original finding - it becomes a second, distinct finding, and the
    original is left open rather than auto-resolved. This test exists so
    that behavior stays a deliberate, verified choice rather than prose that
    quietly stops being true.
    """
    original = _finding(rule_key="mass_user_changes", user_id="U6",
                         detected_at="2026-09-01T10:00:00+00:00",
                         evidence={"user_count": 12})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [original])
    findings_svc.sync_findings(system_id="S23", client="100")

    reshaped = _finding(rule_key="mass_user_changes", user_id="U6",
                         detected_at="2026-09-01T09:58:00+00:00",
                         evidence={"user_count": 13})
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [reshaped])
    findings_svc.sync_findings(system_id="S23", client="100")

    total, items = findings_svc.list_findings(system_id="S23", client="100")
    assert total == 2
    assert {item["status"] for item in items} == {"open"}
