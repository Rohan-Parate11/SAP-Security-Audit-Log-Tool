"""Analyst-friendly explanations for common SAP RFC/collection failures.

sal/jobs.py and sal/collectors/sm20.py store the raw exception text
verbatim (see SapConnection.call()'s f-string in sal/sap_connector/
connection.py: "RFC call '<FM>' failed on system '<ID>': <pyrfc error>")
as collection_jobs.error_message / collection_runs.error_message - exactly
what an engineer needs to diagnose the failure, but not something a
security analyst should be expected to parse. This module maps a small,
curated set of KNOWN, well-documented SAP NW RFC SDK error keys (the
"key=<KEY>" pyrfc embeds in its own error text) to a short plain-language
explanation and a suggested next step - additive only, alongside the raw
message, never replacing it.

Deliberately conservative, per this project's own standing rule against
guessing unvalidated SAP internals (see CLAUDE.md): an error key not in
FRIENDLY_ERRORS below returns None rather than fabricating an explanation
for an error this project hasn't actually grounded in something concrete.
TSV_TNEW_PAGE_ALLOC_FAILED was added after a live UAT tester hit it
verbatim; the other three are the NW RFC SDK's own standard, stable,
protocol-level connection error classes (not guessed business-function
semantics), not a specific business RFC's behavior.
"""
import re

_KEY_RE = re.compile(r"key=([A-Z0-9_]+)")

# error key -> (analyst-facing explanation, suggested action)
FRIENDLY_ERRORS: dict[str, tuple[str, str]] = {
    "TSV_TNEW_PAGE_ALLOC_FAILED": (
        "The SAP system ran out of memory while building the results for this "
        "request - usually because the date range (or other filters) asked for "
        "more data than SAP could hold in memory at once.",
        "Resubmit with a narrower date range, or add a user/transaction-code "
        "filter to reduce how much data SAP has to return in a single request.",
    ),
    "COMMUNICATION_FAILURE": (
        "SAL lost its network connection to the SAP system partway through this "
        "request.",
        "This is usually temporary. Wait a moment and resubmit; if it keeps "
        "happening, check with whoever manages connectivity to this SAP system.",
    ),
    "LOGON_FAILURE": (
        "SAP rejected the logon for this request's technical user (for example, "
        "an incorrect password, or the user being locked/expired on the SAP side).",
        "This isn't something to retry as-is - contact your SAL administrator, "
        "since the system's stored credentials may need to be corrected.",
    ),
    "TIME_OUT": (
        "The request took longer than SAP allows and was cut off before it "
        "could finish.",
        "Resubmit with a narrower date range so SAP has less to process in a "
        "single request.",
    ),
}


def friendly_error(raw_message: str | None) -> dict[str, str] | None:
    """Return {"explanation": ..., "suggestion": ...} for a known SAP error
    key embedded in `raw_message`, or None if `raw_message` is empty or
    doesn't match anything in FRIENDLY_ERRORS. Never raises - a malformed
    or unrecognized message simply yields no friendly explanation, not an
    error.
    """
    if not raw_message:
        return None
    match = _KEY_RE.search(raw_message)
    if not match:
        return None
    entry = FRIENDLY_ERRORS.get(match.group(1))
    if entry is None:
        return None
    explanation, suggestion = entry
    return {"explanation": explanation, "suggestion": suggestion}
