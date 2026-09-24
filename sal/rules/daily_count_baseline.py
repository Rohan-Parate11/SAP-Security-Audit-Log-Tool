"""Shared per-day-count baseline engine for use cases #2 (unusual login
frequency) and #5 (unusual activity volume) - both are "count of X per user
per day, compared to that user's own running daily average," differing only
in which events get counted. Both are one-sided: only a spike *above* normal
is a finding, since unusually low activity isn't the security concern here.
"""
from collections import defaultdict

from ._common import fetch_events, group_by_user
from ._stats import OnlineStats


def _daily_counts(events) -> dict:
    counts = defaultdict(int)
    for ev in events:
        day = ev["event_timestamp"][:10]
        counts[day] += 1
    return dict(sorted(counts.items()))


def detect_daily_count_anomaly(rule_name: str, msg_codes=None, event_class=None,
                                system_id=None, client=None,
                                min_observations: int = 3, deviation_threshold: float = 2.0,
                                severity: str = "Medium"):
    rows = fetch_events(msg_codes=msg_codes, event_class=event_class,
                         system_id=system_id, client=client)
    findings = []

    for user_id, events in group_by_user(rows).items():
        daily = _daily_counts(events)
        stats = OnlineStats()
        for day, count in daily.items():
            if stats.n >= min_observations and stats.stdev > 0:
                deviation = (count - stats.mean) / stats.stdev
                if deviation >= deviation_threshold:
                    findings.append({
                        "rule": rule_name,
                        "severity": severity,
                        "user_id": user_id,
                        "source_system": events[0]["source_system"],
                        "client": events[0]["client"],
                        "detected_at": day,
                        "summary": (
                            f"{user_id} had {count} events on {day}, vs their "
                            f"usual ~{stats.mean:.0f}/day ({deviation:.1f} std "
                            f"devs above normal)"
                        ),
                        "evidence": {
                            "day": day,
                            "count": count,
                            "baseline_mean": round(stats.mean, 1),
                            "baseline_stdev": round(stats.stdev, 1),
                            "baseline_observations": stats.n,
                        },
                    })
            stats.update(count)

    return findings


def detect_unusual_login_frequency(system_id=None, client=None, **kwargs):
    return detect_daily_count_anomaly(
        "unusual_login_frequency", msg_codes=["AU1"],
        system_id=system_id, client=client, **kwargs,
    )


def detect_unusual_activity_volume(system_id=None, client=None, **kwargs):
    return detect_daily_count_anomaly(
        "unusual_activity_volume", msg_codes=["AU3"],
        system_id=system_id, client=client, **kwargs,
    )
