"""Use case #7: unusual login behaviour from the same IP for multiple users.

Signal: AU1 (logon successful), grouped by source IP. Flags an IP once
`user_threshold` distinct users have logged on from it within a rolling
window - a pattern consistent with a shared jump host/proxy being used to
access multiple accounts, or credential abuse from one origin.
"""
from collections import defaultdict
from datetime import datetime

from .. import config
from ._common import fetch_events

_ALWAYS_EXCLUDED_IPS = {"", "127.0.0.1", "0.0.0.0", "::1"}


def _known_server_ips(system_id) -> set:
    if not system_id:
        return set()
    try:
        return {config.sap_system_config(system_id)["ashost"]}
    except RuntimeError:
        return set()


def detect_shared_ip_multi_user(system_id=None, client=None,
                                 window_minutes: int = 10, user_threshold: int = 3,
                                 exclude_ips: set | None = None):
    rows = fetch_events(msg_codes=["AU1"], system_id=system_id, client=client)

    excluded = _ALWAYS_EXCLUDED_IPS | _known_server_ips(system_id)
    if exclude_ips:
        excluded |= set(exclude_ips)

    by_ip = defaultdict(list)
    for row in rows:
        if row["ip_address"] and row["ip_address"] not in excluded:
            by_ip[row["ip_address"]].append(row)

    findings = []
    for ip, events in by_ip.items():
        events_sorted = sorted(events, key=lambda r: r["event_timestamp"])
        window = []
        for ev in events_sorted:
            ts = datetime.fromisoformat(ev["event_timestamp"])
            window = [w for w in window
                      if (ts - datetime.fromisoformat(w["event_timestamp"])).total_seconds()
                      <= window_minutes * 60]
            window.append(ev)

            distinct_users = {w["user_id"] for w in window if w["user_id"]}
            if len(distinct_users) >= user_threshold:
                findings.append({
                    "rule": "shared_ip_multi_user",
                    "severity": "Medium",
                    "user_id": None,
                    "source_system": ev["source_system"],
                    "client": ev["client"],
                    "detected_at": ev["event_timestamp"],
                    "summary": (
                        f"{len(distinct_users)} distinct users logged on from "
                        f"{ip} within {window_minutes} minutes"
                    ),
                    "evidence": {
                        "ip_address": ip,
                        "users": sorted(distinct_users),
                        "window_minutes": window_minutes,
                    },
                })
                window = []

    return findings
