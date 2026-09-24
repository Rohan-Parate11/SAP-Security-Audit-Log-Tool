"""PFCG role/authorization context ingestion (Blueprint v2, Phase F).

Reads two SAP tables live over RFC via RFC_READ_TABLE - validated against
S23 during Phase F planning (see Docs/Memory.md items 4-7 and
scripts/probes/probe_agr_tables.py):

  AGR_USERS  - role <-> user assignment (UNAME, AGR_NAME, FROM_DAT, TO_DAT)
  AGR_TCODES - role -> authorized transaction code, i.e. the role's PFCG
               "menu" (AGR_NAME, TCODE)

Deliberately a direct call, not a sal/jobs.py job - a bulk table read has
none of the day-range-chunking/resumability problems that machinery
solves (same reasoning as audit_config.py/retention.py). Timeout and
in-flight-guard mechanics deliberately mirror sal/audit_config.py's
_run_with_timeout()/_inflight exactly, for the same reason: pyrfc has no
per-call timeout, and this runs on Windows (no signal.alarm), so each call
runs on its own daemon thread and the caller bounds its *wait* via a
concurrent.futures.Future's result(timeout=). The timeout here (see
_RFC_TIMEOUT_SECONDS) is far longer than audit_config.py's 30s single-call
bound, because this fetch is many sequential paginated RFC_READ_TABLE
calls, not one - confirmed against real data (S23: ~20k AGR_USERS rows,
~171k AGR_TCODES rows, taking well under a minute end to end, but the
bound is set generously above that observed figure).

Storage model: raw AGR_USERS rows are kept as-is, with their own
FROM_DAT/TO_DAT validity window, rather than collapsed into a
"current-only" table - this lets authorized_tcodes_for_user() ask "was
this valid as of date X" as a plain query filter instead of needing a
separate snapshot-history table. IMPORTANT LIMITATION, not solved here:
this does NOT give true point-in-time historical reconstruction. When SAP
removes a role from a user, the AGR_USERS row is deleted outright, not
soft-expired - TO_DAT represents a *scheduled future* removal, not a
historical revocation log. So this module can answer "is/was this valid
per any validity window we've ever captured," and in particular "is this
authorized right now," but it cannot answer "was this authorized on some
past date if the role has since been fully removed." True historical
reconstruction would require ingesting SU01/PFCG change documents, which
is out of scope for Phase F.

That said, this is exactly what makes the tool able to answer the
audit scenario it was built for: a user who ran a critical transaction
weeks ago and no longer holds any role granting it today will show up as
"ran it, not currently authorized" the next time findings are
re-evaluated after a role-context refresh - sync_findings() re-scans all
retained events on every run, not just new ones, so an old event that
was fine when it happened becomes newly flagged the moment the user's
current access no longer covers it. See sal/rules/out_of_context_transaction.py.

Refresh model: every field is fetched into memory FIRST (with pagination
- RFC_READ_TABLE cannot be relied on to return an entire table in one
call, and each raw "WA" row is validated to have the exact expected field
count before being kept - a short/malformed row is logged and skipped,
never silently field-shifted into the wrong columns), and the local
tables are only touched, in one transaction (delete this system/client's
rows, insert the freshly-fetched ones, commit), after the fetch has fully
succeeded. A failed live fetch never touches the database - the previous
refresh's data stays intact. The write phase is its own try/except,
separate from the fetch's - a failure there (a locked database, a
still-malformed row that slipped through) can never skip logging the
attempt; every attempt, success, truncated, or failed, is logged to
role_context_refresh_runs.

Runs on its own daily APScheduler job per registered system (see
sal/jobs.py's register_role_context_job()) and can also be triggered on
demand from the UI; the in-flight guard (keyed by system_id) means the
scheduled job and a manual "Refresh now" click can't both fire against
the same system at once - the second caller is told to try again shortly
instead of piling a second full paginated fetch onto the connection.

Directly-assigned profiles (user_access_summary(), added after a live
investigation on 2026-09-13): AGR_USERS/AGR_TCODES only cover access
granted through a PFCG role's menu - a profile assigned straight to a
user's master record (SU01's own Profiles tab, e.g. SAP_ALL, or a
manually-built Z-profile from SU02) grants tcodes with no PFCG role
involved at all, and is invisible to everything above. This was not a
hypothetical gap: investigating a real analyst report (a user's PA20/
PA10/SE93 activity not matching any of their role-menu tcodes) turned up
SAP_ALL directly assigned to that exact user.

Deliberately NOT bulk-synced the same way as AGR_USERS/AGR_TCODES -
validated live against S23 before writing any of this:
  - USR04 (the classic direct-profile-assignment table) exists and BNAME/
    MANDT read fine via RFC_READ_TABLE, but its actual profile data lives
    in a single PROFS field - confirmed via DDIF_FIELDINFO_GET to be one
    3750-char packed LCHR field, not flat repeating columns. Reading it
    (or even just the table's full field list with FIELDS left empty)
    raises DATA_BUFFER_EXCEEDED against the real system - RFC_READ_TABLE's
    per-row buffer can't hold it, and even if it could, decoding a packed
    fixed-width profile list by guesswork is exactly the kind of
    unverified bit-level parsing this project has already been burned by
    once (see sal/rules/_coverage.py's docstring) - not attempted.
  - SUSR_GET_PROFILES_OF_USER_RFC works cleanly and was already validated
    per-user during Phase F planning (scripts/probes/probe_user_master.py:
    real import parameter is USER_NAME, not USERNAME; raises USER_NOT_EXISTS
    for a user_id that isn't a maintained SU01 record, e.g. some values
    seen in events.user_id) - but it takes exactly one user at a time, with
    no bulk/table-scan equivalent. Given S23 alone has ~20k distinct users
    on record, a daily bulk pull the way AGR_USERS/AGR_TCODES get pulled
    would mean ~20k individual RFC round-trips - not what an analyst
    investigating one specific user needs anyway. So this is a live,
    on-demand, single-user lookup (mirrors sal/audit_config.py's
    check_audit_config() shape: one bounded RFC call per invocation, not
    sync_role_context()'s bulk daily-refresh shape), timeout-bounded the
    same way for the same reason (pyrfc has no per-call timeout, this runs
    on Windows with no signal.alarm).
"""
import concurrent.futures
import logging
import threading
import time
from datetime import date, datetime, timezone

from . import config
from .sap_connector import SapConnection
from .storage.db import get_connection, init_schema

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000
_MAX_PAGES = 500  # safety cap (500k rows) - comfortably above the ~171k real AGR_TCODES rows seen

_USER_ROLES_FIELDS = ["UNAME", "AGR_NAME", "FROM_DAT", "TO_DAT"]
_ROLE_TCODES_FIELDS = ["AGR_NAME", "TCODE"]

# Many sequential paginated RFC_READ_TABLE calls, not one - bounded well
# above the observed real-data duration (see module docstring).
_RFC_TIMEOUT_SECONDS = 300

_inflight_lock = threading.Lock()
_inflight: set[str] = set()


def _read_table_all(conn, table: str, fields: list[str]) -> tuple[list[dict], bool]:
    """RFC_READ_TABLE, paginated via ROWSKIPS/ROWCOUNT until a short page
    (or an empty one) signals the end - a single call cannot be assumed to
    return an entire table. Returns (rows, truncated) - truncated is True
    only if the _MAX_PAGES safety cap was hit, meaning more rows may exist
    that were never fetched; callers must surface this, not silently
    report success as if the data were complete.
    """
    rows: list[dict] = []
    skips = 0
    hit_cap = True
    for _ in range(_MAX_PAGES):
        result = conn.call(
            "RFC_READ_TABLE", QUERY_TABLE=table, DELIMITER="|",
            FIELDS=[{"FIELDNAME": f} for f in fields],
            ROWSKIPS=skips, ROWCOUNT=_PAGE_SIZE,
        )
        page = result.get("DATA", [])
        for raw in page:
            values = raw["WA"].split("|")
            if len(values) != len(fields):
                logger.warning(
                    "Skipping malformed %s row (expected %d fields, got %d): %r",
                    table, len(fields), len(values), raw["WA"],
                )
                continue
            rows.append(dict(zip(fields, (v.strip() for v in values))))
        skips += len(page)
        if len(page) < _PAGE_SIZE:
            hit_cap = False
            break
    if hit_cap:
        logger.warning(
            "Hit the %d-page safety cap reading %s - data may be truncated", _MAX_PAGES, table
        )
    return rows, hit_cap


def _fetch_role_context(system_id: str) -> tuple[list[dict], list[dict], bool]:
    with SapConnection(system_id) as conn:
        user_roles, users_truncated = _read_table_all(conn, "AGR_USERS", _USER_ROLES_FIELDS)
        role_tcodes, tcodes_truncated = _read_table_all(conn, "AGR_TCODES", _ROLE_TCODES_FIELDS)
    return user_roles, role_tcodes, users_truncated or tcodes_truncated


def _run_fetch_with_timeout(system_id: str, timeout: float) -> tuple[list[dict], list[dict], bool]:
    """Run _fetch_role_context on its own daemon thread; bound only the
    caller's wait. Mirrors sal/audit_config.py's _run_with_timeout() -
    see this module's docstring for why.
    """
    future: concurrent.futures.Future = concurrent.futures.Future()
    started_at = time.monotonic()

    def _target():
        try:
            future.set_result(_fetch_role_context(system_id))
        except Exception as exc:  # noqa: BLE001 - captured via the future, not swallowed
            future.set_exception(exc)

    threading.Thread(target=_target, daemon=True, name=f"sal-role-context-{system_id}").start()

    def _on_done(fut: concurrent.futures.Future) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed > timeout:
            exc = fut.exception()
            if exc is not None:
                logger.warning(
                    "role-context fetch for %s finished %.1fs after its %.0fs timeout, "
                    "with error: %s", system_id, elapsed, timeout, exc,
                )
            else:
                logger.info(
                    "role-context fetch for %s finished %.1fs after its %.0fs timeout - "
                    "result discarded, caller already gave up", system_id, elapsed, timeout,
                )
        with _inflight_lock:
            _inflight.discard(system_id)

    future.add_done_callback(_on_done)
    return future.result(timeout=timeout)


def _replace_role_context(system_id: str, client: str, user_roles: list[dict],
                           role_tcodes: list[dict]) -> None:
    """Delete this system/client's existing rows and insert the freshly
    fetched ones, in one transaction - only ever called after a fully
    successful fetch, so a failure here (e.g. a locked database) leaves
    the previous refresh's data as whichever state SQLite's own
    rollback-on-no-commit leaves it in, and is caught by the caller so the
    attempt still gets logged rather than raising uncaught.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn_db = get_connection()
    try:
        conn_db.execute(
            "DELETE FROM user_roles WHERE system_id = ? AND client = ?", (system_id, client)
        )
        conn_db.executemany(
            "INSERT INTO user_roles "
            "(system_id, client, user_id, role_name, from_dat, to_dat, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (system_id, client, r.get("UNAME"), r.get("AGR_NAME"),
                 r.get("FROM_DAT") or None, r.get("TO_DAT") or None, now)
                for r in user_roles
            ],
        )
        conn_db.execute(
            "DELETE FROM role_tcodes WHERE system_id = ? AND client = ?", (system_id, client)
        )
        conn_db.executemany(
            "INSERT INTO role_tcodes (system_id, client, role_name, tcode, captured_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(system_id, client, r.get("AGR_NAME"), r.get("TCODE"), now) for r in role_tcodes],
        )
        conn_db.commit()
    finally:
        conn_db.close()


def _log_refresh_run(system_id: str, client: str | None, run_at: str, actor: str, status: str,
                      user_role_rows: int | None, role_tcode_rows: int | None,
                      error_message: str | None) -> None:
    conn_db = get_connection()
    try:
        conn_db.execute(
            "INSERT INTO role_context_refresh_runs "
            "(system_id, client, run_at, actor, status, user_role_rows, role_tcode_rows, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (system_id, client, run_at, actor, status, user_role_rows, role_tcode_rows, error_message),
        )
        conn_db.commit()
    finally:
        conn_db.close()


def sync_role_context(system_id: str, actor: str = "system") -> dict:
    """Refresh one system's role/tcode context from live SAP.

    Only one refresh per system_id runs at a time - a duplicate request
    (the daily scheduled job and a manual "Refresh now" landing at nearly
    the same moment, or two clicks) is rejected immediately rather than
    piling a second full paginated fetch onto the connection. See this
    module's docstring for the fetch-before-write / all-or-nothing model
    and why every attempt is logged regardless of where it fails.
    """
    system_id = system_id.strip().upper()

    with _inflight_lock:
        if system_id in _inflight:
            return {
                "status": "error", "system_id": system_id, "client": None,
                "run_at": datetime.now(timezone.utc).isoformat(),
                "user_role_rows": None, "role_tcode_rows": None,
                "error": "A role-context refresh for this system is already in progress - try again shortly",
            }
        _inflight.add(system_id)

    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    status = "error"
    error_message = None
    client: str | None = None
    user_roles: list[dict] = []
    role_tcodes: list[dict] = []

    try:
        client = config.sap_system_config(system_id)["client"]
        user_roles, role_tcodes, truncated = _run_fetch_with_timeout(system_id, _RFC_TIMEOUT_SECONDS)
        status = "success_truncated" if truncated else "success"
    except concurrent.futures.TimeoutError:
        error_message = f"Timed out after {_RFC_TIMEOUT_SECONDS}s waiting for SAP"
        # Deliberately do NOT discard the in-flight entry here - _on_done
        # (fired when the background thread actually finishes) owns that,
        # so a second refresh can't pile another thread onto this target
        # while the first one is still genuinely running.
    except Exception as exc:  # noqa: BLE001 - covers config lookup failures too (e.g. an
        # unconfigured system) - any failure up to this point must still
        # finalize a logged run, not propagate raw.
        error_message = str(exc)
        with _inflight_lock:
            _inflight.discard(system_id)

    # Write phase is deliberately its own try/except, separate from the
    # fetch above - a failure here must never skip logging this attempt.
    if status in ("success", "success_truncated"):
        try:
            _replace_role_context(system_id, client, user_roles, role_tcodes)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_message = f"Fetched role context but failed to store it: {exc}"

    try:
        _log_refresh_run(
            system_id, client, now, actor, status,
            len(user_roles) if status != "error" else None,
            len(role_tcodes) if status != "error" else None,
            error_message,
        )
    except Exception:  # noqa: BLE001 - logging the attempt must never itself raise uncaught
        logger.exception("Failed to log role-context refresh run for %s", system_id)

    logger.info("Role-context refresh for %s: status=%s users=%d roles/tcodes=%d",
                system_id, status, len(user_roles), len(role_tcodes))
    return {
        "status": status, "system_id": system_id, "client": client, "run_at": now,
        "user_role_rows": len(user_roles) if status != "error" else None,
        "role_tcode_rows": len(role_tcodes) if status != "error" else None,
        "error": error_message,
    }


def _current_roles_and_tcodes(system_id: str, client: str | None, user_id: str,
                               as_of: str) -> tuple[list[str] | None, set[str]]:
    """Shared query logic behind authorized_tcodes_for_user() and
    user_access_summary() - previously duplicated between the two
    (python-reviewer caught the duplication during this feature's own
    review: same SQL in two places is a drift risk, and it ran the same
    two SELECTs twice per user_access_summary() call for no benefit).

    Returns (role_names, tcodes): role_names is None only if this user has
    ZERO role rows on record at all, at any validity date (see
    authorized_tcodes_for_user()'s docstring for why that distinction from
    "empty list" matters) - tcodes is always an empty set in that case.
    `client` may be None/empty to mean "any client," matching the
    conditional-clause convention already used by role_context_counts()/
    latest_refresh()/list_refresh_runs() in this same file (python-reviewer
    also caught that the old hardcoded "client = ?" would silently return
    "no role data" for a None client rather than matching any).
    """
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?", "user_id = ?"], [system_id, user_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        where = " AND ".join(clauses)

        has_any_role_row = conn.execute(
            f"SELECT 1 FROM user_roles WHERE {where} LIMIT 1", params
        ).fetchone()
        if has_any_role_row is None:
            return None, set()

        role_rows = conn.execute(
            f"SELECT DISTINCT role_name FROM user_roles WHERE {where} "
            "AND (from_dat IS NULL OR from_dat <= ?) AND (to_dat IS NULL OR to_dat >= ?)",
            params + [as_of, as_of],
        ).fetchall()
        if not role_rows:
            return [], set()  # had role(s) on record, none currently valid

        role_names = [r["role_name"] for r in role_rows]
        role_clauses, role_params = ["system_id = ?"], [system_id]
        if client:
            role_clauses.append("client = ?")
            role_params.append(client)
        placeholders = ", ".join("?" for _ in role_names)
        role_clauses.append(f"role_name IN ({placeholders})")
        tcode_rows = conn.execute(
            f"SELECT DISTINCT tcode FROM role_tcodes WHERE {' AND '.join(role_clauses)}",
            role_params + role_names,
        ).fetchall()
        return role_names, {r["tcode"] for r in tcode_rows}
    finally:
        conn.close()


def authorized_tcodes_for_user(system_id: str, client: str, user_id: str,
                                as_of: str | None = None) -> set[str] | None:
    """Tcodes assigned via any role held by this user, valid as of
    `as_of` (default: today). Dates are compared as SAP's own raw
    "YYYYMMDD" strings - `as_of` MUST be built the same way, not with
    `.isoformat()`, or the comparison silently breaks the same way the
    retention purge's cutoff once did (see Docs/Memory.md item 13/#3.8).

    Returns None - not an empty set - only if this user has ZERO role
    rows on record at all, at any validity date (the "never had, or had
    every role fully removed" case - see this module's docstring on why
    a full removal leaves no row rather than an expired one). A user with
    at least one role row that simply isn't valid as of `as_of` (e.g. its
    own scheduled TO_DAT has passed) returns an empty set, not None -
    they have role history on record, it's just not currently valid,
    which is a materially different finding than no role data existing
    at all. Callers must not conflate the two.
    """
    init_schema()
    system_id = system_id.strip().upper()
    as_of = as_of or date.today().strftime("%Y%m%d")
    role_names, tcodes = _current_roles_and_tcodes(system_id, client, user_id, as_of)
    return tcodes if role_names is not None else None


# Single lightweight RFC call, not the many-page bulk fetch above - bounded
# far more tightly than _RFC_TIMEOUT_SECONDS, matching sal/audit_config.py's
# single-call _RFC_TIMEOUT_SECONDS (30s) for the same reason (see this
# module's docstring's "Directly-assigned profiles" section).
_PROFILE_LOOKUP_TIMEOUT_SECONDS = 30

_profile_inflight_lock = threading.Lock()
_profile_inflight: set[tuple[str, str]] = set()


def _fetch_user_profiles(system_id: str, user_id: str) -> list[str]:
    with SapConnection(system_id) as conn:
        result = conn.call("SUSR_GET_PROFILES_OF_USER_RFC", USER_NAME=user_id)
    return [row["PROFILE"] for row in result.get("PROFILE", [])]


def _run_profile_fetch_with_timeout(system_id: str, user_id: str, timeout: float) -> list[str]:
    """Mirrors _run_fetch_with_timeout() above / sal/audit_config.py's
    _run_with_timeout() exactly, and for the identical reason: pyrfc has no
    per-call timeout and this runs on Windows (no signal.alarm), so the
    call runs on its own daemon thread and the caller only bounds its wait.
    """
    key = (system_id, user_id)
    future: concurrent.futures.Future = concurrent.futures.Future()
    started_at = time.monotonic()

    def _target():
        try:
            future.set_result(_fetch_user_profiles(system_id, user_id))
        except Exception as exc:  # noqa: BLE001 - captured via the future, not swallowed
            future.set_exception(exc)

    threading.Thread(
        target=_target, daemon=True, name=f"sal-user-profiles-{system_id}-{user_id}"
    ).start()

    def _on_done(fut: concurrent.futures.Future) -> None:
        elapsed = time.monotonic() - started_at
        if elapsed > timeout:
            exc = fut.exception()
            if exc is not None:
                logger.warning(
                    "user-profile lookup for %s/%s finished %.1fs after its %.0fs "
                    "timeout, with error: %s", system_id, user_id, elapsed, timeout, exc,
                )
            else:
                logger.info(
                    "user-profile lookup for %s/%s finished %.1fs after its %.0fs "
                    "timeout - result discarded, caller already gave up",
                    system_id, user_id, elapsed, timeout,
                )
        with _profile_inflight_lock:
            _profile_inflight.discard(key)

    future.add_done_callback(_on_done)
    return future.result(timeout=timeout)


def directly_assigned_profiles(system_id: str, user_id: str) -> tuple[list[str] | None, str | None]:
    """Live, per-user lookup of profiles assigned directly to a user's SAP
    master record (see this module's docstring - "Directly-assigned
    profiles"). Returns (profiles, error) - exactly one is None on any
    given call. Shares the in-flight de-dup guard and timeout-bounded RFC
    call with user_access_summary() (which calls this too, see below) -
    both ultimately hit the same live SUSR_GET_PROFILES_OF_USER_RFC for
    the same (system_id, user_id) key, so a scheduled sync's automated
    lookup and a manual "look up this user" click can't pile two live RFC
    calls onto the same user at once.
    """
    system_id = system_id.strip().upper()
    user_id = user_id.strip().upper()
    key = (system_id, user_id)
    with _profile_inflight_lock:
        already_running = key in _profile_inflight
        if not already_running:
            _profile_inflight.add(key)
    if already_running:
        return None, "A profile lookup for this user is already in progress - try again shortly"
    try:
        return sorted(_run_profile_fetch_with_timeout(system_id, user_id, _PROFILE_LOOKUP_TIMEOUT_SECONDS)), None
    except concurrent.futures.TimeoutError:
        return None, f"Timed out after {_PROFILE_LOOKUP_TIMEOUT_SECONDS}s waiting for SAP"
    except Exception as exc:  # noqa: BLE001 - e.g. USER_NOT_EXISTS, connection failure
        with _profile_inflight_lock:
            _profile_inflight.discard(key)
        return None, str(exc)


def user_access_summary(system_id: str, client: str, user_id: str,
                         as_of: str | None = None) -> dict:
    """Everything this module can currently say about one user's access,
    combined: PFCG roles and role-menu tcodes from the local, bulk-synced
    tables (no new RFC call - already kept fresh by sync_role_context()),
    plus a live, on-demand fetch of profiles assigned directly to this
    user's master record (see this module's docstring - SAP_ALL and
    similar directly-assigned profiles are invisible to the role-menu data
    alone). The profile fetch is a separate try/except from the role/tcode
    lookup: a live RFC failure (timeout, USER_NOT_EXISTS for a user_id that
    isn't a maintained SU01 record, connection error) must not hide
    locally-available role/tcode data behind an unrelated error.
    """
    init_schema()
    system_id = system_id.strip().upper()
    # SAP usernames (AGR_USERS.UNAME, user_roles.user_id) are stored
    # uppercase - normalize input the same way system_id already is above,
    # so a lowercase-typed username in the UI doesn't silently look like
    # "no role data" (security-reviewer caught this during this feature's
    # own review: a case mismatch reads as a false negative, not an error).
    user_id = user_id.strip().upper()
    as_of = as_of or date.today().strftime("%Y%m%d")

    role_names, tcodes = _current_roles_and_tcodes(system_id, client, user_id, as_of)
    has_role_data = role_names is not None
    roles = sorted(role_names or [])
    tcodes_via_roles = sorted(tcodes)

    profiles, profiles_error = directly_assigned_profiles(system_id, user_id)

    return {
        "system_id": system_id, "client": client, "user_id": user_id, "as_of": as_of,
        "has_role_data": has_role_data, "roles": roles, "tcodes_via_roles": tcodes_via_roles,
        "profiles": profiles, "profiles_error": profiles_error,
    }


def latest_refresh(system_id: str, client: str | None = None) -> dict | None:
    init_schema()
    system_id = system_id.strip().upper()
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?"], [system_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        row = conn.execute(
            f"SELECT * FROM role_context_refresh_runs WHERE {' AND '.join(clauses)} "
            "ORDER BY run_at DESC LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_refresh_runs(system_id: str, client: str | None = None, limit: int = 20) -> list[dict]:
    init_schema()
    system_id = system_id.strip().upper()
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?"], [system_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        rows = conn.execute(
            f"SELECT * FROM role_context_refresh_runs WHERE {' AND '.join(clauses)} "
            "ORDER BY run_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def role_context_counts(system_id: str, client: str | None = None) -> dict:
    """Live distinct counts for the UI status panel."""
    init_schema()
    system_id = system_id.strip().upper()
    conn = get_connection()
    try:
        clauses, params = ["system_id = ?"], [system_id]
        if client:
            clauses.append("client = ?")
            params.append(client)
        where = " AND ".join(clauses)
        users = conn.execute(
            f"SELECT COUNT(DISTINCT user_id) c FROM user_roles WHERE {where}", params
        ).fetchone()["c"]
        roles = conn.execute(
            f"SELECT COUNT(DISTINCT role_name) c FROM user_roles WHERE {where}", params
        ).fetchone()["c"]
        tcodes = conn.execute(
            f"SELECT COUNT(DISTINCT tcode) c FROM role_tcodes WHERE {where}", params
        ).fetchone()["c"]
    finally:
        conn.close()
    return {"users": users, "roles": roles, "tcodes": tcodes}
