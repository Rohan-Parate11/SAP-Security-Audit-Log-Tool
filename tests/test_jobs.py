"""Regression tests for sal/jobs.py (Blueprint v2 Phase B).

Exercises chunking, retry-then-give-up, the daily checkpoint calculation,
and the one-job-at-a-time claim mechanism against a throwaway sqlite db
(see conftest.py). collect_and_store() and sync_findings() are monkeypatched
so no live SAP connection or rule computation is needed - these tests target
sal/jobs.py's own orchestration logic, not the collector or detection rules.
"""
import json
from datetime import datetime, timedelta, timezone

import sal.jobs as jobs_svc


def test_submit_job_defaults_job_class_to_medium():
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    assert jobs_svc.get_job(job_id)["job_class"] == "B"


def test_submit_job_rejects_invalid_job_class():
    import pytest
    with pytest.raises(ValueError):
        jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                             dat_to="20260101", mode="adhoc", triggered_by="tester", job_class="Z")


def test_run_daily_checkpoint_submits_high_priority():
    job_id = jobs_svc.run_daily_checkpoint("S23", "100")
    assert jobs_svc.get_job(job_id)["job_class"] == "A"


def test_claim_next_queued_job_respects_priority_over_submission_order():
    """A later-submitted High-priority job must be claimed before an
    earlier-submitted Medium/Low one - SM36/SM37 parity: the detection-feed
    baseline (job_class='A') must not get stuck behind a pile of ad-hoc
    requests already sitting in the queue.
    """
    low_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester", job_class="C")
    high_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                   dat_to="20260101", mode="scheduled", triggered_by="daily_scheduler",
                                   job_class="A")

    claimed = jobs_svc._claim_next_queued_job()

    assert claimed["id"] == high_id
    assert claimed["id"] != low_id


def test_submit_job_persists_job_name_and_description():
    job_id = jobs_svc.submit_job(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
        mode="adhoc", triggered_by="tester",
        job_name="Weekly SU01 spot-check", job_description="For the Q1 audit ask",
    )
    job = jobs_svc.get_job(job_id)
    assert job["job_name"] == "Weekly SU01 spot-check"
    assert job["job_description"] == "For the Q1 audit ask"


def test_submit_job_without_name_or_description_stores_none():
    job_id = jobs_svc.submit_job(
        system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
        mode="adhoc", triggered_by="tester",
    )
    job = jobs_svc.get_job(job_id)
    assert job["job_name"] is None
    assert job["job_description"] is None


def test_daterange_yields_one_entry_per_day_inclusive():
    days = list(jobs_svc._daterange("20260101", "20260104"))
    assert days == ["20260101", "20260102", "20260103", "20260104"]


def test_daterange_single_day():
    assert list(jobs_svc._daterange("20260101", "20260101")) == ["20260101"]


def test_run_job_scheduled_collects_each_day_and_syncs_once(monkeypatch):
    """Scheduled jobs still chunk by day (an unattended catch-up gap
    benefits from resuming a partial failure) - ad-hoc jobs no longer do,
    see the mode="adhoc" tests below."""
    calls = []

    def fake_collect_and_store(**kwargs):
        calls.append(kwargs["dat_from"])
        return {"status": "success", "fetched": 1, "inserted": 1}

    sync_calls = []
    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings",
                         lambda **kw: sync_calls.append(kw) or {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260103", mode="scheduled", triggered_by="daily_scheduler")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    assert calls == ["20260101", "20260102", "20260103"]
    assert len(sync_calls) == 1

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "success"
    assert stored["last_completed_date"] == "20260103"
    assert stored["error_message"] is None


def test_run_job_scheduled_retries_a_failing_day_before_giving_up(monkeypatch):
    attempts = {"20260102": 0}

    def fake_collect_and_store(**kwargs):
        day = kwargs["dat_from"]
        if day == "20260101":
            return {"status": "success"}
        attempts[day] += 1
        return {"status": "error", "error": "RFC timeout"}

    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260103", mode="scheduled", triggered_by="daily_scheduler")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    assert attempts["20260102"] == jobs_svc._MAX_RETRIES

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "partial"
    assert stored["last_completed_date"] == "20260101"
    assert stored["error_message"] == "RFC timeout"


def test_run_job_adhoc_collects_whole_range_in_a_single_call(monkeypatch):
    """The behavior change this pins: an ad-hoc job spanning multiple days
    must NOT show up as N separate collection_runs entries for one query -
    exactly one collect_and_store() call spanning the whole range, not
    one per day."""
    calls = []

    def fake_collect_and_store(**kwargs):
        calls.append((kwargs["dat_from"], kwargs["dat_to"]))
        return {"status": "success", "fetched": 1, "inserted": 1}

    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260905",
                                  dat_to="20260912", mode="adhoc", triggered_by="tester")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    assert calls == [("20260905", "20260912")]

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "success"
    assert stored["last_completed_date"] == "20260912"
    assert stored["days_total"] == 1
    assert stored["days_completed"] == 1


def test_run_job_adhoc_retries_the_whole_range_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def fake_collect_and_store(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 2:
            return {"status": "error", "error": "transient"}
        return {"status": "success"}

    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260905",
                                  dat_to="20260912", mode="adhoc", triggered_by="tester")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    assert attempts["n"] == 2

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "success"
    assert stored["last_completed_date"] == "20260912"


def test_run_job_adhoc_gives_up_after_max_retries_marks_error_not_partial(monkeypatch):
    """A failed ad-hoc range has no partial credit to fall back to -
    unlike the day-chunked scheduled path, there's no "day 1 already
    succeeded" possible when the whole range is one call."""
    attempts = {"n": 0}

    def fake_collect_and_store(**kwargs):
        attempts["n"] += 1
        return {"status": "error", "error": "RFC timeout"}

    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260905",
                                  dat_to="20260912", mode="adhoc", triggered_by="tester")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    assert attempts["n"] == jobs_svc._MAX_RETRIES

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "error"
    assert stored["last_completed_date"] is None
    assert stored["error_message"] == "RFC timeout"


def test_run_job_first_day_fails_marks_error_not_partial(monkeypatch):
    monkeypatch.setattr(jobs_svc, "collect_and_store",
                         lambda **kw: {"status": "error", "error": "no connection"})
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "error"
    assert stored["last_completed_date"] is None


def test_run_job_day_that_fails_then_succeeds_on_retry_does_not_truncate_run(monkeypatch):
    seen = {"20260102": 0}

    def fake_collect_and_store(**kwargs):
        day = kwargs["dat_from"]
        if day == "20260102":
            seen[day] += 1
            if seen[day] == 1:
                return {"status": "error", "error": "transient"}
        return {"status": "success"}

    monkeypatch.setattr(jobs_svc, "collect_and_store", fake_collect_and_store)
    monkeypatch.setattr(jobs_svc.findings_svc, "sync_findings", lambda **kw: {"computed": 0, "new": 0})

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260103", mode="scheduled", triggered_by="daily_scheduler")
    job = jobs_svc._claim_next_queued_job()
    jobs_svc.run_job(job)

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "success"
    assert stored["last_completed_date"] == "20260103"
    assert stored["error_message"] is None


def test_claim_next_queued_job_picks_up_one_at_a_time():
    id1 = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                               dat_to="20260101", mode="adhoc", triggered_by="a")
    id2 = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260102",
                               dat_to="20260102", mode="adhoc", triggered_by="b")

    first = jobs_svc._claim_next_queued_job()
    assert first["id"] == id1
    assert first["status"] == "running"
    assert jobs_svc.get_job(id1)["status"] == "running"

    second = jobs_svc._claim_next_queued_job()
    assert second["id"] == id2

    assert jobs_svc._claim_next_queued_job() is None


def test_run_daily_checkpoint_uses_default_lookback_when_no_prior_scheduled_job():
    job_id = jobs_svc.run_daily_checkpoint("S23", client="100", default_lookback_days=3)
    job = jobs_svc.get_job(job_id)
    filters = json.loads(job["filters_json"])
    expected_from = (datetime.now(timezone.utc).date() - timedelta(days=3)).strftime("%Y%m%d")
    assert filters["dat_from"] == expected_from
    assert job["mode"] == "scheduled"


def test_run_daily_checkpoint_resumes_from_last_completed_date():
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260105", mode="scheduled", triggered_by="daily_scheduler")
    jobs_svc._finish_job(job_id, "success", "20260105", None)

    next_id = jobs_svc.run_daily_checkpoint("S23", client="100")
    filters = json.loads(jobs_svc.get_job(next_id)["filters_json"])
    assert filters["dat_from"] == "20260106"


def test_reconcile_stale_state_marks_orphaned_running_job_as_error():
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()  # simulates a job left "running" when the process died

    jobs_svc.reconcile_stale_state()

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "error"
    assert "re-run" in stored["error_message"].lower()
    assert stored["finished_at"] is not None


def test_reconcile_stale_state_marks_orphaned_running_collection_run_as_error():
    from sal.storage.db import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO collection_runs "
            "(run_id, source_system, client, dat_from, dat_to, started_at, status) "
            "VALUES ('orphan-run', 'S23', '100', '20260101', '20260101', "
            "'2026-01-01T00:00:00+00:00', 'running')"
        )
        conn.commit()
    finally:
        conn.close()

    jobs_svc.reconcile_stale_state()

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, finished_at, error_message FROM collection_runs WHERE run_id = 'orphan-run'"
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "error"
    assert row["finished_at"] is not None
    assert "re-run" in row["error_message"].lower()


def test_list_jobs_paginates_and_reports_total():
    for i in range(25):
        jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                             mode="adhoc", triggered_by="tester", job_name=f"Job {i}")

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", limit=10, offset=0)

    assert total == 25
    assert len(items) == 10
    assert items[0]["job_name"] == "Job 24"  # newest first


def test_list_jobs_filters_by_name_mode_and_status():
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_name="Weekly SU01 spot-check")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="scheduled", triggered_by="daily_scheduler")

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", job_name="SU01")
    assert total == 1 and items[0]["mode"] == "adhoc"

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", mode="scheduled")
    assert total == 1 and items[0]["triggered_by"] == "daily_scheduler"

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", status="queued")
    assert total == 2  # both jobs start out queued


def test_list_jobs_accepts_multiple_values_per_filter():
    """Excel-style column-header filters check multiple boxes at once -
    mode/status/job_class must each accept a list meaning "any of these",
    not just a single value."""
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="A")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="scheduled", triggered_by="daily_scheduler", job_class="B")
    jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101", dat_to="20260101",
                         mode="adhoc", triggered_by="tester", job_class="C")

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", job_class=["A", "C"])
    assert total == 2
    assert {i["job_class"] for i in items} == {"A", "C"}

    total, items = jobs_svc.list_jobs(system_id="S23", client="100", mode=["scheduled"])
    assert total == 1

    # A single string (not a list) must still work exactly as before.
    total, _items = jobs_svc.list_jobs(system_id="S23", client="100", mode="adhoc")
    assert total == 2

    # An empty list is "no filter", same as None.
    total, _items = jobs_svc.list_jobs(system_id="S23", client="100", job_class=[])
    assert total == 3


def test_list_jobs_view_deleted_excludes_and_then_includes_soft_deleted_job():
    from sal.storage.db import get_connection

    kept_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                   dat_to="20260101", mode="adhoc", triggered_by="tester",
                                   job_name="Kept job")
    deleted_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                      dat_to="20260101", mode="adhoc", triggered_by="tester",
                                      job_name="Deleted job")

    conn = get_connection()
    conn.execute(
        "UPDATE collection_jobs SET deleted_at = ?, deleted_by = ?, delete_reason = ? WHERE id = ?",
        ("2026-09-14T00:00:00+00:00", "tester", "no longer needed", deleted_id),
    )
    conn.commit()
    conn.close()

    total_active, active_items = jobs_svc.list_jobs(system_id="S23", client="100")
    assert total_active == 1
    assert active_items[0]["id"] == kept_id

    total_deleted, deleted_items = jobs_svc.list_jobs(system_id="S23", client="100", view="deleted")
    assert total_deleted == 1
    assert deleted_items[0]["id"] == deleted_id
    assert deleted_items[0]["delete_reason"] == "no longer needed"


def test_reconcile_stale_state_does_not_touch_completed_jobs():
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)

    jobs_svc.reconcile_stale_state()

    stored = jobs_svc.get_job(job_id)
    assert stored["status"] == "success"


class _FakeScheduler:
    def __init__(self):
        self.added = []
        self.removed = []
        self.calls = []  # full kwargs of every add_job() call, for Slice B's cron-vs-interval tests

    def add_job(self, func, trigger, **kwargs):
        self.added.append(kwargs.get("id"))
        self.calls.append({"trigger": trigger, **kwargs})

    def remove_job(self, job_id):
        if job_id not in self.added:
            from apscheduler.jobstores.base import JobLookupError
            raise JobLookupError(job_id)
        self.added.remove(job_id)
        self.removed.append(job_id)

    def get_job(self, job_id):
        return None


def test_register_and_unregister_daily_job_normalize_casing(monkeypatch):
    fake = _FakeScheduler()
    monkeypatch.setattr(jobs_svc, "_scheduler", fake)

    jobs_svc.register_daily_job("s23", "100")
    assert fake.added == ["daily-S23"]

    jobs_svc.unregister_daily_job("s23")  # lowercase, like a raw URL segment
    assert fake.removed == ["daily-S23"]


def test_unregister_daily_job_missing_job_does_not_raise(monkeypatch):
    monkeypatch.setattr(jobs_svc, "_scheduler", _FakeScheduler())
    jobs_svc.unregister_daily_job("NEVER_REGISTERED")  # must not raise


def test_run_daily_checkpoint_never_submits_any_filters():
    """Guardrail (added per dev-team QA verdict, 2026-09-14): the baseline
    scheduled job feeds every downstream detection rule and must always be
    a comprehensive, unfiltered pull - never scoped to a user/tcode/report/
    instance/msg_code. This must stay true even after future UI changes
    physically relocate the Schedule controls next to Collect's filtered
    ad-hoc form, so the two can never be silently conflated.
    """
    job_id = jobs_svc.run_daily_checkpoint("S23", "100")
    job = jobs_svc.get_job(job_id)
    filters = json.loads(job["filters_json"])

    assert filters["user"] is None
    assert filters["transaction_code"] is None
    assert filters["report"] is None
    assert filters["instance"] is None
    assert filters["msg_code"] is None
    assert filters["dat_from"] and filters["dat_to"]  # still a real date range, just unfiltered


def test_register_daily_job_defaults_to_cron_with_no_schedule_settings_row(monkeypatch):
    fake = _FakeScheduler()
    monkeypatch.setattr(jobs_svc, "_scheduler", fake)

    jobs_svc.register_daily_job("S23", "100")

    call = fake.calls[0]
    assert call["trigger"] == "cron"
    assert call["hour"] == 2 and call["minute"] == 0  # SAL_DAILY_COLLECTION_TIME unset -> 02:00 default


def test_register_daily_job_uses_interval_trigger_once_configured(monkeypatch):
    import sal.schedule as schedule_svc

    fake = _FakeScheduler()
    monkeypatch.setattr(jobs_svc, "_scheduler", fake)
    schedule_svc.set_schedule("S23", "interval", "tester", interval_hours=6)

    jobs_svc.register_daily_job("S23", "100")

    call = fake.calls[-1]
    assert call["trigger"] == "interval"
    assert call["hours"] == 6


def test_run_daily_checkpoint_returns_none_when_already_caught_up():
    today_str = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to=today_str, mode="scheduled", triggered_by="daily_scheduler")
    jobs_svc._finish_job(job_id, "success", today_str, None)

    result = jobs_svc.run_daily_checkpoint("S23", client="100")
    assert result is None


# ---- estimate_eta_seconds (requested directly, 2026-09-15: "the ETA column
# ---- is empty even for running jobs") ---------------------------------

def _complete_job(job_id: int, started_at: datetime, finished_at: datetime,
                   status: str = "success") -> None:
    """Direct SQL, not _claim_next_queued_job()/_finish_job() - those use
    datetime.now() internally, and these tests need exact, controllable
    started_at/finished_at values to construct a known historical duration.
    """
    from sal.storage.db import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collection_jobs SET status = ?, started_at = ?, finished_at = ? WHERE id = ?",
            (status, started_at.isoformat(), finished_at.isoformat(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _running_job(system_id: str, mode: str, dat_from: str, dat_to: str,
                  started_at: datetime) -> int:
    job_id = jobs_svc.submit_job(system_id=system_id, client="100", dat_from=dat_from,
                                  dat_to=dat_to, mode=mode, triggered_by="tester")
    from sal.storage.db import get_connection
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collection_jobs SET status = 'running', started_at = ? WHERE id = ?",
            (started_at.isoformat(), job_id),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def test_estimate_eta_seconds_returns_none_when_not_running():
    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    assert jobs_svc.estimate_eta_seconds(jobs_svc.get_job(job_id)) is None


def test_estimate_eta_seconds_none_for_adhoc_with_no_job_history():
    """The exact reported gap: a single-call ad-hoc job never has partial
    within-run progress, and with zero completed jobs of this system+mode
    to learn from, there is genuinely nothing to estimate from yet."""
    now = datetime.now(timezone.utc)
    job_id = _running_job("S23", "adhoc", "20260101", "20260107", now - timedelta(minutes=2))
    assert jobs_svc.estimate_eta_seconds(jobs_svc.get_job(job_id)) is None


def test_estimate_eta_seconds_uses_historical_average_for_adhoc_job():
    now = datetime.now(timezone.utc)
    # Two past 7-day ad-hoc pulls for S23, each took 70s -> 10s/day.
    for i in range(2):
        past_job = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                        dat_to="20260107", mode="adhoc", triggered_by="tester")
        started = now - timedelta(days=i + 1)
        _complete_job(past_job, started, started + timedelta(seconds=70))

    # A new 10-day ad-hoc pull, 20s in - expect ~10s/day * 10 days - 20s = 80s left.
    running = _running_job("S23", "adhoc", "20260201", "20260210", now - timedelta(seconds=20))
    eta = jobs_svc.estimate_eta_seconds(jobs_svc.get_job(running))
    assert eta is not None
    assert 75 <= eta <= 85


def test_estimate_eta_seconds_requires_at_least_two_historical_samples():
    now = datetime.now(timezone.utc)
    single_past = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                       dat_to="20260107", mode="adhoc", triggered_by="tester")
    _complete_job(single_past, now - timedelta(days=1), now - timedelta(days=1) + timedelta(seconds=70))

    running = _running_job("S23", "adhoc", "20260201", "20260210", now - timedelta(seconds=20))
    assert jobs_svc.estimate_eta_seconds(jobs_svc.get_job(running)) is None


def test_estimate_eta_seconds_does_not_mix_adhoc_and_scheduled_history():
    now = datetime.now(timezone.utc)
    for i in range(2):
        past_job = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                        dat_to="20260107", mode="scheduled", triggered_by="tester")
        started = now - timedelta(days=i + 1)
        _complete_job(past_job, started, started + timedelta(seconds=70))

    # Scheduled history exists, but this running job is ad-hoc - must not borrow it.
    running = _running_job("S23", "adhoc", "20260201", "20260210", now - timedelta(seconds=20))
    assert jobs_svc.estimate_eta_seconds(jobs_svc.get_job(running)) is None


def test_estimate_eta_seconds_falls_back_to_within_run_progress_for_multiday_job():
    """With no job-history baseline at all, a genuinely multi-day scheduled
    job that has already completed at least one day still gets the old
    within-run extrapolation - the one case that always worked before."""
    now = datetime.now(timezone.utc)
    running = _running_job("S99", "scheduled", "20260101", "20260110", now - timedelta(seconds=100))
    jobs_svc._update_progress(running, days_completed=2, days_total=10)

    eta = jobs_svc.estimate_eta_seconds(jobs_svc.get_job(running))
    assert eta is not None
    assert eta > 0
