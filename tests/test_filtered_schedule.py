"""Regression tests for recurring filtered collection schedules.

Requested directly (2026-09-16): "if I want to schedule an ad hoc job to
run on daily or whatever basis, I should be able to do that as well."
Covers sal/filtered_schedule.py's CRUD/validation, the window-computation
logic, sal/jobs.py's registration/run functions, and the
GET/POST/PATCH/DELETE /api/filtered-schedules endpoints. Mirrors
tests/test_schedule.py's conventions throughout - same validation rules,
same API shapes - since filtered_schedule.py's cadence fields are
deliberately identical to schedule.py's.
"""
import pytest

import sal.filtered_schedule as filtered_schedule_svc
import sal.jobs as jobs_svc
import sal.systems as systems_svc
from sal import audit
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


# ---- sal/filtered_schedule.py -----------------------------------------

def test_add_schedule_daily_validates_and_stores():
    cfg = filtered_schedule_svc.add_schedule(
        "S23", "100", "Daily SU01 check", "tester", interval_type="daily",
        anchor_hour=6, anchor_minute=30, user="U1,U2", transaction_code="SU01",
    )
    assert cfg["name"] == "Daily SU01 check"
    assert cfg["interval_type"] == "daily"
    assert cfg["anchor_hour"] == 6 and cfg["anchor_minute"] == 30
    assert cfg["interval_hours"] is None
    assert cfg["user_filter"] == "U1,U2"
    assert cfg["transaction_code"] == "SU01"
    assert cfg["enabled"] == 1
    assert cfg["created_by"] == "tester"


def test_add_schedule_interval_validates_and_stores():
    cfg = filtered_schedule_svc.add_schedule(
        "S23", "100", "Hourly FB01N check", "tester",
        interval_type="interval", interval_hours=4,
    )
    assert cfg["interval_type"] == "interval"
    assert cfg["interval_hours"] == 4
    assert cfg["anchor_hour"] is None and cfg["anchor_minute"] is None


def test_add_schedule_requires_name():
    with pytest.raises(ValueError):
        filtered_schedule_svc.add_schedule(
            "S23", "100", "  ", "tester", interval_type="daily", anchor_hour=2, anchor_minute=0,
        )


def test_add_schedule_rejects_out_of_range_hour():
    with pytest.raises(ValueError):
        filtered_schedule_svc.add_schedule(
            "S23", "100", "Bad", "tester", interval_type="daily", anchor_hour=24, anchor_minute=0,
        )


@pytest.mark.parametrize("bad_hours", [0, 200])
def test_add_schedule_rejects_interval_hours_out_of_bounds(bad_hours):
    with pytest.raises(ValueError):
        filtered_schedule_svc.add_schedule(
            "S23", "100", "Bad", "tester", interval_type="interval", interval_hours=bad_hours,
        )


def test_a_system_can_have_multiple_schedules_at_once():
    filtered_schedule_svc.add_schedule("S23", "100", "First", "tester", interval_type="daily",
                                        anchor_hour=2, anchor_minute=0)
    filtered_schedule_svc.add_schedule("S23", "100", "Second", "tester", interval_type="interval",
                                        interval_hours=6)

    items = filtered_schedule_svc.list_schedules("S23", "100")
    assert {i["name"] for i in items} == {"First", "Second"}


def test_update_schedule_replaces_filters_and_cadence():
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0,
                                              transaction_code="SU01")
    updated = filtered_schedule_svc.update_schedule(
        cfg["id"], "editor", name="Renamed", interval_type="interval", interval_hours=8,
        transaction_code="PFCG",
    )
    assert updated["name"] == "Renamed"
    assert updated["interval_type"] == "interval"
    assert updated["interval_hours"] == 8
    assert updated["anchor_hour"] is None
    assert updated["transaction_code"] == "PFCG"
    assert updated["updated_by"] == "editor"


def test_update_schedule_can_toggle_enabled_without_touching_other_fields():
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0,
                                              transaction_code="SU01")
    updated = filtered_schedule_svc.update_schedule(cfg["id"], "editor", enabled=False)
    assert updated["enabled"] == 0
    assert updated["name"] == "Original"
    assert updated["transaction_code"] == "SU01"


def test_update_schedule_returns_none_for_unknown_id():
    assert filtered_schedule_svc.update_schedule(999, "tester", enabled=False) is None


def test_remove_schedule_deletes_row_and_returns_it():
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "ToRemove", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    removed = filtered_schedule_svc.remove_schedule(cfg["id"])
    assert removed["name"] == "ToRemove"
    assert filtered_schedule_svc.get_schedule(cfg["id"]) is None


def test_remove_schedule_returns_none_for_unknown_id():
    assert filtered_schedule_svc.remove_schedule(999) is None


def test_window_for_run_is_a_two_day_rolling_window():
    from datetime import datetime, timedelta, timezone
    dat_from, dat_to = filtered_schedule_svc.window_for_run()
    today = datetime.now(timezone.utc).date()
    assert dat_to == today.strftime("%Y%m%d")
    assert dat_from == (today - timedelta(days=1)).strftime("%Y%m%d")


# ---- sal/jobs.py integration --------------------------------------------

def test_run_filtered_schedule_submits_a_job_with_saved_filters(monkeypatch):
    cfg = filtered_schedule_svc.add_schedule(
        "S23", "100", "Daily SU01 check", "tester", interval_type="daily",
        anchor_hour=6, anchor_minute=30, user="U1", transaction_code="SU01",
    )
    job_id = jobs_svc.run_filtered_schedule(cfg["id"])
    assert job_id is not None

    job = jobs_svc.get_job(job_id)
    assert job["mode"] == jobs_svc.FILTERED_SCHEDULED_MODE
    assert job["mode"] != "scheduled"  # must never be mistaken for baseline progress
    assert job["job_name"] == "Daily SU01 check"
    assert job["triggered_by"] == "filtered_scheduler"

    import json
    filters = json.loads(job["filters_json"])
    assert filters["user"] == "U1"
    assert filters["transaction_code"] == "SU01"


def test_run_filtered_schedule_does_not_move_the_baseline_checkpoint():
    """The exact correctness risk this mode value exists to avoid: a
    filtered-schedule job completing must never be mistaken by
    last_scheduled_checkpoint() (mode='scheduled' only) for baseline
    progress, or the real detection-feed collection would silently skip
    days it never actually pulled unfiltered."""
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Filtered", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    job_id = jobs_svc.run_filtered_schedule(cfg["id"])
    jobs_svc._finish_job(job_id, "success", "20260101", None)

    assert jobs_svc.last_scheduled_checkpoint("S23") is None


def test_run_filtered_schedule_returns_none_when_disabled():
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Paused", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    filtered_schedule_svc.update_schedule(cfg["id"], "tester", enabled=False)

    assert jobs_svc.run_filtered_schedule(cfg["id"]) is None


def test_run_filtered_schedule_returns_none_for_unknown_id():
    assert jobs_svc.run_filtered_schedule(999) is None


# ---- API endpoints -------------------------------------------------------

def test_get_filtered_schedules_requires_system_id():
    resp = _client().get("/api/filtered-schedules")
    assert resp.status_code == 400


def test_post_filtered_schedule_requires_known_system():
    resp = _client().post(
        "/api/filtered-schedules?system_id=BOGUS&client=100",
        json={"name": "X", "interval_type": "daily", "anchor_hour": 2, "anchor_minute": 0},
    )
    assert resp.status_code == 400


def test_post_filtered_schedule_creates_registers_and_audits(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    seen = {}
    monkeypatch.setattr(api_module.jobs, "register_filtered_schedule_job",
                         lambda sid: seen.setdefault("registered", sid))

    resp = _client().post(
        "/api/filtered-schedules?system_id=S23&client=100",
        json={"name": "Daily SU01 check", "interval_type": "daily",
              "anchor_hour": 2, "anchor_minute": 0, "transaction_code": "SU01"},
    )

    assert resp.status_code == 201
    item = resp.get_json()["item"]
    assert item["name"] == "Daily SU01 check"
    assert "registered" in seen

    total, entries = audit.list_entries(action="filtered_schedule_add", system_id="S23", client="100")
    assert total == 1


def test_post_filtered_schedule_rejects_invalid_input():
    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    resp = _client().post(
        "/api/filtered-schedules?system_id=S23&client=100",
        json={"name": "X", "interval_type": "daily"},
    )
    assert resp.status_code == 400


def test_patch_filtered_schedule_updates_and_audits(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    monkeypatch.setattr(api_module.jobs, "register_filtered_schedule_job", lambda sid: None)

    resp = _client().patch(f"/api/filtered-schedules/{cfg['id']}", json={"name": "Renamed"})

    assert resp.status_code == 200
    assert resp.get_json()["item"]["name"] == "Renamed"
    total, entries = audit.list_entries(action="filtered_schedule_update", system_id="S23", client="100")
    assert total == 1


def test_patch_filtered_schedule_disabling_unregisters(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    seen = {}
    monkeypatch.setattr(api_module.jobs, "unregister_filtered_schedule_job",
                         lambda sid: seen.setdefault("unregistered", sid))

    resp = _client().patch(f"/api/filtered-schedules/{cfg['id']}", json={"enabled": False})

    assert resp.status_code == 200
    assert seen["unregistered"] == cfg["id"]


def test_patch_filtered_schedule_unknown_id_404s():
    resp = _client().patch("/api/filtered-schedules/999", json={"name": "X"})
    assert resp.status_code == 404


def test_delete_filtered_schedule_requires_reason():
    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    resp = _client().delete(f"/api/filtered-schedules/{cfg['id']}", json={})
    assert resp.status_code == 400
    assert filtered_schedule_svc.get_schedule(cfg["id"]) is not None


def test_delete_filtered_schedule_removes_unregisters_and_audits(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    seen = {}
    monkeypatch.setattr(api_module.jobs, "unregister_filtered_schedule_job",
                         lambda sid: seen.setdefault("unregistered", sid))

    resp = _client().delete(f"/api/filtered-schedules/{cfg['id']}", json={"reason": "no longer needed"})

    assert resp.status_code == 200
    assert filtered_schedule_svc.get_schedule(cfg["id"]) is None
    assert seen["unregistered"] == cfg["id"]
    total, entries = audit.list_entries(action="filtered_schedule_remove", system_id="S23", client="100")
    assert total == 1


def test_delete_system_removes_its_filtered_schedules(monkeypatch):
    import sal.web.api as api_module

    systems_svc.add_system("S23", "Development", "host", "00", "100", "tester")
    cfg = filtered_schedule_svc.add_schedule("S23", "100", "Original", "tester",
                                              interval_type="daily", anchor_hour=2, anchor_minute=0)
    monkeypatch.setattr(api_module.jobs, "unregister_filtered_schedule_job", lambda sid: None)

    _client().delete("/api/systems/S23")

    assert filtered_schedule_svc.get_schedule(cfg["id"]) is None
