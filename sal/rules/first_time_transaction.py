"""Use cases #4 and #11: unusual transaction execution / first-time sensitive
transaction execution.

Signal: AU3 (transaction started). Both use the same "has this user run this
tcode before" mechanism; they differ in scope and learning period:

  - only_critical=False (#4, general): any tcode qualifies, but the first
    `min_history` distinct tcodes a user runs establish their baseline
    without being flagged, so day-one activity doesn't all look "new".
  - only_critical=True (#11): restricted to the critical-transaction
    catalogue, and there is no learning period - the very first time a user
    runs a sensitive tcode is itself the finding.
"""
from ..catalogues import list_critical_transactions
from ._common import fetch_events, group_by_user


def detect_first_time_transactions(system_id=None, client=None,
                                    only_critical: bool = False, min_history: int = 5):
    rows = fetch_events(msg_codes=["AU3"], system_id=system_id, client=client)

    critical = set(list_critical_transactions()) if only_critical else None
    effective_min_history = 0 if only_critical else min_history

    findings = []
    for user_id, events in group_by_user(rows).items():
        seen_tcodes = set()
        baseline_count = 0

        for ev in events:
            tcode = ev["transaction_code"]
            if not tcode:
                continue
            if critical is not None and tcode not in critical:
                continue

            if baseline_count < effective_min_history:
                seen_tcodes.add(tcode)
                baseline_count += 1
                continue

            if tcode not in seen_tcodes:
                rule = "first_time_sensitive_transaction" if only_critical else "unusual_transaction"
                findings.append({
                    "rule": rule,
                    "severity": "High" if only_critical else "Medium",
                    "user_id": user_id,
                    "source_system": ev["source_system"],
                    "client": ev["client"],
                    "detected_at": ev["event_timestamp"],
                    "summary": f"{user_id} ran {tcode} for the first time",
                    "evidence": {
                        "transaction_code": tcode,
                        "terminal": ev["terminal"],
                        "ip_address": ev["ip_address"],
                    },
                })
                seen_tcodes.add(tcode)

    return findings
