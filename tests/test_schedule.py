"""Regression tests for Slice B: per-system schedule-frequency configuration.

Covers sal/schedule.py's get_schedule()/set_schedule()/remove_schedule() and
the new GET/PUT /api/systems/<id>/schedule endpoints in sal/web/api.py.
Cron-vs-interval trigger selection in sal/jobs.py's register_daily_job() is
covered in tests/test_jobs.py instead, alongside its existing scheduler tests.
"""
import pytest

import sal.schedule as schedule_svc
import sal.systems as systems_svc
from sal import audit
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_get_schedule_falls_back_to_default_when_no_row():
    cfg = schedule_svc.get_schedule("S23")

    assert cfg["interval_type"] == "daily"
    assert cfg["anchor_hour"] == 2
    assert cfg["anchor_minute"] == 0
    assert cfg["interval_hours"] is None


def test_set_schedule_daily_validates_and_upserts():
    schedule_svc.set_schedule("S23", "daily", "tester", anchor_hour=6, anchor_minute=30)
    cfg = schedule_svc.get_schedule("S23")
    assert cfg["anchor_hour"] == 6 and cfg["anchor_minute"] == 30
    assert cfg["interval_hours"] is None
    assert cfg["updated_by"] == "tester"

    schedule_svc.set_schedule("S23", "daily", "tester2", anchor_hour=9, anchor_minute=0)
    cfg = schedule_svc.get_schedule("S23")
    assert cfg["anchor_hour"] == 9
    assert cfg["updated_by"] == "tester2"


def test_set_schedule_interval_validates_and_stores():
    cfg = schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)

    assert cfg["interval_type"] == "interval"
    assert cfg["interval_hours"] == 6
    assert cfg["anchor_hour"] is None and cfg["anchor_minute"] is None


def test_set_schedule_coerces_string_numeric_fields():
    cfg = schedule_svc.set_schedule("S23", "daily", "tester", anchor_hour="6", anchor_minute="30")
    assert cfg["anchor_hour"] == 6 and cfg["anchor_minute"] == 30


def test_set_schedule_rejects_unknown_interval_type():
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "weekly", "tester", anchor_hour=1, anchor_minute=0)


def test_set_schedule_daily_requires_hour_and_minute():
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "daily", "tester")


def test_set_schedule_rejects_out_of_range_hour():
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "daily", "tester", anchor_hour=24, anchor_minute=0)


def test_set_schedule_interval_requires_interval_hours():
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "interval", "tester")


@pytest.mark.parametrize("bad_hours", [0, 200])
def test_set_schedule_rejects_interval_hours_out_of_bounds(bad_hours):
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=bad_hours)


@pytest.mark.parametrize("bad_value", [True, 6.9, float("inf"), float("-inf"), float("nan")])
def test_set_schedule_rejects_malformed_numeric_values(bad_value):
    """A bool, a non-whole float, or an infinite/NaN float must all become a
    clean ValueError (-> 400 at the API layer) - not silently coerced (a
    bool truncating to 1/0, a float truncating to an int) and not an
    unhandled OverflowError (int(float('inf')) raises OverflowError, which
    used to escape _to_int()'s narrower except clause).
    """
    with pytest.raises(ValueError):
        schedule_svc.set_schedule("S23", "daily", "tester", anchor_hour=bad_value, anchor_minute=0)


def test_schedule_settings_check_constraint_rejects_inconsistent_row():
    """DB-level insurance (found in review) alongside set_schedule()'s own
    validation - a 'daily' row with a NULL anchor_hour must never be
    writable at all, even by some future code path that bypasses
    set_schedule() entirely.
    """
    from sal.storage.db import get_connection

    conn = get_connection()
    try:
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            conn.execute(
                "INSERT INTO schedule_settings "
                "(system_id, interval_type, anchor_hour, anchor_minute, interval_hours, "
                " updated_by, updated_at) VALUES ('S23', 'daily', NULL, NULL, NULL, 'x', 'x')"
            )
    finally:
        conn.close()


def test_get_schedule_falls_back_when_existing_row_is_malformed():
    """Defense in depth: even if a malformed row somehow exists (bypassing
    both set_schedule()'s validation and the CHECK constraint, e.g. on a
    SQLite build/config where CHECK enforcement differs), get_schedule()
    must never hand a NULL anchor_hour/anchor_minute back to
    register_daily_job() - that reaches APScheduler's CronTrigger, which
    fires roughly once a second rather than erroring.
    """
    from sal.storage.db import get_connection

    conn = get_connection()
    try:
        conn.execute("PRAGMA ignore_check_constraints = 1")
        conn.execute(
            "INSERT INTO schedule_settings "
            "(system_id, interval_type, anchor_hour, anchor_minute, interval_hours, "
            " updated_by, updated_at) VALUES ('S23', 'daily', NULL, NULL, NULL, 'x', 'x')"
        )
        conn.commit()
    finally:
        conn.close()

    cfg = schedule_svc.get_schedule("S23")

    assert cfg["anchor_hour"] is not None
    assert cfg["anchor_minute"] is not None


def test_remove_schedule_deletes_row_and_reverts_to_default():
    schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)

    schedule_svc.remove_schedule("S23")

    cfg = schedule_svc.get_schedule("S23")
    assert cfg["interval_type"] == "daily"
    assert cfg["anchor_hour"] == 2


# ---- API endpoints ---------------------------------------------------------

def test_get_system_schedule_requires_known_system():
    resp = _client().get("/api/systems/BOGUS/schedule")
    assert resp.status_code == 404


def test_put_system_schedule_requires_known_system():
    resp = _client().put(
        "/api/systems/BOGUS/schedule",
        json={"interval_type": "daily", "anchor_hour": 2, "anchor_minute": 0},
    )
    assert resp.status_code == 404


def test_put_system_schedule_rejects_invalid_input():
    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")

    resp = _client().put("/api/systems/S23/schedule", json={"interval_type": "daily"})

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_put_system_schedule_updates_registers_live_and_audits(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    seen = {}
    monkeypatch.setattr(api_module.jobs, "register_daily_job",
                         lambda sid, client: seen.setdefault("registered", (sid, client)))

    resp = _client().put(
        "/api/systems/S23/schedule", json={"interval_type": "interval", "interval_hours": 4}
    )

    assert resp.status_code == 200
    item = resp.get_json()["item"]
    assert item["interval_type"] == "interval"
    assert item["interval_hours"] == 4
    assert seen["registered"] == ("S23", "100")

    total, entries = audit.list_entries(action="schedule_update")
    assert total == 1
    assert entries[0]["source_system"] == "S23"


def test_get_system_schedule_includes_next_scheduled_run(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    monkeypatch.setattr(api_module.jobs, "next_scheduled_run", lambda sid: "2026-09-14T02:00:00+00:00")

    resp = _client().get("/api/systems/S23/schedule")

    assert resp.status_code == 200
    assert resp.get_json()["item"]["next_scheduled_run"] == "2026-09-14T02:00:00+00:00"


def test_jobs_list_enriches_scheduled_job_with_current_daily_frequency():
    import sal.jobs as jobs_svc

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    schedule_svc.set_schedule("S23", "daily", "tester", anchor_hour=6, anchor_minute=15)
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="scheduled", triggered_by="daily_scheduler")

    item = _client().get("/api/jobs?system_id=S23&client=100").get_json()["items"][0]

    assert item["schedule_interval_type"] == "daily"
    assert item["schedule_anchor_hour"] == 6
    assert item["schedule_anchor_minute"] == 15
    assert item["schedule_interval_hours"] is None


def test_jobs_list_enriches_scheduled_job_with_current_interval_frequency():
    import sal.jobs as jobs_svc

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="scheduled", triggered_by="daily_scheduler")

    item = _client().get("/api/jobs?system_id=S23&client=100").get_json()["items"][0]

    assert item["schedule_interval_type"] == "interval"
    assert item["schedule_interval_hours"] == 6


def test_jobs_list_leaves_adhoc_job_frequency_fields_null():
    import sal.jobs as jobs_svc

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester")

    item = _client().get("/api/jobs?system_id=S23&client=100").get_json()["items"][0]

    assert item["schedule_interval_type"] is None
    assert item["schedule_interval_hours"] is None


def test_delete_system_removes_schedule_settings():
    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)

    _client().delete("/api/systems/S23")

    cfg = schedule_svc.get_schedule("S23")
    assert cfg["interval_type"] == "daily"  # reverted to default, not a leftover interval row
