"""Export helpers for findings and collection results (Blueprint v2, Phase C).

No new data model - these serialize what findings_svc.list_findings() and
the collection_runs table already produce into CSV text / XLSX bytes, for
the "download this for the client" step every consultant workflow in the
original use-case sheet asked for.
"""
import csv
import io
import json

from openpyxl import Workbook

_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell_value(value):
    """Defang CSV/Excel formula injection (CWE-1236): a string cell value
    starting with =, +, -, @, tab, or CR is treated as a live formula by
    Excel/LibreOffice/Sheets on open, not literal text. Several columns in
    both this module's exports and sal/itgc_report.py's ITGC workbook carry
    user-controlled free text with no character restriction (actor display
    names set via POST /api/identity, disposition reason_code/notes) or
    text sourced from live SAP event data - and the ITGC workbook in
    particular is built to be handed to the client's external audit team,
    raising the stakes of a live formula reaching an opened cell there.
    Found by security-reviewer during the ITGC report's review pass.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def sanitize_row(values: list) -> list:
    """sanitize_cell_value applied across a row - the common case for
    building a styled workbook one appended row at a time (see
    sal/itgc_report.py and sal/rules_catalog.py).
    """
    return [sanitize_cell_value(v) for v in values]


FINDINGS_HEADERS = [
    "finding_key", "rule_key", "rule_label", "severity", "source_system",
    "client", "user_id", "detected_at", "summary", "status", "disposed_by",
    "disposed_at", "reason_code", "analyst_notes", "first_seen_at",
    "last_seen_at", "evidence",
]

COLLECTION_RUNS_HEADERS = [
    "run_id", "source_system", "client", "dat_from", "dat_to", "started_at",
    "finished_at", "status", "row_count", "error_message", "actor", "filters_json",
]

# Every column on the `events` table (sal/storage/db.py), reordered for a
# reader rather than the table's own definition order - event_timestamp
# first since that's what an analyst sorts/scans by, bookkeeping columns
# (log_tstmp/counter/collection_run_id/inserted_at) last.
EVENTS_HEADERS = [
    "event_timestamp", "source_system", "client", "user_id", "user_email",
    "transaction_code", "msg_code", "area", "event_class", "severity",
    "program", "terminal", "ip_address", "message", "param1", "param2", "param3",
    "instance", "log_tstmp", "counter", "collection_run_id", "inserted_at",
]


def flatten_finding(finding: dict) -> dict:
    """Findings carry evidence as a dict - flatten it to a JSON string so it
    fits in a single spreadsheet cell rather than erroring or being dropped.
    """
    row = dict(finding)
    row["evidence"] = json.dumps(row.get("evidence") or {}, default=str)
    return row


def rows_to_csv(headers: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: sanitize_cell_value(v) for k, v in row.items()})
    return buf.getvalue()


def rows_to_xlsx(headers: list[str], rows: list[dict], sheet_title: str = "Sheet1") -> bytes:
    """write_only=True streams each appended row straight through instead of
    keeping a full in-memory Cell object per value - this export carries no
    per-cell styling (see sal/xlsx_style.py for the formatted reports that
    do), so there's nothing write_only's leaner API can't do, and it keeps
    memory flat rather than growing with row count. events.py's raw dump can
    run into the hundreds of thousands of rows for a wide date range against
    this app's real data volumes.
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=sheet_title)
    ws.append(headers)
    for row in rows:
        ws.append([sanitize_cell_value(row.get(h, "")) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
