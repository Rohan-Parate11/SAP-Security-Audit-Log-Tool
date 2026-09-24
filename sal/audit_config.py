"""SM19 audit-configuration visibility (Blueprint v2, Phase D).

check_audit_config() is a direct, synchronous RFC call with an explicit
timeout - deliberately NOT routed through sal/jobs.py's chunked job model.
Decided by a dev-team + council review during planning (see Docs/CHANGELOG.md):
jobs.py's machinery solves day-range chunking/resumability, which a
single, dateless config read has no use for. try/except/finally discipline
mirrors sal/collectors/sm20.py's collect_and_store() - a snapshot row is
finalized on the success, timeout, and generic-exception paths; a
persistence-layer failure (e.g. a locked database) is not caught here,
matching the same pre-existing gap in collect_and_store().

Timeout: pyrfc has no per-call timeout kwarg, and this runs on Windows
(no signal.alarm), so each call runs on its own daemon thread and the
caller bounds its *wait* via a concurrent.futures.Future's result(timeout=).
Deliberately not a shared ThreadPoolExecutor: that pattern's worker
threads are non-daemon and get joined by an atexit hook, so one genuinely
wedged RFC call (dead TCP session, black-holed packets - precisely the
scenario the timeout exists for) would hang a clean process shutdown
indefinitely, and a fixed-size pool could be starved by repeat checks
against the same stuck system. A one-thread-per-call, daemon=True design
avoids both: process exit is never blocked, and an in-flight guard below
(keyed per system_id/client) caps concurrent duplicate checks at one
in-flight thread per target regardless of how many times "Check" is
clicked. Note this bounds how long the *caller* waits, not a true cancel -
Python cannot forcibly kill a blocked native call - so an abandoned call's
thread keeps running in the background; its eventual outcome is logged
(not silently discarded) via the done-callback in _run_with_timeout().

FM: RSAU_API_GET_AUDIT_CONFIG, callable with no input parameters -
validated against a live system (S23) during Phase D planning. Returns the
CURRENT dynamic profile ($DYN$ slot(s)), i.e. actually-active configuration,
not a saved-but-inactive one.
"""
import concurrent.futures
import json
import logging
import threading
import time
from datetime import datetime, timezone

from .rules._coverage import RULE_COVERAGE
from .sap_connector import SapConnection
from .storage.db import get_connection, init_schema

logger = logging.getLogger(__name__)

_RFC_TIMEOUT_SECONDS = 30

_CLASS_FIELDS = [
    "CLASS_LOGIN", "CLASS_RFC_LOGIN", "CLASS_TCD", "CLASS_REP",
    "CLASS_USER", "CLASS_SYST", "CLASS_RFC", "CLASS_OTHER",
]

# Top-level scalar fields worth keeping for diagnostics - deliberately an
# allowlist, not the whole RFC response: ET_SLOT_INFO is already fully
# captured (more cleanly) in parsed_slots_json, and blindly persisting an
# entire upstream payload is exactly the "unfiltered capture" pattern this
# project has been burned by once already (see Docs/CHANGELOG.md).
_RAW_CONFIG_ALLOWLIST = [
    "ED_ENABLE", "ED_VERSION", "ED_DATE", "ED_CURFILENUM", "ED_CURFILESIZE",
    "ED_MAXFILESIZE", "ED_POSITION", "ED_SIZEOFFILE", "ED_SLOTCNT",
    "ED_FILESTATUS", "ED_USER_SELECTION", "ED_EXCP_TEXT",
]

_inflight_lock = threading.Lock()
_inflight: set[tuple[str, str | None]] = set()


def _fetch_raw_config(system_id: str) -> dict:
    with SapConnection(system_id) as conn:
        return conn.call("RSAU_API_GET_AUDIT_CONFIG")


def _allowlisted_raw(raw: dict | None) -> dict | None:
    if raw is None:
        return None
    return {k: raw.get(k) for k in _RAW_CONFIG_ALLOWLIST if k in raw}


def _parse_slots(et_slot_info: list[dict] | None) -> list[dict]:
    parsed = []
    for slot in et_slot_info or []:
        active_classes = [c for c in _CLASS_FIELDS if slot.get(c) == "X"]
        parsed.append({
            "profile": slot.get("PROFNAME"),
            "status": slot.get("STATUS"),
            "active_classes": active_classes,
            "severity_low": slot.get("SEVERITY_LOW") == "X",
            "severity_med": slot.get("SEVERITY_MED") == "X",
            "severity_hgh": slot.get("SEVERITY_HGH") == "X",
            "client_filter": slot.get("MANDT"),
            "user_filter": slot.get("UNAME"),
        })
    return parsed


def _run_with_timeout(system_id: str, client: str | None, timeout: float) -> dict:
    """Run _fetch_raw_config on its own daemon thread; bound only the
    caller's wait. The done-callback fires whenever the thread actually
    finishes - if that's after `timeout` has already elapsed, the result
    would otherwise be silently discarded, so it's logged instead, and
    this is also where the in-flight guard for this (system_id, client) is
    released - deliberately not released when the caller merely times out,
    so a second check can't pile another thread onto an already-wedged
    system.
    """
    key = (system_id, client)
    future: concurrent.futures.Future = concurrent.futures.Future()
    started_at = time.monotonic()

    def _target():
        try:
            future.set_result(_fetch_raw_config(system_id))
        except Exception as exc:  # noqa: BLE001 - captured via the future, not swallowed
            future.set_exception(exc)

    threading.Thread(target=_target, daemon=True, name=f"sal-audit-config-{system_id}").start()

    def _on_done(fut: concurrent.futures.Future) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed > timeout:
            exc = fut.exception()
            if exc is not None:
                logger.warning(
                    "audit_config check for %s finished %.1fs after its %.0fs "
                    "timeout, with error: %s", system_id, elapsed, timeout, exc,
                )
            else:
                logger.info(
                    "audit_config check for %s finished %.1fs after its %.0fs "
                    "timeout - result discarded, caller already gave up",
                    system_id, elapsed, timeout,
                )
        with _inflight_lock:
            _inflight.discard(key)

    future.add_done_callback(_on_done)
    return future.result(timeout=timeout)


def check_audit_config(system_id: str, client: str | None = None,
                        actor: str = "unknown") -> dict:
    """Read the live, active SM19 configuration for one system. Reports
    every RFC-level failure (connection error, timeout) as a result dict
    with status='error' rather than raising - a persistence-layer failure
    is not caught, matching the pre-existing behavior of
    collect_and_store(). Only one check per (system_id, client) runs at a
    time; a duplicate request while one is already in flight is rejected
    immediately rather than queuing another thread onto a possibly-wedged
    target.
    """
    key = (system_id, client)
    with _inflight_lock:
        if key in _inflight:
            return {
                "status": "error", "enabled": None, "slots": [],
                "error": "A check for this system is already in progress - try again shortly",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        _inflight.add(key)

    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    status = "error"
    raw = None
    enabled = None
    parsed_slots: list[dict] = []
    error_message = None

    try:
        raw = _run_with_timeout(system_id, client, _RFC_TIMEOUT_SECONDS)
        enabled = raw.get("ED_ENABLE") == "X"
        parsed_slots = _parse_slots(raw.get("ET_SLOT_INFO"))
        status = "success"
    except concurrent.futures.TimeoutError:
        error_message = f"Timed out after {_RFC_TIMEOUT_SECONDS}s waiting for SAP"
        # Deliberately do NOT discard the in-flight entry here - _on_done
        # (fired when the background thread actually finishes) owns that,
        # so a second check can't pile another thread onto this target
        # while the first one is still genuinely running.
    except Exception as exc:  # noqa: BLE001 - any RFC-level failure must still finalize a row
        error_message = str(exc)
        with _inflight_lock:
            _inflight.discard(key)
    finally:
        conn_db = get_connection()
        try:
            raw_summary = _allowlisted_raw(raw)
            conn_db.execute(
                "INSERT INTO audit_config_snapshots "
                "(system_id, client, captured_at, status, enabled, "
                " raw_config_json, parsed_slots_json, error_message, actor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (system_id, client, now, status, enabled,
                 json.dumps(raw_summary, default=str) if raw_summary is not None else None,
                 json.dumps(parsed_slots), error_message, actor),
            )
            conn_db.commit()
        finally:
            conn_db.close()

    return {
        "status": status, "enabled": enabled, "slots": parsed_slots,
        "error": error_message, "captured_at": now,
    }


def latest_snapshot(system_id: str, client: str | None = None) -> dict | None:
    init_schema()
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?"], [system_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        row = conn.execute(
            f"SELECT * FROM audit_config_snapshots WHERE {' AND '.join(clauses)} "
            "ORDER BY captured_at DESC LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    result = dict(row)
    result["parsed_slots"] = json.loads(result.pop("parsed_slots_json") or "[]")
    result.pop("raw_config_json", None)
    # SQLite has no native bool type - normalize so every API response
    # describes `enabled` the same way (a genuine bool or None), not an
    # int here vs. a bool in check_audit_config()'s own return value.
    result["enabled"] = bool(result["enabled"]) if result["enabled"] is not None else None
    return result


def coverage_gaps(system_id: str, client: str | None = None) -> list[dict]:
    """Cross-reference RULE_COVERAGE against the latest snapshot's active
    classes. A rule is reported as a gap if its required class(es) aren't
    all covered, OR if there is no successful snapshot yet - unverified
    coverage is reported explicitly, never silently assumed fine.
    """
    snapshot = latest_snapshot(system_id, client)
    have_snapshot = snapshot is not None and snapshot["status"] == "success"
    active_classes = set()
    if have_snapshot:
        for slot in snapshot["parsed_slots"]:
            active_classes.update(slot["active_classes"])

    gaps = []
    for rule_key, entry in RULE_COVERAGE.items():
        required = set(entry["classes"])
        missing = required - active_classes if have_snapshot else required
        if missing or not have_snapshot:
            gaps.append({
                "rule_key": rule_key,
                "required_classes": sorted(required),
                "missing_classes": sorted(missing),
                "source": entry["source"],
                "confidence": entry["confidence"],
                "unverified": not have_snapshot,
            })
    return gaps
