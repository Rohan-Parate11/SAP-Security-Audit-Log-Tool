"""Use case #9: potential login attack.

Signals used (confirmed against real S23 data):
  AU2 - Logon failed
  AU1 - Logon successful
  AUM - User locked after repeated failed password checks

Two findings are raised:
  - "account_locked": SAP itself already crossed its own lockout threshold.
  - "potential_login_attack": N+ failed logons for a user within a rolling
    window, followed by a successful logon.
"""
from datetime import datetime

from ._common import fetch_events, group_by_user


def detect_login_attacks(system_id=None, client=None,
                          window_minutes: int = 15, fail_threshold: int = 3):
    rows = fetch_events(msg_codes=["AU1", "AU2", "AUM"],
                         system_id=system_id, client=client)
    findings = []

    for user_id, events in group_by_user(rows).items():
        recent_fails = []
        for ev in events:
            ts = datetime.fromisoformat(ev["event_timestamp"])

            if ev["msg_code"] == "AUM":
                findings.append({
                    "rule": "account_locked",
                    "severity": "High",
                    "user_id": user_id,
                    "source_system": ev["source_system"],
                    "client": ev["client"],
                    "detected_at": ev["event_timestamp"],
                    "summary": f"{user_id} was locked after repeated failed logons",
                    "evidence": {"message": ev["message"]},
                })
                recent_fails = []
                continue

            if ev["msg_code"] == "AU2":
                recent_fails.append(ts)
                continue

            # AU1: successful logon - check the failure window behind it
            recent_fails = [t for t in recent_fails
                             if (ts - t).total_seconds() <= window_minutes * 60]
            if len(recent_fails) >= fail_threshold:
                findings.append({
                    "rule": "potential_login_attack",
                    "severity": "High",
                    "user_id": user_id,
                    "source_system": ev["source_system"],
                    "client": ev["client"],
                    "detected_at": ev["event_timestamp"],
                    "summary": (
                        f"{user_id} logged on successfully after "
                        f"{len(recent_fails)} failed attempts within "
                        f"{window_minutes} minutes"
                    ),
                    "evidence": {
                        "failed_count": len(recent_fails),
                        "window_minutes": window_minutes,
                        "first_failed_at": recent_fails[0].isoformat(),
                        "success_at": ev["event_timestamp"],
                        "terminal": ev["terminal"],
                        "ip_address": ev["ip_address"],
                    },
                })
                recent_fails = []

    return findings
