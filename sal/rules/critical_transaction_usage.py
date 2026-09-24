"""Critical transaction usage - tracked unconditionally, every time.

Signal: AU3 (transaction started), restricted to the critical-transaction
catalogue (same scoping sal/catalogues.py already provides to use cases
#11 and #14). Requested directly: "I want that all the critical
transactions be always be marked as finding even if they are a part of
user's role or profile assignment" - a deliberate, comprehensive audit
trail of privileged-transaction usage, not an anomaly detector.

This is NOT a replacement for either existing critical-transaction rule -
it is additive, and deliberately does none of what they do:

  - sal/rules/first_time_transaction.py's first_time_sensitive_transaction
    fires exactly once per (user, tcode) - the very first occurrence ever
    seen, never again after that.
  - sal/rules/out_of_context_transaction.py's out_of_context_transaction/
    out_of_context_no_role_data fire only when the user's CURRENT SAP
    roles (or a directly-assigned profile) do not cover the tcode - a
    properly-authorized run never flags there, by design.

Both of those answer "is this worth a second look" and intentionally go
quiet once an explanation exists (a role now covers it; it's already been
seen once). This rule answers a different question entirely - "did a
critical transaction run, by anyone, authorized or not" - and never goes
quiet, on purpose: every run is its own finding, indefinitely, at High
severity (an explicit choice, not a default - see the corresponding
AskUserQuestion in Docs/CHANGELOG.md's entry for this feature). A system
whose critical-transaction catalogue sees frequent, fully-authorized
admin activity will accumulate a High-severity finding per run - that
volume is the intended behavior, not a bug; use the whitelist (scoped to
a specific user, or left open to any user) if a known, accepted pattern
should stop generating new open findings.

Like every other rule, sync_findings() re-evaluates all currently-
retained events on every run, not just new ones - the first sync after
this rule ships will retroactively create a finding for every
critical-transaction event already in the database, exactly the way
out_of_context_transaction's own retroactive re-flagging already works.
"""
from ..catalogues import list_critical_transactions
from ._common import fetch_events


def detect_critical_transaction_usage(system_id=None, client=None):
    critical = set(list_critical_transactions())
    if not critical:
        return []

    rows = fetch_events(msg_codes=["AU3"], system_id=system_id, client=client)
    findings = []
    for ev in rows:
        tcode = ev["transaction_code"]
        user_id = ev["user_id"]
        if not tcode or tcode not in critical or not user_id:
            continue

        findings.append({
            "rule": "critical_transaction_usage",
            "severity": "High",
            "user_id": user_id,
            "source_system": ev["source_system"],
            "client": ev["client"],
            "detected_at": ev["event_timestamp"],
            "summary": f"{user_id} ran critical transaction {tcode}",
            "evidence": {
                "transaction_code": tcode,
                "terminal": ev["terminal"],
                "ip_address": ev["ip_address"],
            },
        })

    return findings
