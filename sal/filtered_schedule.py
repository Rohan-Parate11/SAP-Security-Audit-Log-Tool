"""Recurring FILTERED collection schedules - distinct from and additional to
sal/schedule.py's single per-system comprehensive baseline schedule.

Requested directly: "the schedule button is only for changing the daily
scheduled job which is prebuilt in our tool. in the same way, if I want
to schedule an ad hoc job to run on daily or whatever basis, I should be
able to do that as well." The baseline schedule (sal/schedule.py) is
deliberately never filterable - it's the sole feed for every detection
rule and must stay comprehensive by construction (see
tests/test_jobs.py's test_run_daily_checkpoint_never_submits_any_filters).
This module is a genuinely separate, supplementary capability: save a
Collect-style filtered pull (specific user(s)/transaction code(s)/report/
instance/message code(s)) and have it run on its own recurring cadence.
Unlike the baseline (one row per system), a system can have any number of
these - "daily SU01 check for these 3 users" and "hourly check of
FB01N" can both exist for the same system at once, which is why this is
its own table keyed by a surrogate id, not an upsert-by-system_id row
like schedule_settings.

No catch-up/resume, deliberately unlike the baseline's day-by-day
checkpoint: each firing just pulls a fixed 2-calendar-day rolling window
(today and yesterday, full day) regardless of interval_type, relying on
events' own natural-key INSERT OR IGNORE dedup to make repeated/
overlapping pulls harmless. This sidesteps a real ambiguity in trying to
express a genuine sub-day rolling window: RSAU_API_GET_LOG_DATA's
TIM_FROM/TIM_TO apply as a time-of-day slice repeated across every day in
[DAT_FROM, DAT_TO], not as a single continuous datetime span (confirmed
in sal/collectors/sm20.py and documented in the Analyst User Guide) - so
there is no clean way to express "the last 6 hours" as one interval
call when that window crosses midnight. A missed firing (app was down)
simply isn't backfilled - these are supplementary/investigative pulls,
not the primary detection feed, so that tradeoff is acceptable here in a
way it deliberately is NOT for the baseline.
"""
from datetime import datetime, timedelta, timezone

from .schedule import _MAX_INTERVAL_HOURS, _MIN_INTERVAL_HOURS, _to_int
from .storage.db import get_connection, init_schema

_LOOKBACK_DAYS = 1  # yesterday + today, every firing - see module docstring


def window_for_run() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    dat_from = (today - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    dat_to = today.strftime("%Y%m%d")
    return dat_from, dat_to


def list_schedules(system_id: str, client: str | None = None) -> list[dict]:
    init_schema()
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?"], [system_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        rows = conn.execute(
            f"SELECT * FROM filtered_schedules WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at ASC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_schedule(schedule_id: int) -> dict | None:
    init_schema()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM filtered_schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_all_enabled() -> list[dict]:
    """Every currently-enabled filtered schedule, across all systems - used
    once at process startup to register each one's APScheduler job (see
    sal/jobs.py's start_daily_scheduler())."""
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM filtered_schedules WHERE enabled = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _validate_cadence(interval_type: str, anchor_hour, anchor_minute, interval_hours):
    """Mirrors sal/schedule.py's set_schedule() validation exactly (same
    _to_int() coercion, same bounds) - kept as its own function here rather
    than imported wholesale since the two modules' persistence shapes
    (upsert-by-system_id vs. insert/update-by-surrogate-id) differ enough
    that sharing the write path isn't worth the coupling, but the
    validation RULES must stay identical - both ultimately hand these same
    fields to APScheduler.
    """
    if interval_type not in ("daily", "interval"):
        raise ValueError("interval_type must be 'daily' or 'interval'")

    if anchor_hour is not None:
        anchor_hour = _to_int(anchor_hour, "anchor_hour")
    if anchor_minute is not None:
        anchor_minute = _to_int(anchor_minute, "anchor_minute")
    if interval_hours is not None:
        interval_hours = _to_int(interval_hours, "interval_hours")

    if interval_type == "daily":
        if anchor_hour is None or anchor_minute is None:
            raise ValueError("anchor_hour and anchor_minute are required for 'daily'")
        if not (0 <= anchor_hour <= 23):
            raise ValueError("anchor_hour must be between 0 and 23")
        if not (0 <= anchor_minute <= 59):
            raise ValueError("anchor_minute must be between 0 and 59")
        interval_hours = None
    else:
        if interval_hours is None:
            raise ValueError("interval_hours is required for 'interval'")
        if not (_MIN_INTERVAL_HOURS <= interval_hours <= _MAX_INTERVAL_HOURS):
            raise ValueError(
                f"interval_hours must be between {_MIN_INTERVAL_HOURS} and {_MAX_INTERVAL_HOURS}"
            )
        anchor_hour = anchor_minute = None
    return anchor_hour, anchor_minute, interval_hours


def add_schedule(system_id: str, client: str | None, name: str, actor: str,
                  interval_type: str, anchor_hour=None, anchor_minute=None, interval_hours=None,
                  user: str | None = None, transaction_code: str | None = None,
                  report: str | None = None, instance: str | None = None,
                  msg_code: str | None = None) -> dict:
    if not name or not name.strip():
        raise ValueError("name is required")
    anchor_hour, anchor_minute, interval_hours = _validate_cadence(
        interval_type, anchor_hour, anchor_minute, interval_hours
    )

    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO filtered_schedules "
            "(system_id, client, name, user_filter, transaction_code, report, instance, msg_code, "
            " interval_type, anchor_hour, anchor_minute, interval_hours, enabled, "
            " created_by, created_at, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (system_id, client, name.strip(), user or None, transaction_code or None,
             report or None, instance or None, msg_code or None,
             interval_type, anchor_hour, anchor_minute, interval_hours,
             actor, now, actor, now),
        )
        conn.commit()
        return get_schedule(cur.lastrowid)
    finally:
        conn.close()


def update_schedule(schedule_id: int, actor: str, name: str | None = None,
                     interval_type: str | None = None, anchor_hour=None, anchor_minute=None,
                     interval_hours=None, enabled: bool | None = None,
                     user: str | None = None, transaction_code: str | None = None,
                     report: str | None = None, instance: str | None = None,
                     msg_code: str | None = None) -> dict | None:
    """Full-replace semantics for the filter/cadence fields (matching how
    the Collect-page edit form always resubmits every field, not a partial
    PATCH) - only `enabled` is a true optional toggle, since that's reached
    via its own pause/resume control, separate from the edit form.
    """
    existing = get_schedule(schedule_id)
    if existing is None:
        return None

    effective_interval_type = interval_type if interval_type is not None else existing["interval_type"]
    if anchor_hour is None and anchor_minute is None and interval_hours is None and interval_type is None:
        anchor_hour, anchor_minute, interval_hours = (
            existing["anchor_hour"], existing["anchor_minute"], existing["interval_hours"]
        )
    anchor_hour, anchor_minute, interval_hours = _validate_cadence(
        effective_interval_type, anchor_hour, anchor_minute, interval_hours
    )
    if name is not None and not name.strip():
        raise ValueError("name is required")

    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE filtered_schedules SET name = ?, user_filter = ?, transaction_code = ?, "
            "report = ?, instance = ?, msg_code = ?, interval_type = ?, anchor_hour = ?, "
            "anchor_minute = ?, interval_hours = ?, enabled = ?, updated_by = ?, updated_at = ? "
            "WHERE id = ?",
            (
                (name or existing["name"]).strip(),
                user if user is not None else existing["user_filter"],
                transaction_code if transaction_code is not None else existing["transaction_code"],
                report if report is not None else existing["report"],
                instance if instance is not None else existing["instance"],
                msg_code if msg_code is not None else existing["msg_code"],
                effective_interval_type, anchor_hour, anchor_minute, interval_hours,
                1 if (enabled if enabled is not None else existing["enabled"]) else 0,
                actor, now, schedule_id,
            ),
        )
        conn.commit()
        return get_schedule(schedule_id)
    finally:
        conn.close()


def remove_schedule(schedule_id: int) -> dict | None:
    """Hard delete, unlike collection_jobs/collection_runs' soft-delete -
    a saved filter/cadence definition has no ongoing audit value once
    removed the way a job's own execution history does; the removal
    itself is still attributed via the API route's own audit.record()
    call (reason required there), same as every other delete in this app.
    Returns the row as it was just before deletion (None if it never
    existed) so the caller can unregister the matching APScheduler job.
    """
    existing = get_schedule(schedule_id)
    if existing is None:
        return None
    conn = get_connection()
    try:
        conn.execute("DELETE FROM filtered_schedules WHERE id = ?", (schedule_id,))
        conn.commit()
    finally:
        conn.close()
    return existing
