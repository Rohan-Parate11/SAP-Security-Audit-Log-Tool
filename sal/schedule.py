"""Per-system daily-collection cadence (Blueprint v2, Phase G "Slice B").

Owns schedule_settings CRUD and validation only - deliberately does not
import sal/jobs.py (which would create a circular import, since jobs.py's
register_daily_job() needs to read the effective schedule from here). The
API layer (sal/web/api.py) is what sequences the two: write the row here,
then call jobs.register_daily_job() to apply it live - the same
write-then-reregister shape sal/web/api.py's system_update() already uses
for ashost/sysnr/client changes.

A system with no row here (never explicitly configured) falls back to the
SAL_DAILY_COLLECTION_TIME env var / 02:00 default - the same default
sal/jobs.py used before this module existed - so an existing install
upgrades without any system's daily job silently deregistering.
"""
import math
import os
from datetime import datetime, timezone

from .storage.db import get_connection, init_schema

_DEFAULT_ANCHOR = (2, 0)
_MIN_INTERVAL_HOURS = 1
_MAX_INTERVAL_HOURS = 168  # one week - beyond this, "daily" at a fixed time already covers it


def _default_anchor() -> tuple[int, int]:
    """The pre-Slice-B env var default, kept as the fallback for any system
    that has never had its cadence explicitly set through the Schedule tab.
    """
    time_str = os.environ.get("SAL_DAILY_COLLECTION_TIME", "02:00")
    try:
        hour, minute = (int(part) for part in time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except (ValueError, TypeError):
        return _DEFAULT_ANCHOR


def get_schedule(system_id: str) -> dict:
    """The *effective* schedule for a system - its own row if one has ever
    been saved, otherwise the env var/default fallback. Always returns a
    fully-populated dict so callers (register_daily_job(), the API) never
    need their own fallback logic.
    """
    init_schema()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM schedule_settings WHERE system_id = ?", (system_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        cfg = dict(row)
        # Defensive (found in review): set_schedule() is the only writer
        # today, and it never leaves the fields its own interval_type needs
        # as NULL - but a hand-edited row, a future direct-write path, or
        # partial DB corruption could. That must never reach APScheduler
        # as-is: CronTrigger(hour=None, minute=None) doesn't error, it
        # fires roughly once a second against a live SAP system, and
        # IntervalTrigger(hours=None) does raise but only in
        # register_daily_job(), after this function already returned
        # something that looked usable. Falling back to the safe env
        # var/default here is cheap insurance against a real hammering risk.
        if cfg["interval_type"] == "daily" and (cfg["anchor_hour"] is None or cfg["anchor_minute"] is None):
            hour, minute = _default_anchor()
            cfg.update(anchor_hour=hour, anchor_minute=minute, interval_hours=None)
        elif cfg["interval_type"] == "interval" and cfg["interval_hours"] is None:
            hour, minute = _default_anchor()
            cfg.update(interval_type="daily", anchor_hour=hour, anchor_minute=minute, interval_hours=None)
        return cfg
    hour, minute = _default_anchor()
    return {
        "system_id": system_id, "interval_type": "daily",
        "anchor_hour": hour, "anchor_minute": minute, "interval_hours": None,
        "updated_by": None, "updated_at": None,
    }


def _to_int(value: object, field_name: str) -> int:
    """Coerces a JSON-derived value to a plain int, rejecting anything that
    would otherwise reach APScheduler malformed: a bool (bool is an int
    subclass in Python, so True/False would otherwise silently become 1/0),
    a non-whole float (silently truncated otherwise), or an infinite/NaN
    float (int() raises OverflowError on inf, which is NOT a TypeError/
    ValueError - reproduced live via PUT .../schedule with
    {"interval_hours": Infinity}, valid JSON that Python's json module
    accepts by default - that OverflowError previously escaped uncaught as
    an unhandled 500 instead of the clean 400 this module promises).
    """
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a whole number, not a boolean")
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            raise ValueError(f"{field_name} must be a whole number")
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number") from None


def set_schedule(system_id: str, interval_type: str, actor: str,
                  anchor_hour: int | str | None = None, anchor_minute: int | str | None = None,
                  interval_hours: int | str | None = None) -> dict:
    """Validates and upserts one system's cadence. Raises ValueError (caught
    by the API layer and turned into a 400) on anything that would reach
    APScheduler's add_job() malformed - mutually exclusive fields, an
    out-of-range hour/minute, or an interval outside a sane bound (guarding
    against a fat-fingered "every 0 hours" hammering the SAP system, or an
    equally fat-fingered value so large it would effectively never fire).
    Numeric fields are coerced from whatever JSON gave us (a stray string
    from a form field is a ValueError here, not a TypeError deeper in).
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

    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO schedule_settings "
            "(system_id, interval_type, anchor_hour, anchor_minute, interval_hours, "
            " updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(system_id) DO UPDATE SET "
            "interval_type = excluded.interval_type, anchor_hour = excluded.anchor_hour, "
            "anchor_minute = excluded.anchor_minute, interval_hours = excluded.interval_hours, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (system_id, interval_type, anchor_hour, anchor_minute, interval_hours, actor, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_schedule(system_id)


def remove_schedule(system_id: str) -> None:
    """Deletes a system's explicit cadence row (reverting it to the env
    var/default fallback) - called from delete_system() so a stale row
    doesn't linger for a system_id that could later be reused, mirroring
    unregister_daily_job()'s own cleanup on system removal.
    """
    init_schema()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM schedule_settings WHERE system_id = ?", (system_id,))
        conn.commit()
    finally:
        conn.close()
