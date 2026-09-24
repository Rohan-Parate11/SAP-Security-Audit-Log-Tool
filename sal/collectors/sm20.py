"""SM20 (Security Audit Log) collector.

Pulls events via the RSAU_API_GET_LOG_DATA remote function module and stores
them into the normalized ``events`` table. RSAU_READ_LOG (the older FM of the
same name used by the classic SM20 report) was tried first during the
technical spike and reliably returned zero rows/zero file-stats over RFC even
against windows independently confirmed to contain data; RSAU_API_GET_LOG_DATA
is the one that actually works remotely and returns richer, pre-decoded
fields (message text, severity, email), so it is what SAL builds on.

Selection filters mirror what SM20/RSAU_READ_LOG's own selection screen
offers, to the extent RSAU_API_GET_LOG_DATA's interface exposes them: date/
time interval, client, user, transaction code, report, instance and message
code. It has no event-class/severity import parameters (unlike the classic
FM), so those aren't offered as server-side selection - they're still stored
per-event and filterable locally after the fact.
"""
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from ..sap_connector import SapConnection
from ..storage.db import get_connection, init_schema


def _as_list(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [v.strip() for v in value.split(",") if v.strip()]
        return parts or None
    values = [str(v).strip() for v in value if str(v).strip()]
    return values or None


def _range_option(value: str) -> list[dict]:
    return [{"SIGN": "I", "OPTION": "EQ", "LOW": value, "HIGH": ""}]


def _range_options(values: list[str]) -> list[dict]:
    return [{"SIGN": "I", "OPTION": "EQ", "LOW": v, "HIGH": ""} for v in values]


def _fmt_log_tstmp(value) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def event_timestamp(sal_date: str, sal_time: str) -> str:
    """YYYYMMDD + HHMMSS -> the "YYYY-MM-DD HH:MM:SS" shape events.event_timestamp
    is stored in. Public (not module-private) because sal/web/api.py's
    events_export() needs the exact same conversion for its date-range
    query bounds - dat_from/tim_from are the same YYYYMMDD/HHMMSS shape as
    SAP's own SAL_DATE/SAL_TIME, so this is the single source of truth for
    that format rather than a second inline copy of the slicing.
    """
    return (
        f"{sal_date[0:4]}-{sal_date[4:6]}-{sal_date[6:8]} "
        f"{sal_time[0:2]}:{sal_time[2:4]}:{sal_time[4:6]}"
    )


def normalize_row(raw: dict, run_id: str) -> dict:
    return {
        "source_system": raw["SID"],
        "client": raw["SLGMAND"],
        "instance": raw["INSTANCE"],
        "log_tstmp": _fmt_log_tstmp(raw["LOG_TSTMP"]),
        "counter": int(raw["COUNTER"]),
        "event_timestamp": event_timestamp(raw["SAL_DATE"], raw["SAL_TIME"]),
        "user_id": raw["SLGUSER"] or None,
        "user_email": raw["SMTP_ADDR"] or None,
        "msg_code": raw["MSG"] or None,
        "area": raw["AREA"] or None,
        "event_class": raw["TXSUBCLSID"] or None,
        "severity": raw["SEVERITY_S"] or None,
        "transaction_code": raw["SLGTC"] or None,
        "program": raw["SLGREPNA"] or None,
        "terminal": raw["SLGLTRM2"] or None,
        "ip_address": raw["TERM_IPV6"] or None,
        "message": raw["SAL_DATA"] or None,
        "param1": raw["PARAM1"] or None,
        "param2": raw["PARAM2"] or None,
        "param3": raw["PARAM3"] or None,
        "collection_run_id": run_id,
        "inserted_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_events(system_id: str, dat_from: str, dat_to: str,
                  tim_from: str = "000000", tim_to: str = "235959",
                  client: str | None = None, user=None, transaction_code=None,
                  report=None, instance=None, msg_code=None) -> list[dict]:
    is_interval = {
        "DAT_FROM": dat_from, "DAT_TO": dat_to,
        "TIM_FROM": tim_from, "TIM_TO": tim_to,
    }
    kwargs = {"IS_INTERVAL": is_interval}
    if client:
        kwargs["IT_R_MANDT"] = _range_option(client)

    for value, fm_param in (
        (user, "IT_R_USER"),
        (transaction_code, "IT_R_TCD"),
        (report, "IT_R_REPS"),
        (instance, "IT_R_INSTANCE"),
        (msg_code, "IT_R_MSG"),
    ):
        values = _as_list(value)
        if values:
            kwargs[fm_param] = _range_options(values)

    with SapConnection(system_id) as conn:
        result = conn.call("RSAU_API_GET_LOG_DATA", **kwargs)
    return result.get("ET_LOG", [])


def store_events(rows: list[dict], run_id: str) -> int:
    if not rows:
        return 0
    conn = get_connection()
    try:
        normalized = [normalize_row(row, run_id) for row in rows]
        columns = list(normalized[0].keys())
        placeholders = ", ".join(f":{c}" for c in columns)
        sql = (
            f"INSERT OR IGNORE INTO events ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        cur = conn.executemany(sql, normalized)
        conn.commit()
        return cur.rowcount if cur.rowcount is not None else len(normalized)
    finally:
        conn.close()


def collect_and_store(system_id: str, dat_from: str, dat_to: str,
                       tim_from: str = "000000", tim_to: str = "235959",
                       client: str | None = None, user=None, transaction_code=None,
                       report=None, instance=None, msg_code=None,
                       actor: str | None = None, job_id: int | None = None) -> dict:
    init_schema()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    filters = {
        "tim_from": tim_from, "tim_to": tim_to,
        "user": _as_list(user), "transaction_code": _as_list(transaction_code),
        "report": _as_list(report), "instance": _as_list(instance),
        "msg_code": _as_list(msg_code),
    }
    filters = {k: v for k, v in filters.items() if v}

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO collection_runs "
            "(run_id, source_system, client, dat_from, dat_to, started_at, status, filters_json, actor, job_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)",
            (run_id, system_id, client, dat_from, dat_to, started_at, json.dumps(filters), actor, job_id),
        )
        conn.commit()
    finally:
        conn.close()

    summary = {"run_id": run_id, "system_id": system_id, "client": client}
    # Catches any failure, not just SapConnectionError - a narrower catch
    # here left a real production row stuck at status='running' forever
    # when an unconfigured system raised a plain RuntimeError from config
    # lookup instead: that exception skipped this whole block, so the
    # finalizing UPDATE below never ran. Every caller (the CLI script,
    # sal/jobs.py's job runner) already only reads this function's return
    # value and never expects it to raise, so swallowing broadly here
    # doesn't change the contract - it just makes it actually hold.
    try:
        rows = fetch_events(system_id, dat_from, dat_to, tim_from, tim_to, client,
                             user=user, transaction_code=transaction_code,
                             report=report, instance=instance, msg_code=msg_code)
        inserted = store_events(rows, run_id)
        summary.update(status="success", fetched=len(rows), inserted=inserted)
        status, row_count, error_message = "success", len(rows), None
    except Exception as exc:
        summary.update(status="error", error=str(exc))
        status, row_count, error_message = "error", None, str(exc)
    finally:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE collection_runs "
                "SET finished_at = ?, status = ?, row_count = ?, error_message = ? "
                "WHERE run_id = ?",
                (datetime.now(timezone.utc).isoformat(), status, row_count,
                 error_message, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    return summary
