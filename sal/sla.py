"""SLA/aging classification for open findings (Blueprint v2 add-on).

"Business day" = Monday-Friday in UTC, no holiday calendar - the simplest
defensible default given no holiday-calendar infrastructure exists anywhere
in this codebase (see Docs/Open_Questions_For_Review.txt, item 8). This is a
known simplification, not a hidden assumption - revisit if real
holiday-awareness is needed.

Thresholds, in business days from first_seen_at (when a finding was first
computed, not when it was detected in SAP - matches "time an analyst could
have acted on this"): High 1, Medium 3, Low 7. Only meaningful for
currently-open findings; callers should not pass disposed ones in.
"""
from datetime import datetime, timedelta, timezone

SLA_BUSINESS_DAYS = {"High": 1, "Medium": 3, "Low": 7}

_AT_RISK_FRACTION = 0.75


def business_days_between(start: datetime, end: datetime) -> float:
    """Business days elapsed between two aware datetimes, walking one
    calendar day at a time and counting only the actual overlap between
    [start, end) and each weekday - so a partial first day and a partial
    last day are each counted by their real elapsed hours, not as whole
    days. Not restricted to a 9-5 business-hours window within a day, since
    the SLA is stated in whole days, not hours.
    """
    if end <= start:
        return 0.0
    days = 0.0
    cursor_date = start.date()
    end_date = end.date()
    while cursor_date <= end_date:
        day_start = datetime(cursor_date.year, cursor_date.month, cursor_date.day, tzinfo=start.tzinfo)
        day_end = day_start + timedelta(days=1)
        overlap_start = max(start, day_start)
        overlap_end = min(end, day_end)
        if overlap_end > overlap_start and cursor_date.weekday() < 5:
            days += (overlap_end - overlap_start).total_seconds() / 86400
        cursor_date += timedelta(days=1)
    return days


def classify(severity: str, first_seen_at: str, now: datetime | None = None) -> dict:
    """Bucket one open finding into on_track / at_risk / breached."""
    threshold = SLA_BUSINESS_DAYS.get(severity)
    if threshold is None:
        return {"bucket": "unknown", "business_days_open": None, "threshold_days": None}

    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(first_seen_at)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    elapsed = business_days_between(start, now)
    if elapsed >= threshold:
        bucket = "breached"
    elif elapsed >= threshold * _AT_RISK_FRACTION:
        bucket = "at_risk"
    else:
        bucket = "on_track"
    return {"bucket": bucket, "business_days_open": round(elapsed, 2), "threshold_days": threshold}
