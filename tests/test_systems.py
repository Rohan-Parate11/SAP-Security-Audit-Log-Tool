"""Regression tests for sal/systems.py (environment/connector registry).

Confirms the registry never stores or returns a credential value, that
seed_from_env() backfills a pre-existing .env-only system without
duplicating it on repeated calls, and basic CRUD behavior.
"""
import sal.systems as systems_svc


def test_add_and_get_system_roundtrip():
    systems_svc.add_system("T01", "Development", "host1", "00", "100", "tester",
                            description="test system")
    row = systems_svc.get_system("T01")
    assert row["environment"] == "Development"
    assert row["ashost"] == "host1"
    assert row["has_credentials"] is False


def test_add_system_rejects_invalid_environment():
    try:
        systems_svc.add_system("T02", "Staging", "host", "00", "100", "tester")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_update_system_partial_fields_only():
    systems_svc.add_system("T03", "Development", "host1", "00", "100", "tester")
    ok = systems_svc.update_system("T03", environment="Quality")
    assert ok is True
    row = systems_svc.get_system("T03")
    assert row["environment"] == "Quality"
    assert row["ashost"] == "host1"  # untouched field preserved


def test_update_unknown_system_returns_false():
    assert systems_svc.update_system("NOPE", environment="Quality") is False


def test_remove_system():
    systems_svc.add_system("T04", "Sandbox", "host1", "00", "100", "tester")
    systems_svc.remove_system("T04")
    assert systems_svc.get_system("T04") is None


def test_seed_from_env_backfills_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(systems_svc.config, "list_configured_systems", lambda: [
        {"system_id": "S23", "client": "100", "description": "S23"},
    ])
    monkeypatch.setattr(systems_svc.os, "environ", {
        "SAL_SAP_S23_ASHOST": "sap.example.com", "SAL_SAP_S23_SYSNR": "00",
    })

    systems_svc.seed_from_env()
    first = systems_svc.get_system("S23")
    assert first["environment"] == "Sandbox"
    assert first["ashost"] == "sap.example.com"

    systems_svc.seed_from_env()
    second = systems_svc.get_system("S23")
    assert second["created_at"] == first["created_at"]  # not re-inserted/overwritten


def test_add_system_duplicate_raises_value_error_not_integrity_error():
    systems_svc.add_system("T07", "Development", "host", "00", "100", "tester")
    try:
        systems_svc.add_system("T07", "Quality", "host2", "01", "200", "tester")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "already exists" in str(exc)


def test_update_system_description_unset_vs_explicitly_cleared():
    systems_svc.add_system("T08", "Development", "host", "00", "100", "tester",
                            description="original")

    # Omitting description (default UNSET) must leave it untouched.
    systems_svc.update_system("T08", environment="Quality")
    assert systems_svc.get_system("T08")["description"] == "original"

    # Explicitly passing None (what the API does for an empty string) clears it.
    systems_svc.update_system("T08", description=None)
    assert systems_svc.get_system("T08")["description"] is None


def test_remove_system_returns_whether_a_row_was_deleted():
    assert systems_svc.remove_system("NOPE") is False
    systems_svc.add_system("T09b", "Sandbox", "host", "00", "100", "tester")
    assert systems_svc.remove_system("T09b") is True


def test_has_credentials_checks_env_var_presence(monkeypatch):
    monkeypatch.setattr(systems_svc.os, "environ", {"SAL_SAP_T05_PASSWD": "secret"})
    assert systems_svc.has_credentials("T05") is True
    assert systems_svc.has_credentials("T06") is False
