"""Use case #8: unusual export of data.

Signals confirmed against real S23 data:
  DU9 - Generic table access call to <table> with activity <NN> (auth check)
        PARAM1 = table name, PARAM2 = activity code (01 create, 02 change,
        03 display, 06 delete), PARAM3 = auth check result.
  AUY - Download <bytes> Bytes to File <path>
        PARAM1 = byte count, PARAM3 = destination file path.

Two findings are raised:
  - "sensitive_table_access": a DU9 hit on a table in the sensitive-tables
    catalogue, on its own (worth visibility regardless of what happens next).
    Change/delete activity is High; a plain display is Low - viewing a
    sensitive table on its own is the least urgent of the outcomes this
    module reports, worth a record but not competing for attention with a
    real change/delete or an actual export (requested directly, 2026-09-15:
    "have we configured any findings under low category?" - none had ever
    been assigned Low before this).
  - "sensitive_data_export": an AUY download preceded by a sensitive table
    access from the same user within `correlation_minutes` - the strongest
    match to "logged in, exported data from a sensitive table, logged off,"
    kept at High. A download with no such correlated access is still
    reported ("data_export"), now at Low rather than Medium - any export is
    still worth a record even without a specific table tied to it, but an
    uncorrelated download is a much weaker signal than one that actually
    matches sensitive-table access moments before.
"""
from datetime import datetime

from ..catalogues import list_sensitive_tables
from ._common import fetch_events, group_by_user

_CHANGE_OR_DELETE_ACTIVITIES = {"02", "06"}


def detect_sensitive_table_access(system_id=None, client=None):
    sensitive = set(list_sensitive_tables())
    if not sensitive:
        return []

    rows = fetch_events(msg_codes=["DU9"], system_id=system_id, client=client)
    findings = []
    for ev in rows:
        table = ev["param1"]
        if not table or table not in sensitive:
            continue
        activity = ev["param2"]
        severity = "High" if activity in _CHANGE_OR_DELETE_ACTIVITIES else "Low"
        findings.append({
            "rule": "sensitive_table_access",
            "severity": severity,
            "user_id": ev["user_id"],
            "source_system": ev["source_system"],
            "client": ev["client"],
            "detected_at": ev["event_timestamp"],
            "summary": f"{ev['user_id']} accessed sensitive table {table} (activity {activity})",
            "evidence": {
                "table": table,
                "activity": activity,
                "auth_check": ev["param3"],
                "transaction_code": ev["transaction_code"],
            },
        })
    return findings


def detect_data_exports(system_id=None, client=None, correlation_minutes: int = 15):
    sensitive = set(list_sensitive_tables())
    du9_rows = fetch_events(msg_codes=["DU9"], system_id=system_id, client=client)
    auy_rows = fetch_events(msg_codes=["AUY"], system_id=system_id, client=client)

    sensitive_access_by_user = group_by_user(
        [r for r in du9_rows if r["param1"] in sensitive]
    )

    findings = []
    for ev in auy_rows:
        user_id = ev["user_id"]
        export_ts = datetime.fromisoformat(ev["event_timestamp"])

        matched_table = None
        for access in sensitive_access_by_user.get(user_id, []):
            access_ts = datetime.fromisoformat(access["event_timestamp"])
            delta = (export_ts - access_ts).total_seconds()
            if 0 <= delta <= correlation_minutes * 60:
                matched_table = access["param1"]
                break

        findings.append({
            "rule": "sensitive_data_export" if matched_table else "data_export",
            "severity": "High" if matched_table else "Low",
            "user_id": user_id,
            "source_system": ev["source_system"],
            "client": ev["client"],
            "detected_at": ev["event_timestamp"],
            "summary": (
                f"{user_id} downloaded data"
                + (f" recently accessed from sensitive table {matched_table}" if matched_table else "")
            ),
            "evidence": {
                "bytes": ev["param1"],
                "destination": ev["param3"],
                "transaction_code": ev["transaction_code"],
                "correlated_table": matched_table,
            },
        })

    return findings
