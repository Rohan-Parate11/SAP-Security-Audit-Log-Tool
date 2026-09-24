"""Use case #12: mass user updates.

Signal: SM20's own "User master changes" class (confirmed codes seen in real
data: AUD record changed, AU7 user created, AUB authorizations changed, AUA
user unlocked, BU2 password changed). v1 counts overall volume of this class
rather than distinct target users, since the target username only appears in
free-text message content, not a dedicated column; that refinement can follow
once PARAM1's exact semantics are confirmed for each of these codes.

Events are merged into a single incident whenever consecutive events are less
than `gap_minutes` apart, and one finding is raised per incident that reaches
`count_threshold` - rather than re-firing on every event of a sustained
burst, which just floods the same incident as dozens of near-duplicate
findings.
"""
from datetime import datetime

from ._common import fetch_events


def detect_mass_user_changes(system_id=None, client=None,
                              gap_minutes: int = 15, count_threshold: int = 5):
    rows = fetch_events(event_class="User master changes",
                         system_id=system_id, client=client)
    if not rows:
        return []

    rows = sorted(rows, key=lambda r: r["event_timestamp"])
    findings = []
    incident: list = []
    last_ts = None

    def flush():
        if len(incident) >= count_threshold:
            findings.append({
                "rule": "mass_user_changes",
                "severity": "Medium",
                "user_id": None,
                "source_system": incident[-1]["source_system"],
                "client": incident[-1]["client"],
                "detected_at": incident[0]["event_timestamp"],
                "summary": (
                    f"{len(incident)} user-master-change events between "
                    f"{incident[0]['event_timestamp']} and {incident[-1]['event_timestamp']}"
                ),
                "evidence": {
                    "count": len(incident),
                    "started_at": incident[0]["event_timestamp"],
                    "ended_at": incident[-1]["event_timestamp"],
                    "actors": sorted({e["user_id"] for e in incident if e["user_id"]}),
                    "msg_codes": sorted({e["msg_code"] for e in incident if e["msg_code"]}),
                },
            })

    for ev in rows:
        ts = datetime.fromisoformat(ev["event_timestamp"])
        if last_ts is not None and (ts - last_ts).total_seconds() > gap_minutes * 60:
            flush()
            incident = []
        incident.append(ev)
        last_ts = ts
    flush()

    return findings
