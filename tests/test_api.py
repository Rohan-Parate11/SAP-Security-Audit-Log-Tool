"""Regression tests for sal/web/api.py's /collect endpoint (Phase B hardening).

Confirms an unconfigured system_id is rejected at submission time rather
than accepted into the job queue and only failing once the worker actually
tries to run it - found live during Phase B testing ("BOGUS" was queued
with no upfront check).

Uses Flask's test client against create_app(); WERKZEUG_RUN_MAIN is unset
in the test process, so create_app()'s worker/scheduler startup guard
correctly stays off - no background thread runs during these tests.
"""
import csv
import io

from openpyxl import load_workbook

import sal.findings as findings_svc
import sal.web.api as api_module
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_connection_test_reports_live_rfc_failure_distinctly_from_missing_credentials(monkeypatch):
    """Regression (caught in review): SapConnectionError subclasses
    RuntimeError, so the missing-credentials except RuntimeError clause
    must come AFTER except SapConnectionError, or a real, live RFC
    failure (credentials perfectly fine - bad host, timeout, etc.) gets
    mislabeled as "credentials not maintained"."""
    class _FailingConnection:
        def __enter__(self):
            raise api_module.SapConnectionError("Failed to connect to SAP system 'S23': timeout")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(api_module, "SapConnection", lambda system_id: _FailingConnection())

    resp = _client().post("/api/connection-test", json={"system_id": "S23"})
    data = resp.get_json()

    assert data["ok"] is False
    assert "credentials not maintained" not in data["error"].lower()
    assert "timeout" in data["error"]


def test_connection_test_reports_missing_credentials_cleanly():
    """Found in UAT (CONN-01): a system with no SAL_SAP_<ID>_* env vars set
    made connection_test() raise an uncaught RuntimeError (from
    config.sap_system_config(), before SapConnection.__enter__()'s own
    try/except - which only wraps the live RFC call - ever runs), surfacing
    as an unhandled 500 instead of a clean, actionable error. This test's
    system_id has no SAL_SAP_* env vars configured in the test environment
    either, by construction - real SAP credentials are never present here."""
    resp = _client().post("/api/connection-test", json={"system_id": "NOCREDS_TEST_SYS"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert "credentials not maintained" in data["error"].lower()
    assert ".env" in data["error"]


def test_delete_whitelist_requires_a_reason():
    client = _client()
    add_resp = client.post("/api/whitelist", json={
        "rule_key": "test_rule", "reason": "initial add", "expires_at": "2099-01-01T23:59:59+00:00",
    })
    entry_id = add_resp.get_json()["id"]

    no_reason = client.delete(f"/api/whitelist/{entry_id}", json={})
    assert no_reason.status_code == 400
    assert entry_id in [w["id"] for w in findings_svc.list_whitelist()]

    with_reason = client.delete(f"/api/whitelist/{entry_id}", json={"reason": "no longer needed"})
    assert with_reason.status_code == 200
    assert entry_id not in [w["id"] for w in findings_svc.list_whitelist()]

    from sal import audit
    total, entries = audit.list_entries(action="whitelist_remove")
    assert total == 1
    assert entries[0]["params_json"] and "no longer needed" in entries[0]["params_json"]


def test_audit_actions_route_reflects_distinct_recorded_actions():
    from sal import audit

    audit.record("tester", "collect")
    audit.record("tester", "job_delete")
    audit.record("tester", "collect")  # duplicate action - must not appear twice

    resp = _client().get("/api/audit/actions")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["actions"] == sorted(set(data["actions"]))  # sorted, no duplicates
    assert "collect" in data["actions"]
    assert "job_delete" in data["actions"]
    assert data["actions"].count("collect") == 1


def test_delete_job_requires_reason():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)

    resp = _client().delete(f"/api/jobs/{job_id}", json={})

    assert resp.status_code == 400


def test_delete_job_rejects_queued_job():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")

    resp = _client().delete(f"/api/jobs/{job_id}", json={"reason": "test"})

    assert resp.status_code == 409


def test_delete_job_rejects_running_job():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()  # advances status to "running"

    resp = _client().delete(f"/api/jobs/{job_id}", json={"reason": "test"})

    assert resp.status_code == 409


def test_delete_and_restore_job_round_trip_with_reason_and_audit():
    import sal.jobs as jobs_svc
    from sal import audit

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester",
                                  job_name="Test job")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)
    client = _client()

    delete_resp = client.delete(f"/api/jobs/{job_id}", json={"reason": "duplicate submission"})
    assert delete_resp.status_code == 200

    active = client.get("/api/jobs?system_id=S23&client=100").get_json()["items"]
    assert all(item["id"] != job_id for item in active)

    deleted = client.get("/api/jobs?system_id=S23&client=100&view=deleted").get_json()["items"]
    assert deleted[0]["id"] == job_id
    assert deleted[0]["delete_reason"] == "duplicate submission"

    no_reason = client.post(f"/api/jobs/{job_id}/restore", json={})
    assert no_reason.status_code == 400

    restore_resp = client.post(f"/api/jobs/{job_id}/restore", json={"reason": "needed after all"})
    assert restore_resp.status_code == 200

    active_again = client.get("/api/jobs?system_id=S23&client=100").get_json()["items"]
    assert any(item["id"] == job_id for item in active_again)

    total_delete, _ = audit.list_entries(action="job_delete")
    total_restore, _ = audit.list_entries(action="job_restore")
    assert total_delete == 1
    assert total_restore == 1


def test_delete_job_404_when_missing():
    resp = _client().delete("/api/jobs/999999", json={"reason": "x"})
    assert resp.status_code == 404


def test_delete_job_404_on_second_delete_of_same_job():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)
    client = _client()

    first = client.delete(f"/api/jobs/{job_id}", json={"reason": "duplicate submission"})
    assert first.status_code == 200

    second = client.delete(f"/api/jobs/{job_id}", json={"reason": "trying again"})
    assert second.status_code == 404


def test_list_jobs_route_accepts_repeated_query_param_for_multi_value_filter():
    import sal.jobs as jobs_svc

    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="A")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="B")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="C")

    resp = _client().get("/api/jobs?system_id=S23&client=100&job_class=A&job_class=C")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["total"] == 2
    assert {i["job_class"] for i in data["items"]} == {"A", "C"}


def test_restore_job_404_when_not_deleted():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)

    resp = _client().post(f"/api/jobs/{job_id}/restore", json={"reason": "x"})
    assert resp.status_code == 404


def test_list_jobs_route_filters_by_job_class():
    import sal.jobs as jobs_svc

    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="A")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="C")

    resp = _client().get("/api/jobs?system_id=S23&client=100&job_class=A")
    data = resp.get_json()

    assert data["total"] == 1
    assert data["items"][0]["job_class"] == "A"


def test_list_jobs_route_paginates():
    import sal.jobs as jobs_svc

    for i in range(5):
        jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                             mode="adhoc", triggered_by="tester", job_name=f"Job {i}")

    resp = _client().get("/api/jobs?system_id=S23&client=100&limit=2&offset=0")
    data = resp.get_json()

    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["job_name"] == "Job 4"


def test_list_jobs_rejects_date_to_that_matches_shape_but_not_a_real_date():
    """"2026-02-30" passes the YYYY-MM-DD shape regex but isn't a real
    calendar date - must 400, not silently drop the filter and return an
    unfiltered result set (found in review).
    """
    resp = _client().get("/api/jobs?system_id=S23&client=100&date_to=2026-02-30")

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_collect_rejects_unconfigured_system(monkeypatch):
    monkeypatch.setattr(api_module.systems_svc, "list_systems",
                         lambda: [{"system_id": "S23", "client": "100", "description": "S23"}])
    client = _client()

    resp = client.post("/api/collect", json={
        "system_id": "BOGUS", "client": "999",
        "dat_from": "20260101", "dat_to": "20260101",
    })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "BOGUS" in data["error"]


def test_collect_accepts_configured_system(monkeypatch):
    monkeypatch.setattr(api_module.systems_svc, "list_systems",
                         lambda: [{"system_id": "S23", "client": "100", "description": "S23"}])
    monkeypatch.setattr(api_module.jobs, "submit_job", lambda **kw: 42)
    client = _client()

    resp = client.post("/api/collect", json={
        "system_id": "S23", "client": "100",
        "dat_from": "20260101", "dat_to": "20260101",
    })

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert data["job_id"] == 42


def _seed_one_finding(monkeypatch):
    finding = {
        "rule_key": "new_source", "rule_label": "New Source IP", "severity": "High",
        "source_system": "S23", "client": "100", "user_id": "U1",
        "detected_at": "2026-09-01T00:00:00+00:00", "summary": "test finding",
        "evidence": {"ip": "10.0.0.1"},
    }
    monkeypatch.setattr(findings_svc, "run_all_rules", lambda **kw: [finding])
    findings_svc.sync_findings(system_id="S23", client="100")


def test_findings_route_filters_by_user_id_and_multi_value_severity(monkeypatch):
    _seed_one_finding(monkeypatch)
    client = _client()

    resp = client.get("/api/findings?system_id=S23&client=100&user_id=u1")
    data = resp.get_json()
    assert data["total"] == 1

    resp = client.get("/api/findings?system_id=S23&client=100&user_id=nobody")
    assert resp.get_json()["total"] == 0

    resp = client.get("/api/findings?system_id=S23&client=100&severity=High&severity=Low")
    assert resp.get_json()["total"] == 1


def test_findings_route_finding_key_lookup_ignores_current_system_selection(monkeypatch):
    """Regression: requested directly - the Activity page's finding_dispose
    entries only ever showed an opaque finding_key hash, with no way to see
    which finding that was. #/findings?finding_key=... now links straight
    to it, and this must work even if a DIFFERENT system is currently
    selected in the UI (system_id/client are still sent, as they are on
    every page load) - the key alone already fully identifies one finding."""
    _seed_one_finding(monkeypatch)
    client = _client()

    lookup = client.get("/api/findings?system_id=S23&client=100")
    key = lookup.get_json()["items"][0]["finding_key"]

    resp = client.get(f"/api/findings?system_id=OTHER&client=999&finding_key={key}")
    data = resp.get_json()
    assert data["total"] == 1
    assert data["items"][0]["finding_key"] == key

    resp = client.get("/api/findings?system_id=S23&client=100&finding_key=does-not-exist")
    assert resp.get_json()["total"] == 0


def test_findings_export_csv(monkeypatch):
    _seed_one_finding(monkeypatch)
    client = _client()

    resp = client.get("/api/findings/export?system_id=S23&client=100&format=csv")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "sal_findings.csv" in resp.headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert len(rows) == 1
    assert rows[0]["rule_key"] == "new_source"
    assert rows[0]["user_id"] == "U1"


def test_findings_export_xlsx(monkeypatch):
    _seed_one_finding(monkeypatch)
    client = _client()

    resp = client.get("/api/findings/export?system_id=S23&client=100&format=xlsx")

    assert resp.status_code == 200
    assert "sal_findings.xlsx" in resp.headers["Content-Disposition"]
    wb = load_workbook(io.BytesIO(resp.get_data()))
    ws = wb["Findings"]
    assert ws.cell(row=1, column=1).value == "finding_key"
    assert ws.max_row == 2


def test_delete_system_normalizes_casing_for_scheduler_unregister(monkeypatch):
    import sal.systems as systems_svc
    systems_svc.add_system("T09", "Development", "host", "00", "100", "tester")

    seen = {}
    monkeypatch.setattr(api_module.jobs, "unregister_daily_job", lambda sid: seen.setdefault("id", sid))
    client = _client()

    resp = client.delete("/api/systems/t09")  # lowercase, as a caller might send

    assert resp.status_code == 200
    assert seen["id"] == "T09"  # must be normalized, not the raw lowercase path segment
    assert systems_svc.get_system("T09") is None


def test_patch_system_audit_log_only_records_known_fields(monkeypatch):
    import sal.systems as systems_svc
    systems_svc.add_system("T10", "Development", "host", "00", "100", "tester")

    recorded = {}
    monkeypatch.setattr(api_module.audit, "record",
                         lambda *a, **kw: recorded.update(kw))
    client = _client()

    resp = client.patch("/api/systems/t10", json={
        "description": "updated", "unexpected_field": "should not be logged",
    })

    assert resp.status_code == 200
    assert "unexpected_field" not in recorded["params"]
    assert recorded["params"]["description"] == "updated"
    # Regression (UAT round 2): system_update's audit row omitted `client`,
    # so it never matched the Activity page's default scoped view (which
    # filters by system_id AND client together) even though it was recorded.
    assert recorded["client"] == "100"


def test_system_add_audit_entry_includes_client_for_activity_page_scoping(monkeypatch):
    """Same regression as system_update above, for system_add."""
    recorded = {}
    monkeypatch.setattr(api_module.audit, "record", lambda *a, **kw: recorded.update(kw))
    client = _client()

    resp = client.post("/api/systems", json={
        "system_id": "T11", "environment": "Development",
        "ashost": "host", "sysnr": "00", "client": "100",
    })

    assert resp.status_code == 201
    assert recorded["client"] == "100"


def test_schedule_update_audit_entry_includes_client_for_activity_page_scoping(monkeypatch):
    """Same regression as system_update above, for schedule_update."""
    import sal.systems as systems_svc
    systems_svc.add_system("T12", "Development", "host", "00", "100", "tester")

    recorded = {}
    monkeypatch.setattr(api_module.audit, "record", lambda *a, **kw: recorded.update(kw))
    monkeypatch.setattr(api_module.jobs, "register_daily_job", lambda *a, **kw: None)
    client = _client()

    resp = client.put("/api/systems/T12/schedule", json={
        "interval_type": "interval", "interval_hours": 6,
    })

    assert resp.status_code == 200
    assert recorded["client"] == "100"


def test_role_context_refresh_audit_entry_includes_client_for_activity_page_scoping(monkeypatch):
    """Same regression as system_update above, for role_context_refresh -
    client comes from sync_role_context()'s own result dict (it resolves
    the system's client internally), not from the request's query args."""
    import sal.systems as systems_svc
    systems_svc.add_system("T13", "Development", "host", "00", "100", "tester")

    monkeypatch.setattr(
        api_module.role_context, "sync_role_context",
        lambda system_id, actor=None: {
            "status": "success", "system_id": system_id, "client": "100",
            "run_at": "2026-01-01T00:00:00+00:00",
            "user_role_rows": 0, "role_tcode_rows": 0, "error": None,
        },
    )
    recorded = {}
    monkeypatch.setattr(api_module.audit, "record", lambda *a, **kw: recorded.update(kw))
    client = _client()

    resp = client.post("/api/role-context/refresh?system_id=T13")

    assert resp.status_code == 200
    assert recorded["client"] == "100"


def test_connection_test_audit_entry_includes_client_for_activity_page_scoping(monkeypatch):
    """Regression (UAT round 2, JOB-08): connection_test()'s audit.record()
    omitted `client` entirely, so a real connection-test attempt never
    matched the Activity page's default scoped view (GET /api/audit
    filters by system_id AND client together) - the row was being written,
    it just silently never appeared in the view an analyst actually looks
    at."""
    import sal.systems as systems_svc
    systems_svc.add_system("T14", "Development", "host", "00", "100", "tester")

    class _OkConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ping(self):
            return None

        def call(self, name, **kwargs):
            return {"RFCSI_EXPORT": {
                "RFCSYSID": "T14", "RFCSAPRL": "757", "RFCHOST": "host",
                "RFCDBHOST": "dbhost", "RFCOPSYS": "Linux",
            }}

    monkeypatch.setattr(api_module, "SapConnection", lambda system_id: _OkConnection())
    client = _client()

    resp = client.post("/api/connection-test", json={"system_id": "T14"})
    assert resp.get_json()["ok"] is True

    from sal import audit
    total, entries = audit.list_entries(action="connection_test", system_id="T14", client="100")
    assert total == 1
    assert entries[0]["client"] == "100"


def test_whitelist_add_and_remove_audit_entries_are_scoped_for_activity_page():
    """Regression (UAT round 2, FIND-10): whitelist_add/whitelist_remove's
    audit.record() calls omitted system_id/client entirely, so neither
    action ever matched the Activity page's default scoped view - flagged
    directly as a real concern since whitelist removal is a critical,
    auditor-facing action that must be traceable to who did it."""
    client = _client()

    add_resp = client.post("/api/whitelist", json={
        "rule_key": "test_rule_scoped", "reason": "scoped add",
        "expires_at": "2099-01-01T23:59:59+00:00",
        "system_id": "T15", "client": "200",
    })
    entry_id = add_resp.get_json()["id"]

    del_resp = client.delete(f"/api/whitelist/{entry_id}", json={"reason": "scoped remove"})
    assert del_resp.status_code == 200

    from sal import audit
    add_total, _ = audit.list_entries(action="whitelist_add", system_id="T15", client="200")
    assert add_total == 1
    remove_total, remove_entries = audit.list_entries(action="whitelist_remove", system_id="T15", client="200")
    assert remove_total == 1
    assert remove_entries[0]["source_system"] == "T15"
    assert remove_entries[0]["client"] == "200"


def test_catalogue_add_audit_entry_is_visible_when_a_system_is_selected():
    """Regression: unlike whitelist_add/remove above (genuinely tied to one
    system+client), catalogue_add/catalogue_remove - adding a critical
    transaction or sensitive table - are global actions, so audit.record()
    correctly leaves system_id/client unset for them. But the Activity
    page always scopes its query to whatever system happens to be selected
    in the nav bar, and list_entries() used to filter strictly on
    `source_system = ?`, so a global entry could never match any scoped
    view - it looked like the change was never captured at all, even
    though it genuinely was recorded. list_entries() must also admit
    NULL-system/client entries once a scope is applied."""
    client = _client()

    resp = client.post("/api/catalogues/critical-transactions", json={
        "transaction_code": "ZTEST", "description": "test entry",
    })
    assert resp.status_code == 200

    from sal import audit
    total, entries = audit.list_entries(action="catalogue_add", system_id="S23", client="100")
    assert total == 1
    assert entries[0]["source_system"] is None
    assert entries[0]["params_json"] and "critical-transactions" in entries[0]["params_json"]


def test_finding_dispose_audit_entry_is_scoped_for_activity_page(monkeypatch):
    """Regression: a python-reviewer pass on this round's other audit-scope
    fixes (JOB-08/FIND-10) caught that finding_dispose was the one
    significant auditor-facing action left unscoped - a true_positive/
    false_positive/whitelisted call never carried system_id/client, so it
    would never match the Activity page's default scoped view either,
    exactly like the gaps already fixed elsewhere in this same pass."""
    _seed_one_finding(monkeypatch)
    _total, items = findings_svc.list_findings(system_id="S23", client="100")
    finding_key = items[0]["finding_key"]
    client = _client()

    resp = client.post(f"/api/findings/{finding_key}/dispose",
                        json={"status": "true_positive"})
    assert resp.status_code == 200

    from sal import audit
    total, entries = audit.list_entries(action="finding_dispose", system_id="S23", client="100")
    assert total == 1
    assert entries[0]["source_system"] == "S23"
    assert entries[0]["client"] == "100"


def test_collection_runs_numbers_oldest_first_regardless_of_display_order():
    """The table itself is shown newest-first, but run_number should count
    up from this scope's oldest run (1) - a stable label that doesn't
    reshuffle as new runs are added, not just the row's on-screen position.
    """
    from sal.storage.db import get_connection

    conn = get_connection()
    try:
        for i, started_at in enumerate(["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00",
                                         "2026-01-03T00:00:00+00:00"]):
            conn.execute(
                "INSERT INTO collection_runs (run_id, source_system, client, dat_from, dat_to, "
                "started_at, status) VALUES (?, 'S23', '100', '20260101', '20260101', ?, 'success')",
                (f"run-{i}", started_at),
            )
        conn.commit()
    finally:
        conn.close()

    resp = _client().get("/api/collection-runs?system_id=S23&client=100")
    items = resp.get_json()["items"]

    assert [item["run_id"] for item in items] == ["run-2", "run-1", "run-0"]  # newest first
    assert [item["run_number"] for item in items] == [3, 2, 1]  # oldest run = #1


def test_collection_runs_includes_job_name_via_join():
    """collection_runs never knew which job spawned it until job_id was
    added - this pins the LEFT JOIN that lets 'Recent collection runs'
    show the job's name/description/mode, and that a run with no job_id
    (predating the column, or scripts/collect_sm20.py's CLI backfill path)
    still comes back with a null job_name rather than erroring or being
    silently dropped by the join.
    """
    from sal.storage.db import get_connection

    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO collection_jobs (system_id, client, mode, status, triggered_by, "
            "submitted_at, job_name, job_description) VALUES "
            "('S23', '100', 'adhoc', 'success', 'tester', '2026-01-01T00:00:00+00:00', "
            "'Weekly SU01 spot-check', 'Checking for anomalies')"
        )
        job_id = cur.lastrowid
        conn.execute(
            "INSERT INTO collection_runs (run_id, source_system, client, dat_from, dat_to, "
            "started_at, status, job_id) VALUES "
            "('run-with-job', 'S23', '100', '20260101', '20260101', "
            "'2026-01-01T01:00:00+00:00', 'success', ?)",
            (job_id,),
        )
        conn.execute(
            "INSERT INTO collection_runs (run_id, source_system, client, dat_from, dat_to, "
            "started_at, status) VALUES "
            "('run-no-job', 'S23', '100', '20260102', '20260102', "
            "'2026-01-02T01:00:00+00:00', 'success')"
        )
        conn.commit()
    finally:
        conn.close()

    resp = _client().get("/api/collection-runs?system_id=S23&client=100")
    items = {item["run_id"]: item for item in resp.get_json()["items"]}

    assert items["run-with-job"]["job_name"] == "Weekly SU01 spot-check"
    assert items["run-with-job"]["job_description"] == "Checking for anomalies"
    assert items["run-with-job"]["job_mode"] == "adhoc"
    assert items["run-no-job"]["job_name"] is None


def test_collection_runs_export_csv_empty_ok():
    client = _client()

    resp = client.get("/api/collection-runs/export?system_id=S23&client=100&format=csv")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert rows == []


def test_role_context_user_requires_system_id():
    resp = _client().get("/api/role-context/user?user_id=TRAIN_13_S23")

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_role_context_user_requires_user_id():
    resp = _client().get("/api/role-context/user?system_id=S23&client=100")

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_role_context_user_rejects_unconfigured_system(monkeypatch):
    monkeypatch.setattr(api_module.systems_svc, "list_systems",
                         lambda: [{"system_id": "S23", "client": "100", "description": "S23"}])

    resp = _client().get("/api/role-context/user?system_id=BOGUS&client=999&user_id=U1")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "BOGUS" in data["error"]


def test_role_context_user_returns_combined_summary(monkeypatch):
    monkeypatch.setattr(api_module.systems_svc, "list_systems",
                         lambda: [{"system_id": "S23", "client": "100", "description": "S23"}])
    seen = {}

    def _fake_summary(system_id, client, user_id, **kw):
        seen["args"] = (system_id, client, user_id)
        return {
            "system_id": system_id, "client": client, "user_id": user_id, "as_of": "20260913",
            "has_role_data": False, "roles": [], "tcodes_via_roles": [],
            "profiles": ["SAP_ALL"], "profiles_error": None,
        }

    monkeypatch.setattr(api_module.role_context, "user_access_summary", _fake_summary)

    resp = _client().get("/api/role-context/user?system_id=S23&client=100&user_id=TRAIN_13_S23")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profiles"] == ["SAP_ALL"]
    assert data["has_role_data"] is False
    assert seen["args"] == ("S23", "100", "TRAIN_13_S23")
