"""Regression tests for sal/web/api.py's /credentials routes (the central
credential store's HTTP surface - requested directly, 2026-09-16, HOME-02).

Uses "ZZTEST" as the system_id, not "S23" - see tests/test_credentials.py's
own module docstring for why (the real .env's SAL_SAP_S23_* values leak
into the process environment for the whole pytest run).
"""
import pytest
from cryptography.fernet import Fernet

import sal.systems as systems_svc
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("SAL_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _add_system():
    systems_svc.add_system("ZZTEST", "Development", "sapdev.example.com", "00", "100", "tester")


def test_list_credentials_reports_source_per_system(monkeypatch):
    monkeypatch.delenv("SAL_SAP_ZZTEST_PASSWD", raising=False)
    _add_system()
    client = _client()

    resp = client.get("/api/credentials")
    items = {i["system_id"]: i["source"] for i in resp.get_json()["items"]}
    assert items["ZZTEST"] == "missing"

    monkeypatch.setenv("SAL_SAP_ZZTEST_PASSWD", "envpass")
    resp = client.get("/api/credentials")
    items = {i["system_id"]: i["source"] for i in resp.get_json()["items"]}
    assert items["ZZTEST"] == "env"

    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})
    resp = client.get("/api/credentials")
    items = {i["system_id"]: i["source"] for i in resp.get_json()["items"]}
    assert items["ZZTEST"] == "central"


def test_set_credential_requires_known_system():
    client = _client()
    resp = client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})
    assert resp.status_code == 404


def test_set_and_get_credential_round_trip_and_audit_logged():
    _add_system()
    client = _client()

    set_resp = client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})
    assert set_resp.status_code == 200

    get_resp = client.get("/api/credentials/ZZTEST")
    data = get_resp.get_json()
    assert data["rfc_user"] == "SAL_RFC"
    assert data["password"] == "hunter2"

    from sal import audit
    total, entries = audit.list_entries(action="credential_view", system_id="ZZTEST")
    assert total == 1
    assert entries[0]["source_system"] == "ZZTEST"

    set_total, _ = audit.list_entries(action="credential_set", system_id="ZZTEST")
    assert set_total == 1


def test_get_credential_404_when_nothing_stored():
    _add_system()
    client = _client()
    resp = client.get("/api/credentials/ZZTEST")
    assert resp.status_code == 404


def test_set_credential_rejects_empty_fields():
    _add_system()
    client = _client()
    resp = client.post("/api/credentials/ZZTEST", json={"rfc_user": "", "password": "hunter2"})
    assert resp.status_code == 400
    resp = client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": ""})
    assert resp.status_code == 400


def test_get_credential_returns_clean_error_on_decrypt_failure(monkeypatch):
    """Regression (security-reviewer, HIGH): a decrypt failure (e.g. the
    encryption key rotated/changed since the password was saved) must
    return a clean JSON error, not raise uncaught - this app runs with
    debug=True unconditionally (run.py), so an unhandled exception here
    would surface Werkzeug's traceback page, which prints local
    variables including _fernet()'s own key value, with no
    credential_view audit entry recorded at all (the exception fires
    before that line ever runs).
    """
    _add_system()
    client = _client()
    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})

    monkeypatch.setenv("SAL_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    resp = client.get("/api/credentials/ZZTEST")
    assert resp.status_code == 503
    assert resp.get_json()["ok"] is False

    from sal import audit
    total, _ = audit.list_entries(action="credential_view", system_id="ZZTEST")
    assert total == 0


def test_get_credential_response_is_not_cacheable():
    _add_system()
    client = _client()
    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})
    resp = client.get("/api/credentials/ZZTEST")
    assert resp.headers.get("Cache-Control") == "no-store"


def test_delete_system_also_removes_its_stored_credential():
    """Regression (security-reviewer, MEDIUM): otherwise the row survives
    indefinitely - invisible in the Password Manager's list (which only
    iterates currently-registered systems) yet still fetchable by direct
    API call, and silently reactivated with no new credential_set audit
    entry if a system with the same system_id is ever re-added later.
    """
    _add_system()
    client = _client()
    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})

    resp = client.delete("/api/systems/ZZTEST")
    assert resp.status_code == 200

    import sal.credentials as credentials
    assert credentials.has_stored_credential("ZZTEST") is False


def test_delete_credential_requires_a_reason():
    _add_system()
    client = _client()
    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})

    resp = client.delete("/api/credentials/ZZTEST", json={})
    assert resp.status_code == 400


def test_delete_credential_succeeds_and_is_audit_logged():
    _add_system()
    client = _client()
    client.post("/api/credentials/ZZTEST", json={"rfc_user": "SAL_RFC", "password": "hunter2"})

    resp = client.delete("/api/credentials/ZZTEST", json={"reason": "rotating password"})
    assert resp.status_code == 200

    get_resp = client.get("/api/credentials/ZZTEST")
    assert get_resp.status_code == 404

    from sal import audit
    total, entries = audit.list_entries(action="credential_remove", system_id="ZZTEST")
    assert total == 1
    assert entries[0]["source_system"] == "ZZTEST"


def test_delete_credential_404_when_nothing_stored():
    _add_system()
    client = _client()
    resp = client.delete("/api/credentials/ZZTEST", json={"reason": "cleanup"})
    assert resp.status_code == 404
