"""Regression tests for sal/audit_config.py (Blueprint v2, Phase D).

_fetch_raw_config() is monkeypatched throughout - these tests target the
parsing/persistence/coverage logic, not a live RFC call. The real FM
(RSAU_API_GET_AUDIT_CONFIG) was validated live against S23 during Phase D
planning; that validation is not repeated by these tests.
"""
import concurrent.futures

import sal.audit_config as audit_config


def _raw_config(enabled="X", slots=None):
    return {"ED_ENABLE": enabled, "ET_SLOT_INFO": slots or []}


def _slot(profname="$DYN$", classes=None, severity_low="X"):
    classes = classes or []
    slot = {c: ("X" if c in classes else "") for c in audit_config._CLASS_FIELDS}
    slot.update({"PROFNAME": profname, "STATUS": "X", "SEVERITY_LOW": severity_low,
                 "SEVERITY_MED": "", "SEVERITY_HGH": "", "MANDT": "*", "UNAME": "*"})
    return slot


def test_check_audit_config_success_parses_slots_and_persists(monkeypatch):
    raw = _raw_config(slots=[_slot(classes=["CLASS_LOGIN", "CLASS_TCD"])])
    monkeypatch.setattr(audit_config, "_fetch_raw_config", lambda system_id: raw)

    result = audit_config.check_audit_config("S23", "100", actor="tester")

    assert result["status"] == "success"
    assert result["enabled"] is True
    assert result["slots"][0]["active_classes"] == ["CLASS_LOGIN", "CLASS_TCD"]

    snapshot = audit_config.latest_snapshot("S23", "100")
    assert snapshot["status"] == "success"
    assert snapshot["parsed_slots"][0]["active_classes"] == ["CLASS_LOGIN", "CLASS_TCD"]


def test_check_audit_config_timeout_still_persists_a_snapshot(monkeypatch):
    def _raise_timeout(system_id, client, timeout):
        # Real _run_with_timeout only clears _inflight via _on_done, once
        # the abandoned background thread actually finishes - simulate
        # that happening (immediately, for this test) rather than leaving
        # the (system_id, client) key stuck for every later test.
        audit_config._inflight.discard((system_id, client))
        raise concurrent.futures.TimeoutError()

    monkeypatch.setattr(audit_config, "_run_with_timeout", _raise_timeout)

    result = audit_config.check_audit_config("S23", "100", actor="tester")

    assert result["status"] == "error"
    assert "Timed out" in result["error"]
    snapshot = audit_config.latest_snapshot("S23", "100")
    assert snapshot["status"] == "error"
    assert snapshot["enabled"] is None


def test_check_audit_config_rejects_a_duplicate_in_flight_check(monkeypatch):
    # _inflight is only cleared by _run_with_timeout's done-callback, which
    # never fires here since _run_with_timeout itself is replaced - this
    # simulates "a check is already running" without real threading.
    monkeypatch.setattr(audit_config, "_inflight", {("S23", "100")})

    result = audit_config.check_audit_config("S23", "100", actor="tester")

    assert result["status"] == "error"
    assert "already in progress" in result["error"]


def test_latest_snapshot_normalizes_enabled_to_a_real_bool(monkeypatch):
    raw = _raw_config(enabled="X", slots=[_slot(classes=["CLASS_LOGIN"])])
    monkeypatch.setattr(audit_config, "_fetch_raw_config", lambda system_id: raw)
    audit_config.check_audit_config("S23", "100", actor="tester")

    snapshot = audit_config.latest_snapshot("S23", "100")
    assert snapshot["enabled"] is True
    assert isinstance(snapshot["enabled"], bool)  # not the raw sqlite INTEGER (1)


def test_rule_coverage_has_no_drift_from_the_real_rule_registry():
    from sal.rules import RULES
    assert set(audit_config.RULE_COVERAGE) == {key for key, _label, _fn in RULES}


def test_check_audit_config_generic_exception_still_persists_a_snapshot(monkeypatch):
    def _boom(system_id):
        raise RuntimeError("simulated RFC failure")

    monkeypatch.setattr(audit_config, "_fetch_raw_config", _boom)

    result = audit_config.check_audit_config("S23", "100", actor="tester")

    assert result["status"] == "error"
    assert "simulated RFC failure" in result["error"]
    snapshot = audit_config.latest_snapshot("S23", "100")
    assert snapshot["status"] == "error"
    assert snapshot["error_message"] == "simulated RFC failure"


def test_coverage_gaps_reports_every_rule_unverified_with_no_snapshot():
    gaps = audit_config.coverage_gaps("S23", "100")
    assert len(gaps) == len(audit_config.RULE_COVERAGE)
    assert all(g["unverified"] for g in gaps)


def test_coverage_gaps_none_when_all_required_classes_active(monkeypatch):
    all_classes = list(audit_config._CLASS_FIELDS)
    raw = _raw_config(slots=[_slot(classes=all_classes)])
    monkeypatch.setattr(audit_config, "_fetch_raw_config", lambda system_id: raw)
    audit_config.check_audit_config("S23", "100", actor="tester")

    gaps = audit_config.coverage_gaps("S23", "100")
    assert gaps == []


def test_coverage_gaps_flags_specific_missing_class(monkeypatch):
    # Only CLASS_LOGIN active - CLASS_USER (mass_user_changes) and
    # CLASS_TCD (unusual_transaction, etc.) should show as gaps.
    raw = _raw_config(slots=[_slot(classes=["CLASS_LOGIN"])])
    monkeypatch.setattr(audit_config, "_fetch_raw_config", lambda system_id: raw)
    audit_config.check_audit_config("S23", "100", actor="tester")

    gaps = {g["rule_key"]: g for g in audit_config.coverage_gaps("S23", "100")}
    assert "login_attack" not in gaps  # CLASS_LOGIN is active
    assert "mass_user_changes" in gaps
    assert gaps["mass_user_changes"]["missing_classes"] == ["CLASS_USER"]
    assert "unusual_transaction" in gaps
    assert gaps["unusual_transaction"]["missing_classes"] == ["CLASS_TCD"]


def test_required_classes_for_rule_unknown_rule_returns_empty_set():
    assert audit_config.RULE_COVERAGE.get("not_a_real_rule") is None
    from sal.rules._coverage import required_classes_for_rule
    assert required_classes_for_rule("not_a_real_rule") == set()
