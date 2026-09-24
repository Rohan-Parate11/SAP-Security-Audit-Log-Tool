"""Regression tests for the catalogue-seeding performance fix.

sal/web/api.py's dashboard(), findings_list(), get_critical_transactions(),
and get_sensitive_tables() used to call seed_default_critical_transactions()/
seed_default_sensitive_tables() on every single request - both idempotent
(INSERT OR IGNORE against a hardcoded dict), but each was a measurable,
compounding cost on every page view. Seeding now happens once, at process
startup, in sal/web/__init__.py's create_app(). These tests pin the
resulting behavior: if an analyst deliberately removes a default catalogue
entry, hitting these endpoints must not silently resurrect it.

Uses Flask's test client against create_app(); WERKZEUG_RUN_MAIN is unset in
the test process (see tests/test_api.py's docstring), so create_app()'s
startup seeding - like its worker/scheduler startup - correctly does not run
here. That's fine for these tests: they seed explicitly via
sal.catalogues.seed_default_*() themselves, the same way a real process
would have already done once at boot before serving any request.
"""
from sal.catalogues import (
    remove_critical_transaction,
    remove_sensitive_table,
    seed_default_critical_transactions,
    seed_default_sensitive_tables,
)
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_dashboard_does_not_reseed_a_removed_critical_transaction():
    seed_default_critical_transactions()
    remove_critical_transaction("SU01")

    resp = _client().get("/api/dashboard?system_id=S23&client=100")

    assert resp.status_code == 200
    assert resp.get_json()["critical_transaction_count"] == 11  # 12 defaults minus SU01


def test_dashboard_does_not_reseed_a_removed_sensitive_table():
    seed_default_sensitive_tables()
    remove_sensitive_table("USR02")

    resp = _client().get("/api/dashboard?system_id=S23&client=100")

    assert resp.status_code == 200
    assert resp.get_json()["sensitive_table_count"] == 8  # 9 defaults minus USR02


def test_findings_list_does_not_reseed_a_removed_critical_transaction():
    seed_default_critical_transactions()
    remove_critical_transaction("PFCG")

    resp = _client().get("/api/findings?system_id=S23&client=100")

    assert resp.status_code == 200
    from sal.catalogues import list_critical_transactions
    assert "PFCG" not in list_critical_transactions()


def test_catalogues_endpoint_does_not_reseed_a_removed_critical_transaction():
    seed_default_critical_transactions()
    remove_critical_transaction("SM19")

    resp = _client().get("/api/catalogues/critical-transactions")

    assert resp.status_code == 200
    codes = {item["transaction_code"] for item in resp.get_json()["items"]}
    assert "SM19" not in codes


def test_catalogues_endpoint_does_not_reseed_a_removed_sensitive_table():
    seed_default_sensitive_tables()
    remove_sensitive_table("BSEG")

    resp = _client().get("/api/catalogues/sensitive-tables")

    assert resp.status_code == 200
    names = {item["table_name"] for item in resp.get_json()["items"]}
    assert "BSEG" not in names
