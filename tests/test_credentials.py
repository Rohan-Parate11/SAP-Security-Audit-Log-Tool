"""Regression tests for sal/credentials.py - the central, encrypted
credential store (requested directly, 2026-09-16, answering the HOME-02
open question). Also covers its integration points: sal.config.
sap_system_config() (checks here first, falls back to .env) and
sal.systems.has_credentials() (checks both sources).

Uses "ZZTEST" as the system_id throughout, deliberately NOT "S23" (this
project's own real, live system) - python-dotenv's load_dotenv() (called
once at sal.config import time) leaves the real .env's SAL_SAP_S23_*
values sitting in the actual process environment for the whole pytest
run, not just isolated per test the way tests/conftest.py's isolated_db
fixture isolates the sqlite file. A test asserting "S23 has no configured
credentials" would collide with that real, live configuration - caught by
running this file before trusting it.
"""
import pytest
from cryptography.fernet import Fernet

import sal.config as config
import sal.credentials as credentials
import sal.systems as systems_svc


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("SAL_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_set_and_get_credential_round_trips():
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")
    result = credentials.get_credential("ZZTEST")
    assert result["rfc_user"] == "SAL_RFC"
    assert result["password"] == "hunter2"
    assert result["updated_by"] == "tester"


def test_get_credential_returns_none_when_nothing_stored():
    assert credentials.get_credential("ZZTEST") is None


def test_has_stored_credential():
    assert credentials.has_stored_credential("ZZTEST") is False
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")
    assert credentials.has_stored_credential("ZZTEST") is True


def test_set_credential_upserts_not_duplicates():
    credentials.set_credential("ZZTEST", "SAL_RFC", "first", actor="a")
    credentials.set_credential("ZZTEST", "SAL_RFC", "second", actor="b")
    result = credentials.get_credential("ZZTEST")
    assert result["password"] == "second"
    assert result["updated_by"] == "b"


def test_remove_credential():
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")
    assert credentials.remove_credential("ZZTEST") is True
    assert credentials.get_credential("ZZTEST") is None
    assert credentials.remove_credential("ZZTEST") is False  # already gone


def test_set_credential_requires_encryption_key(monkeypatch):
    monkeypatch.delenv("SAL_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(credentials.CredentialStoreNotConfigured):
        credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")


def test_set_credential_rejects_missing_user_or_password():
    with pytest.raises(ValueError):
        credentials.set_credential("ZZTEST", "", "hunter2", actor="tester")
    with pytest.raises(ValueError):
        credentials.set_credential("ZZTEST", "SAL_RFC", "", actor="tester")


def test_credential_source_reports_central_env_or_missing(monkeypatch):
    monkeypatch.delenv("SAL_SAP_ZZTEST_PASSWD", raising=False)
    assert credentials.credential_source("ZZTEST") == "missing"
    monkeypatch.setenv("SAL_SAP_ZZTEST_PASSWD", "envpass")
    assert credentials.credential_source("ZZTEST") == "env"
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")
    assert credentials.credential_source("ZZTEST") == "central"  # central wins once set


def test_resolve_stored_config_none_without_a_systems_registry_row():
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")
    assert credentials.resolve_stored_config("ZZTEST") is None


def test_resolve_stored_config_merges_registry_metadata_with_stored_credential():
    systems_svc.add_system("ZZTEST", "Development", "sapdev.example.com", "00", "100", "tester")
    credentials.set_credential("ZZTEST", "SAL_RFC", "hunter2", actor="tester")

    resolved = credentials.resolve_stored_config("ZZTEST")
    assert resolved == {
        "ashost": "sapdev.example.com", "sysnr": "00", "client": "100",
        "user": "SAL_RFC", "passwd": "hunter2",
    }


def test_resolve_stored_config_none_when_nothing_stored():
    systems_svc.add_system("ZZTEST", "Development", "sapdev.example.com", "00", "100", "tester")
    assert credentials.resolve_stored_config("ZZTEST") is None


# ---- sal.config.sap_system_config() integration ----------------------------

def test_sap_system_config_prefers_central_store_over_env(monkeypatch):
    monkeypatch.setenv("SAL_SAP_ZZTEST_ASHOST", "env-host")
    monkeypatch.setenv("SAL_SAP_ZZTEST_SYSNR", "01")
    monkeypatch.setenv("SAL_SAP_ZZTEST_CLIENT", "200")
    monkeypatch.setenv("SAL_SAP_ZZTEST_USER", "ENV_USER")
    monkeypatch.setenv("SAL_SAP_ZZTEST_PASSWD", "envpass")

    systems_svc.add_system("ZZTEST", "Development", "central-host", "00", "100", "tester")
    credentials.set_credential("ZZTEST", "SAL_RFC", "centralpass", actor="tester")

    cfg = config.sap_system_config("ZZTEST")
    assert cfg == {
        "ashost": "central-host", "sysnr": "00", "client": "100",
        "user": "SAL_RFC", "passwd": "centralpass",
    }


def test_sap_system_config_falls_back_to_env_when_nothing_stored(monkeypatch):
    monkeypatch.setenv("SAL_SAP_ZZTEST_ASHOST", "env-host")
    monkeypatch.setenv("SAL_SAP_ZZTEST_SYSNR", "01")
    monkeypatch.setenv("SAL_SAP_ZZTEST_CLIENT", "200")
    monkeypatch.setenv("SAL_SAP_ZZTEST_USER", "ENV_USER")
    monkeypatch.setenv("SAL_SAP_ZZTEST_PASSWD", "envpass")

    cfg = config.sap_system_config("ZZTEST")
    assert cfg["ashost"] == "env-host"
    assert cfg["passwd"] == "envpass"


def test_sap_system_config_still_raises_when_neither_source_has_it(monkeypatch):
    monkeypatch.delenv("SAL_SAP_ZZTEST_PASSWD", raising=False)
    with pytest.raises(RuntimeError):
        config.sap_system_config("ZZTEST")


# ---- sal.systems.has_credentials() integration -----------------------------

def test_has_credentials_checks_both_sources(monkeypatch):
    monkeypatch.delenv("SAL_SAP_ZZTEST_PASSWD", raising=False)
    assert systems_svc.has_credentials("ZZTEST") is False
    monkeypatch.setenv("SAL_SAP_ZZTEST_PASSWD", "envpass")
    assert systems_svc.has_credentials("ZZTEST") is True
    monkeypatch.delenv("SAL_SAP_ZZTEST_PASSWD", raising=False)
    assert systems_svc.has_credentials("ZZTEST") is False
    credentials.set_credential("ZZTEST", "SAL_RFC", "centralpass", actor="tester")
    assert systems_svc.has_credentials("ZZTEST") is True
