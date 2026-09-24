"""Regression tests for sal/sla.py (business-day SLA classification)."""
from datetime import datetime, timezone

import sal.sla as sla


def test_business_days_between_same_weekday_pair():
    start = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)  # Monday
    end = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)  # Tuesday
    assert sla.business_days_between(start, end) == 1.0


def test_business_days_between_skips_weekend():
    friday = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    # Fri->Sat->Sun->Mon: only Friday itself counts as a business day elapsed,
    # weekend doesn't add, Monday's partial-day fraction (0 hours in) adds ~0.
    assert 0.9 <= sla.business_days_between(friday, monday) <= 1.1


def test_business_days_between_end_before_start_is_zero():
    a = datetime(2026, 9, 7, tzinfo=timezone.utc)
    b = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert sla.business_days_between(a, b) == 0.0


def test_classify_on_track_when_well_within_threshold():
    now = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)  # Tuesday
    first_seen = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc).isoformat()
    result = sla.classify("Low", first_seen, now=now)  # threshold 7 days
    assert result["bucket"] == "on_track"


def test_classify_breached_past_threshold():
    now = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)  # Wednesday
    first_seen = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).isoformat()  # Monday
    result = sla.classify("High", first_seen, now=now)  # threshold 1 day
    assert result["bucket"] == "breached"
    assert result["business_days_open"] > 1.0


def test_classify_at_risk_between_75_percent_and_threshold():
    # High threshold = 1.0 business day. Mon 09:00 -> Tue 05:00 = 15h (Mon) +
    # 5h (Tue) = 20h/24h = 0.833 business days elapsed - between 0.75 and 1.0.
    now = datetime(2026, 9, 8, 5, 0, tzinfo=timezone.utc)  # Tuesday, early morning
    first_seen = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).isoformat()  # Monday
    result = sla.classify("High", first_seen, now=now)
    assert result["bucket"] == "at_risk"


def test_classify_unknown_severity():
    result = sla.classify("Critical", datetime.now(timezone.utc).isoformat())
    assert result["bucket"] == "unknown"
