"""Use case #1: unusual login time.

Signal: AU1 (logon successful). Each user's login hour-of-day (decimal, e.g.
14.5 = 14:30) is tracked with a running mean/stdev. Once a user has at least
`min_observations` prior logins, a login more than `deviation_threshold`
standard deviations from their own running mean - earlier or later - is
flagged. Hour-of-day is treated linearly (0-24); a user who genuinely and
routinely straddles midnight could see false positives near the boundary -
acceptable for a first cut, worth revisiting if it proves noisy.

Two guards keep this from flooding on real data:
  - Logons within `dedup_minutes` of the previous one for the same user
    (e.g. several parallel RFC/dialog sessions opened in the same burst)
    count as one observation, not several independent samples.
  - `min_stdev_hours` floors the denominator, so a baseline with near-zero
    variance (a handful of logons seconds apart) can't turn a small,
    unremarkable shift into an absurd standard-deviation multiple.
"""
from datetime import datetime

from ._common import fetch_events, group_by_user
from ._stats import OnlineStats


def detect_unusual_login_time(system_id=None, client=None,
                               min_observations: int = 5, deviation_threshold: float = 2.5,
                               dedup_minutes: float = 5, min_stdev_hours: float = 0.5):
    rows = fetch_events(msg_codes=["AU1"], system_id=system_id, client=client)
    findings = []

    for user_id, events in group_by_user(rows).items():
        stats = OnlineStats()
        last_ts = None
        for ev in events:
            ts = datetime.fromisoformat(ev["event_timestamp"])
            if last_ts is not None and (ts - last_ts).total_seconds() < dedup_minutes * 60:
                continue
            last_ts = ts
            hour = ts.hour + ts.minute / 60 + ts.second / 3600

            effective_stdev = max(stats.stdev, min_stdev_hours)
            if stats.n >= min_observations:
                deviation = abs(hour - stats.mean) / effective_stdev
                if deviation >= deviation_threshold:
                    baseline_h, baseline_m = divmod(round(stats.mean * 60), 60)
                    findings.append({
                        "rule": "unusual_login_time",
                        "severity": "Medium",
                        "user_id": user_id,
                        "source_system": ev["source_system"],
                        "client": ev["client"],
                        "detected_at": ev["event_timestamp"],
                        "summary": (
                            f"{user_id} logged on at {ts.strftime('%H:%M')}, "
                            f"{deviation:.1f} std devs from their usual "
                            f"~{baseline_h:02d}:{baseline_m:02d}"
                        ),
                        "evidence": {
                            "login_hour": round(hour, 2),
                            "baseline_mean_hour": round(stats.mean, 2),
                            "baseline_stdev_hours": round(stats.stdev, 2),
                            "baseline_observations": stats.n,
                        },
                    })
            stats.update(hour)

    return findings
