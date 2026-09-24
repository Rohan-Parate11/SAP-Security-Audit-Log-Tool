"""Use case #3: unusual source terminal/IP.

Signal: AU1 (logon successful). For each user, the first `min_history` logons
with an IP address establish their known-source baseline; any later logon
from an IP not yet seen for that user is flagged. Blank IPs (background/batch
logons with no terminal) are ignored.
"""
from ._common import fetch_events, group_by_user


def detect_new_sources(system_id=None, client=None, min_history: int = 3):
    rows = fetch_events(msg_codes=["AU1"], system_id=system_id, client=client)
    findings = []

    for user_id, events in group_by_user(rows).items():
        seen_ips = set()
        baseline_count = 0

        for ev in events:
            ip = ev["ip_address"]
            if not ip:
                continue

            if baseline_count < min_history:
                seen_ips.add(ip)
                baseline_count += 1
                continue

            if ip not in seen_ips:
                findings.append({
                    "rule": "new_source_ip",
                    "severity": "Medium",
                    "user_id": user_id,
                    "source_system": ev["source_system"],
                    "client": ev["client"],
                    "detected_at": ev["event_timestamp"],
                    "summary": f"{user_id} logged on from a new IP address: {ip}",
                    "evidence": {
                        "ip_address": ip,
                        "terminal": ev["terminal"],
                        "known_ip_count": len(seen_ips),
                    },
                })
                seen_ips.add(ip)

    return findings
