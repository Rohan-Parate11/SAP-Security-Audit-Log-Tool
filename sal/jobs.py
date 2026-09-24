"""Shared collection-job execution (Blueprint v2, Phase B).

Both the daily scheduler and the ad-hoc "Collect" UI submit through
submit_job() so neither has to separately remember to chunk, retry, or sync
findings afterward - the exact class of bug that left Phase A's findings
table empty for weeks (see sal/findings.py's docstring): two divergent
trigger paths, only one of which called sync_findings().

Chunking is mode-dependent, not a blanket rule (changed 2026-09-12 - see
Docs/CHANGELOG.md for the request that prompted it):

- Scheduled jobs (mode="scheduled") still split their [dat_from, dat_to]
  range into one collect_and_store() call per day, each its own
  collection_runs row that commits independently - the events table's
  composite primary key makes re-running an already-completed day a
  no-op, so a retried job resumes rather than re-fetching everything.
  This still matters here: a scheduler catch-up gap (the app was down a
  while) can span many unattended days, and losing all of it to one
  failure partway through would be worse than the granularity cost.
- Ad-hoc jobs (mode="adhoc", the "Collect" UI) run their whole
  [dat_from, dat_to] range as a SINGLE collect_and_store() call instead -
  the user submitted one query ("last week's data") and is actively
  watching it, not an unattended multi-day catch-up; they don't want that
  one query to look like N separate collection_runs entries. This trades
  away per-day resumability (a failure means retrying the whole range,
  not just the day it failed on) and per-day progress - accepted
  knowingly, not an oversight, since RSAU_API_GET_LOG_DATA's own
  IS_INTERVAL parameter already accepts a date range natively; the
  chunking was never a technical necessity for a single ad-hoc pull, only
  a resumability nicety that a scheduled catch-up benefits from far more
  than a one-shot ad-hoc query does.

Either way, a day (scheduled) or the whole range (ad-hoc) is retried up to
_MAX_RETRIES times before the job gives up, with last_completed_date left
at the last day/range that actually succeeded.

Concurrency: exactly one background worker thread is started (see
start_worker(), called once from sal/web/__init__.py) and it processes one
queued job fully - chunking, retries, and the final sync_findings() call -
before picking up the next one. That serialization is what keeps SQLite from
seeing two collection+sync writers at once; there is deliberately no
additional lock, since a single worker thread already guarantees it.

scripts/collect_sm20.py deliberately does NOT go through this module - its
whole value is a direct, immediate, unchunked CLI pull for manual
backfills/testing (this is how Phase A's 30-day reference dataset was
collected), and it doesn't run inside the Flask process where the worker
thread lives.
"""
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import findings as findings_svc
from . import schedule
from .collectors import collect_and_store
from .storage.db import get_connection, init_schema

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_POLL_INTERVAL_SECONDS = 1.0
_worker_started = False


def _daterange(dat_from: str, dat_to: str):
    start = datetime.strptime(dat_from, "%Y%m%d").date()
    end = datetime.strptime(dat_to, "%Y%m%d").date()
    d = start
    while d <= end:
        yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


JOB_CLASSES = ("A", "B", "C")  # SAP SM36's own vocabulary: High/Medium/Low - the
# single source of truth for this enum; sal/web/api.py imports this rather
# than re-typing the tuple, so the two can never silently drift apart.


def submit_job(system_id: str, client: str | None, dat_from: str, dat_to: str,
               mode: str, triggered_by: str, tim_from: str = "000000",
               tim_to: str = "235959", user=None, transaction_code=None,
               report=None, instance=None, msg_code=None,
               job_name: str | None = None, job_description: str | None = None,
               job_class: str = "B") -> int:
    if job_class not in JOB_CLASSES:
        raise ValueError(f"job_class must be one of {JOB_CLASSES}")
    init_schema()
    filters = {
        "dat_from": dat_from, "dat_to": dat_to, "tim_from": tim_from, "tim_to": tim_to,
        "user": user, "transaction_code": transaction_code, "report": report,
        "instance": instance, "msg_code": msg_code,
    }
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO collection_jobs "
            "(system_id, client, mode, filters_json, status, triggered_by, submitted_at, "
            " job_name, job_description, job_class) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
            (system_id, client, mode, json.dumps(filters), triggered_by, now,
             job_name or None, job_description or None, job_class),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_job(job_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


_IN_CLAUSE_COLUMNS = ("job_class", "mode", "status")  # every column this
# module's own call sites are allowed to pass to _add_in_clause() below -
# `column` is always one of these hardcoded literals today anyway (never
# request-derived), but asserting it here means a future call site that
# somehow passed request input instead would fail loudly in dev/tests
# rather than silently becoming a SQL injection vector.


def _add_in_clause(clauses: list[str], params: list, column: str, values: str | list[str] | None) -> None:
    """Appends a `column IN (?, ?, ...)` clause when `values` is non-empty -
    a single string is treated as a one-item list, so existing single-value
    callers keep working unchanged. `column` is always a fixed, hardcoded
    string from this module's own code, never request input, so building
    the placeholder list dynamically from len(values) is safe - only the
    values themselves (parameterized, never interpolated) can vary.
    """
    assert column in _IN_CLAUSE_COLUMNS, f"unexpected column {column!r} passed to _add_in_clause"
    if values is None:
        return
    if isinstance(values, str):
        values = [values]
    values = [v for v in values if v]
    if not values:
        return
    clauses.append(f"{column} IN ({', '.join('?' for _ in values)})")
    params.extend(values)


def list_jobs(system_id: str | None = None, client: str | None = None,
              limit: int = 50, offset: int = 0, job_name: str | None = None,
              mode: str | list[str] | None = None, status: str | list[str] | None = None,
              date_from: str | None = None, date_to: str | None = None,
              job_class: str | list[str] | None = None, view: str = "active") -> tuple[int, list[dict]]:
    """Returns (total, items) - total is the full matching count before
    LIMIT/OFFSET, so the Jobs page can paginate instead of only ever
    seeing the most recent `limit` jobs (the same discoverability bug
    fixed for collection_runs applies here once Collection History folds
    into this list - see sal/web/api.py's list_jobs() route).
    job_name filters job_name/job_description (collection_jobs has both as
    direct columns - no join needed, unlike collection_runs' job_name
    which requires one back to this table). date_from/date_to bound
    submitted_at as a lexical string range, not via SQL date() parsing -
    same reasoning as sal/web/api.py's collection_runs() date filter.
    mode/status/job_class each accept either a single value (unchanged,
    existing callers) or a list - added for the Jobs/Recovery tables'
    Excel-style column-header filters, where checking multiple boxes in
    one column means "any of these" (SQL IN), not "exactly one of these".
    """
    conn = get_connection()
    try:
        clauses, params = [], []
        clauses.append("deleted_at IS NOT NULL" if view == "deleted" else "deleted_at IS NULL")
        if system_id:
            clauses.append("system_id = ?")
            params.append(system_id)
        if client:
            clauses.append("client = ?")
            params.append(client)
        if job_name:
            clauses.append("(job_name LIKE ? OR job_description LIKE ?)")
            params.extend([f"%{job_name}%", f"%{job_name}%"])
        _add_in_clause(clauses, params, "job_class", job_class)
        _add_in_clause(clauses, params, "mode", mode)
        _add_in_clause(clauses, params, "status", status)
        if date_from:
            clauses.append("submitted_at >= ?")
            params.append(f"{date_from}T00:00:00")
        if date_to:
            # Let ValueError propagate (caught by the API route -> 400) -
            # found in review: silently swallowing it here and dropping
            # the clause meant a regex-shaped-but-not-a-real-date date_to
            # (e.g. "2026-02-30") returned an unfiltered result set
            # instead of an error, diverging from collection_runs()'s
            # sibling behavior for the exact same input shape.
            next_day = date.fromisoformat(date_to) + timedelta(days=1)
            clauses.append("submitted_at < ?")
            params.append(f"{next_day.isoformat()}T00:00:00")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = conn.execute(f"SELECT COUNT(*) c FROM collection_jobs {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM collection_jobs {where} ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return total, [dict(r) for r in rows]
    finally:
        conn.close()


def last_scheduled_checkpoint(system_id: str) -> str | None:
    """Most recent dat_to a *scheduled* job actually completed through.

    Ad-hoc pulls never move this cursor, even if they cover overlapping or
    later dates - only the daily job's own history determines where it
    resumes from.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_completed_date FROM collection_jobs "
            "WHERE system_id = ? AND mode = 'scheduled' AND last_completed_date IS NOT NULL "
            "ORDER BY submitted_at DESC LIMIT 1",
            (system_id,),
        ).fetchone()
        return row["last_completed_date"] if row else None
    finally:
        conn.close()


def run_daily_checkpoint(system_id: str, client: str | None = None,
                          default_lookback_days: int = 7) -> int | None:
    """Submit today's scheduled job for one system, resuming from its last
    successful scheduled checkpoint. On the very first run for a system
    (no prior scheduled job has ever completed), falls back to
    default_lookback_days so it doesn't try to pull the system's entire
    history. Returns None (submits nothing) if already caught up through
    today.
    """
    checkpoint = last_scheduled_checkpoint(system_id)
    today = datetime.now(timezone.utc).date()
    if checkpoint:
        dat_from = (datetime.strptime(checkpoint, "%Y%m%d").date()
                    + timedelta(days=1)).strftime("%Y%m%d")
    else:
        dat_from = (today - timedelta(days=default_lookback_days)).strftime("%Y%m%d")
    dat_to = today.strftime("%Y%m%d")

    if dat_from > dat_to:
        return None

    # job_class='A' (High) - the detection-feed baseline must not get stuck
    # behind a pile of ad-hoc requests in the single-worker-thread queue.
    return submit_job(system_id=system_id, client=client, dat_from=dat_from,
                       dat_to=dat_to, mode="scheduled", triggered_by="daily_scheduler",
                       job_class="A")


# ---- Daily scheduler ownership --------------------------------------------
#
# Lives here (not in sal/web/__init__.py) so the Jobs page can ask
# next_scheduled_run() directly, and so a system added via the Systems UI
# can register its own daily job immediately (register_daily_job(), called
# from the /api/systems route) instead of requiring an app restart.

_scheduler = None


def register_daily_job(system_id: str, client: str | None) -> None:
    """Reads this system's *effective* cadence from sal/schedule.py fresh on
    every call (deliberately uncached, unlike the pre-Slice-B single
    process-wide time this replaced) - correctness over a caching
    micro-optimization, since a stale cache here would mean a schedule
    change made through the UI silently not taking effect until a process
    restart. Called synchronously from the /api/systems add/edit routes and
    from PUT /api/systems/<id>/schedule, so this must stay cheap - it's one
    indexed primary-key lookup, not a scan.
    """
    if _scheduler is None:
        return
    system_id = system_id.strip().upper()
    cfg = schedule.get_schedule(system_id)
    if cfg["interval_type"] == "interval":
        _scheduler.add_job(
            run_daily_checkpoint, "interval", hours=cfg["interval_hours"],
            kwargs={"system_id": system_id, "client": client},
            id=f"daily-{system_id}", replace_existing=True,
        )
    else:
        _scheduler.add_job(
            run_daily_checkpoint, "cron", hour=cfg["anchor_hour"], minute=cfg["anchor_minute"],
            kwargs={"system_id": system_id, "client": client},
            id=f"daily-{system_id}", replace_existing=True,
        )


def unregister_daily_job(system_id: str) -> None:
    if _scheduler is None:
        return
    from apscheduler.jobstores.base import JobLookupError

    system_id = system_id.strip().upper()
    try:
        _scheduler.remove_job(f"daily-{system_id}")
    except JobLookupError:
        pass


def next_scheduled_run(system_id: str) -> str | None:
    if _scheduler is None:
        return None
    system_id = system_id.strip().upper()
    job = _scheduler.get_job(f"daily-{system_id}")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


# ---- Daily retention purge -------------------------------------------------
#
# Registered on the same scheduler, one hour after the default collection
# time (03:00 vs. 02:00) so the purge doesn't run concurrently with a daily
# collection cycle touching the same events/findings tables (see
# sal/retention.py's docstring).

_RETENTION_JOB_ID = "retention-purge"
_DEFAULT_RETENTION_TIME = (3, 0)


def _retention_purge_time() -> tuple[int, int]:
    global _RETENTION_TIME_CACHE
    try:
        return _RETENTION_TIME_CACHE
    except NameError:
        pass
    time_str = os.environ.get("SAL_RETENTION_PURGE_TIME", "03:00")
    try:
        hour, minute = (int(part) for part in time_str.split(":"))
    except (ValueError, TypeError):
        hour, minute = _DEFAULT_RETENTION_TIME
    _RETENTION_TIME_CACHE = (hour, minute)
    return _RETENTION_TIME_CACHE


def register_retention_job() -> None:
    if _scheduler is None:
        return
    from . import retention

    hour, minute = _retention_purge_time()
    _scheduler.add_job(
        retention.run_purge, "cron", hour=hour, minute=minute,
        kwargs={"actor": "daily_scheduler"},
        id=_RETENTION_JOB_ID, replace_existing=True,
    )


def next_retention_run() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(_RETENTION_JOB_ID)
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


# ---- Daily role-context refresh (Phase F) ----------------------------------
#
# One per registered system, like the collection job - registered/removed
# alongside it from the /api/systems routes. Runs before the default daily
# collection time (01:00 vs. 02:00) so that day's end-of-collection
# sync_findings() call already sees freshly-refreshed role data.

_DEFAULT_ROLE_CONTEXT_TIME = (1, 0)


def _role_context_refresh_time() -> tuple[int, int]:
    global _ROLE_CONTEXT_TIME_CACHE
    try:
        return _ROLE_CONTEXT_TIME_CACHE
    except NameError:
        pass
    time_str = os.environ.get("SAL_ROLE_CONTEXT_REFRESH_TIME", "01:00")
    try:
        hour, minute = (int(part) for part in time_str.split(":"))
    except (ValueError, TypeError):
        hour, minute = _DEFAULT_ROLE_CONTEXT_TIME
    _ROLE_CONTEXT_TIME_CACHE = (hour, minute)
    return _ROLE_CONTEXT_TIME_CACHE


def register_role_context_job(system_id: str) -> None:
    if _scheduler is None:
        return
    from . import role_context

    system_id = system_id.strip().upper()
    hour, minute = _role_context_refresh_time()
    _scheduler.add_job(
        role_context.sync_role_context, "cron", hour=hour, minute=minute,
        kwargs={"system_id": system_id, "actor": "daily_scheduler"},
        id=f"role-context-{system_id}", replace_existing=True,
    )


def unregister_role_context_job(system_id: str) -> None:
    if _scheduler is None:
        return
    from apscheduler.jobstores.base import JobLookupError

    system_id = system_id.strip().upper()
    try:
        _scheduler.remove_job(f"role-context-{system_id}")
    except JobLookupError:
        pass


def next_role_context_run(system_id: str) -> str | None:
    if _scheduler is None:
        return None
    system_id = system_id.strip().upper()
    job = _scheduler.get_job(f"role-context-{system_id}")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


# ---- Recurring filtered collection schedules (sal/filtered_schedule.py) ---
#
# Genuinely separate from the baseline above: any number of rows per
# system, each its own APScheduler job id, submitted with mode=
# FILTERED_SCHEDULED_MODE (never "scheduled" - last_scheduled_checkpoint()
# only looks at mode='scheduled' rows to resume the comprehensive baseline,
# and a filtered pull's last_completed_date must never be mistaken for
# baseline progress, or the real detection-feed collection would silently
# skip days it never actually pulled unfiltered).

FILTERED_SCHEDULED_MODE = "filtered_scheduled"


def run_filtered_schedule(schedule_id: int) -> int | None:
    """Submit one recurring filtered pull for its saved window (see
    sal/filtered_schedule.py's module docstring for why this is a fixed
    rolling window, not a checkpoint-based catch-up). Returns None (submits
    nothing) if the schedule was deleted or disabled since this firing was
    registered - APScheduler can still hold a stale job momentarily between
    a delete/disable and its own unregister call completing.
    """
    from . import filtered_schedule

    cfg = filtered_schedule.get_schedule(schedule_id)
    if cfg is None or not cfg["enabled"]:
        return None
    dat_from, dat_to = filtered_schedule.window_for_run()
    return submit_job(
        system_id=cfg["system_id"], client=cfg.get("client"),
        dat_from=dat_from, dat_to=dat_to, mode=FILTERED_SCHEDULED_MODE,
        triggered_by="filtered_scheduler",
        user=cfg["user_filter"], transaction_code=cfg["transaction_code"],
        report=cfg["report"], instance=cfg["instance"], msg_code=cfg["msg_code"],
        job_name=cfg["name"], job_class="B",
    )


def register_filtered_schedule_job(schedule_id: int) -> None:
    """Mirrors register_daily_job() exactly (see that function's own
    docstring) - reads the schedule row fresh via run_filtered_schedule()'s
    own lookup rather than trusting a cached cfg, for the identical
    correctness reason: a change made through the UI must take effect
    without a process restart.
    """
    if _scheduler is None:
        return
    from . import filtered_schedule

    cfg = filtered_schedule.get_schedule(schedule_id)
    if cfg is None:
        return
    if cfg["interval_type"] == "interval":
        _scheduler.add_job(
            run_filtered_schedule, "interval", hours=cfg["interval_hours"],
            kwargs={"schedule_id": schedule_id},
            id=f"filtered-{schedule_id}", replace_existing=True,
        )
    else:
        _scheduler.add_job(
            run_filtered_schedule, "cron", hour=cfg["anchor_hour"], minute=cfg["anchor_minute"],
            kwargs={"schedule_id": schedule_id},
            id=f"filtered-{schedule_id}", replace_existing=True,
        )


def unregister_filtered_schedule_job(schedule_id: int) -> None:
    if _scheduler is None:
        return
    from apscheduler.jobstores.base import JobLookupError

    try:
        _scheduler.remove_job(f"filtered-{schedule_id}")
    except JobLookupError:
        pass


def next_filtered_schedule_run(schedule_id: int) -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(f"filtered-{schedule_id}")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


def start_daily_scheduler() -> None:
    """Start the single APScheduler instance, once per process, with one
    collection cron job and one role-context refresh cron job per
    currently-registered system, one job per currently-enabled recurring
    filtered schedule, plus the daily retention purge.
    """
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from . import filtered_schedule
    from . import systems as systems_svc

    _scheduler = BackgroundScheduler(daemon=True)
    for system in systems_svc.list_systems():
        register_daily_job(system["system_id"], system.get("client") or None)
        register_role_context_job(system["system_id"])
    for cfg in filtered_schedule.list_all_enabled():
        register_filtered_schedule_job(cfg["id"])
    register_retention_job()
    _scheduler.start()


def _claim_next_queued_job() -> dict | None:
    conn = get_connection()
    try:
        # job_class ASC first ('A' < 'B' < 'C', i.e. High before Medium
        # before Low - SM36/SM37 parity), submitted_at as the tiebreaker
        # within the same priority so same-class jobs still process FIFO.
        row = conn.execute(
            "SELECT * FROM collection_jobs WHERE status = 'queued' "
            "ORDER BY job_class ASC, submitted_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE collection_jobs SET status = 'running', started_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()
        job = dict(row)
        job["status"] = "running"
        job["started_at"] = now
        return job
    finally:
        conn.close()


def _finish_job(job_id: int, status: str, last_completed_date: str | None,
                 error_message: str | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collection_jobs SET status = ?, finished_at = ?, "
            "last_completed_date = ?, error_message = ? WHERE id = ?",
            (status, now, last_completed_date, error_message, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _update_progress(job_id: int, days_completed: int, days_total: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collection_jobs SET days_completed = ?, days_total = ? WHERE id = ?",
            (days_completed, days_total, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _range_days_from_filters(filters_json: str | None) -> int | None:
    """Calendar-day span of a job's own requested [dat_from, dat_to] - the
    real normalizer for "how much work was this job," since days_total
    (the progress-tracking column) means something different per mode:
    always 1 for ad-hoc (a single unchunked call regardless of how wide
    the requested range is - see this module's own docstring) and the
    count of still-remaining days for a scheduled catch-up. Returns None
    for a malformed/missing filters_json rather than raising - a
    historical row this can't parse is simply skipped by the caller, not
    fatal to the whole estimate.
    """
    if not filters_json:
        return None
    try:
        filters = json.loads(filters_json)
        start = datetime.strptime(filters["dat_from"], "%Y%m%d").date()
        end = datetime.strptime(filters["dat_to"], "%Y%m%d").date()
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    days = (end - start).days + 1
    return days if days > 0 else None


# Most recent completed jobs to average over, for a given (system_id, mode) -
# recent performance is a better predictor than an all-time average (a
# system that's gotten slower/faster over months shouldn't be diluted by
# very old runs).
_ETA_HISTORY_SAMPLE_SIZE = 10
# A single past job could be a fluke (one network hiccup, one
# exceptionally quiet/busy day) - require at least two before trusting an
# average enough to show a number.
_ETA_MIN_HISTORY_SAMPLES = 2


def _historical_seconds_per_day(system_id: str, mode: str) -> float | None:
    """Average (wall-clock duration / calendar-day-span) across this
    system+mode's most recent completed jobs. Scoped by mode, not just
    system_id, because an ad-hoc job's single unchunked RFC call and a
    scheduled job's one-call-per-day chunking have genuinely different
    per-day overhead - averaging them together would misestimate both.
    Only 'success'/'partial' jobs count - an 'error' job may have failed
    fast (never did the real work) or slow (already an outlier), neither
    of which represents a normal completed duration.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT filters_json, started_at, finished_at FROM collection_jobs "
            "WHERE system_id = ? AND mode = ? AND status IN ('success', 'partial') "
            "AND deleted_at IS NULL AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "ORDER BY finished_at DESC LIMIT ?",
            (system_id, mode, _ETA_HISTORY_SAMPLE_SIZE),
        ).fetchall()
    finally:
        conn.close()

    rates = []
    for row in rows:
        range_days = _range_days_from_filters(row["filters_json"])
        if not range_days:
            continue
        elapsed = (
            datetime.fromisoformat(row["finished_at"]) - datetime.fromisoformat(row["started_at"])
        ).total_seconds()
        if elapsed <= 0:
            continue
        rates.append(elapsed / range_days)

    if len(rates) < _ETA_MIN_HISTORY_SAMPLES:
        return None
    return sum(rates) / len(rates)


def estimate_eta_seconds(job: dict) -> float | None:
    """Rough ETA for a running job.

    Primary method (added 2026-09-15, requested directly - "the ETA
    column is empty even for running jobs"): extrapolate from how long
    this SAME system's past completed jobs of the SAME mode actually took
    per calendar day requested, applied to this job's own requested range.
    This is what makes ETA available at all for the common case: an
    ad-hoc job (always a single unchunked call, so it never has a
    "day 1 of N done" partial-progress signal to extrapolate from) and a
    single-day scheduled job (the ordinary daily case once a system is
    caught up) previously NEVER got an ETA while running - the old method
    below requires at least one fully completed day of a multi-day job
    before it has anything to extrapolate from, which a single-call/
    single-day job by definition never reaches while still "running."

    Falls back to the old within-this-job progress-based estimate
    (meaningful only for a genuinely multi-day scheduled catch-up, once
    its first day has completed) when there isn't yet enough job history
    for this system+mode to trust an average - a system's very first job
    of a given mode, for instance, has no history to learn from either
    way, and still gets nothing until either it or a sibling job completes
    once.
    """
    if job.get("status") != "running":
        return None
    started_at = job.get("started_at")
    if not started_at:
        return None
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds()

    range_days = _range_days_from_filters(job.get("filters_json"))
    if range_days:
        seconds_per_day = _historical_seconds_per_day(job["system_id"], job["mode"])
        if seconds_per_day is not None:
            expected_total = seconds_per_day * range_days
            return round(max(0.0, expected_total - elapsed), 1)

    days_completed = job.get("days_completed") or 0
    days_total = job.get("days_total") or 0
    if days_completed < 1 or days_total <= days_completed:
        return None
    rate_per_day = elapsed / days_completed
    return round(rate_per_day * (days_total - days_completed), 1)


def _collect_chunk(job: dict, filters: dict, dat_from: str, dat_to: str) -> str | None:
    """Runs collect_and_store() for [dat_from, dat_to], retried up to
    _MAX_RETRIES times - the same single day for a chunked scheduled job,
    or the whole requested range for an ad-hoc job that isn't chunked at
    all. Returns the error message on failure, None on success.
    """
    error = None
    for _ in range(_MAX_RETRIES):
        summary = collect_and_store(
            system_id=job["system_id"], client=job["client"],
            dat_from=dat_from, dat_to=dat_to,
            tim_from=filters.get("tim_from", "000000"),
            tim_to=filters.get("tim_to", "235959"),
            user=filters.get("user"), transaction_code=filters.get("transaction_code"),
            report=filters.get("report"), instance=filters.get("instance"),
            msg_code=filters.get("msg_code"), actor=job["triggered_by"],
            job_id=job["id"],
        )
        if summary.get("status") == "success":
            return None
        error = summary.get("error") or "collection failed"
    return error


def run_job(job: dict) -> None:
    """Execute one job to completion, sync once. See this module's
    docstring for why scheduled jobs chunk by day while ad-hoc jobs run
    their whole range as a single collect_and_store() call.
    """
    filters = json.loads(job["filters_json"] or "{}")
    dat_from, dat_to = filters["dat_from"], filters["dat_to"]

    last_completed = None
    error_message = None

    if job["mode"] == "adhoc":
        _update_progress(job["id"], 0, 1)
        error_message = _collect_chunk(job, filters, dat_from, dat_to)
        if not error_message:
            last_completed = dat_to
        _update_progress(job["id"], 0 if error_message else 1, 1)
    else:
        days = list(_daterange(dat_from, dat_to))
        days_total = len(days)
        _update_progress(job["id"], 0, days_total)
        for index, day in enumerate(days):
            error_message = _collect_chunk(job, filters, day, day)
            if error_message:
                break
            last_completed = day
            _update_progress(job["id"], index + 1, days_total)

    # Sync whatever was collected even on partial/no success - a day (or
    # range) that succeeded before a later failure should still produce
    # findings for what did land.
    findings_svc.sync_findings(system_id=job["system_id"], client=job["client"])

    if error_message:
        status = "partial" if last_completed else "error"
    else:
        status = "success"
    _finish_job(job["id"], status, last_completed, error_message)


def _worker_loop() -> None:
    while True:
        try:
            job = _claim_next_queued_job()
        except Exception:  # noqa: BLE001 - a transient DB error must not kill the worker
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue
        if job is None:
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue
        try:
            run_job(job)
        except Exception as exc:  # noqa: BLE001 - a bad job must not kill the worker
            try:
                _finish_job(job["id"], "error", None, str(exc))
            except Exception:  # noqa: BLE001 - e.g. "database is locked" from a
                # concurrent writer (retention.run_purge()) - losing this one
                # status update must not take the whole worker thread down.
                logger.exception(
                    "Failed to record job %s as errored after: %s", job["id"], exc
                )


_INTERRUPTED_MESSAGE = "Interrupted by a process restart - please re-run this collection."


def reconcile_stale_state() -> None:
    """Mark any row left at 'running' as 'error' on a fresh process start.

    Within one live process, a 'running' row can only belong to the single
    active worker thread - so on a brand new start, before that thread has
    claimed anything, any row already sitting at 'running' is necessarily
    left over from a previous process that crashed or was killed mid-job,
    not a job actually in flight. Covers both collection_jobs (the Phase B
    job record) and collection_runs (the per-day chunk collect_and_store()
    writes), since either can be interrupted mid-write by a process-level
    crash rather than a normal exception.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE collection_jobs SET status = 'error', finished_at = ?, "
            "error_message = ? WHERE status = 'running'",
            (now, _INTERRUPTED_MESSAGE),
        )
        conn.execute(
            "UPDATE collection_runs SET status = 'error', finished_at = ?, "
            "error_message = ? WHERE status = 'running'",
            (now, _INTERRUPTED_MESSAGE),
        )
        conn.commit()
    finally:
        conn.close()


def start_worker() -> None:
    """Start the single background worker thread, once per process."""
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    # The worker's first poll happens almost immediately on a background
    # thread - the schema must already exist by then, since
    # _claim_next_queued_job() doesn't call init_schema() itself (unlike
    # submit_job()). Confirmed necessary: without this, the worker thread
    # crashed on a fresh app startup with "no such table: collection_jobs".
    init_schema()
    reconcile_stale_state()
    threading.Thread(target=_worker_loop, daemon=True, name="sal-job-worker").start()
