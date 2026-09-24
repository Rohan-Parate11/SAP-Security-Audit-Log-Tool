"""Findings persistence & disposition (Blueprint v2, Phase A).

Sits above ``sal.rules.registry.run_all_rules`` rather than replacing it:
that function stays the pure "compute current findings from event history"
engine. This module is the workflow layer - it gives each computed finding a
stable identity, persists it once, and lets an analyst disposition it
(true/false positive, whitelist) in a way that survives future re-syncs.

Finding identity: a hash of (rule_key, system, client, user_id, detected_at,
stable evidence). detected_at alone is only second-granularity, and several
rules can legitimately emit more than one distinct finding for the same
user/rule within one second (e.g. sensitive_table_access firing once per
DU9 row - two different tables or activity codes logged in the same
second are two different findings, not one); evidence is folded into the
key to keep those distinct rather than silently colliding and dropping one
(confirmed against real data during implementation: 4 of 199 computed
findings collided before evidence was added to the key). A denylist of
known-volatile evidence fields (the online-baseline statistics that
legitimately shift as more history is backfilled, e.g. baseline_mean) is
excluded from the key so it doesn't destabilize identity for the rules that
report them.

Two known instabilities are still accepted for v1 rather than solved here -
see Docs/SAL_Architecture_Blueprint_v2.docx, Phase A: (1) incident-grouping
rules (mass_user_changes, shared_ip_multi_user) can reshape an incident's
boundary timestamp - and thus its evidence - if a later collection backfills
an event between two previously adjacent ones; (2) new_source's
known_ip_count is itself a running count that can shift slightly on
backfill. Neither invalidates an existing disposition - sync only ever
inserts-if-new, or for an existing finding_key, bumps last_seen_at (every
status) and, for a finding still at status 'open' or 'whitelisted' only,
also refreshes summary/evidence_json/severity to the latest computed
values (added 2026-09-15, FIND-07: identity is keyed on STABLE evidence
only, so a volatile field excluded from that key, e.g. a live profile
lookup's result, can still legitimately change what's stored for an
unchanged finding_key - freezing the displayed evidence at first-insert
time meant it could go stale forever even once the live data it reflects
had moved on. severity joined this same refresh shortly after, for the
identical reason applied to a rule's own logic rather than live data: a
rule-code change to what severity a given finding_key computes to -
e.g. sensitive_table_access/data_export's Medium-to-Low reclassification
that same day - would otherwise never reach an already-open finding).
A true_positive/false_positive finding's evidence is never rewritten
this way, deliberately (security-reviewer caught this distinction missing
from the first version of this fix): that's a considered human judgment
made against a specific evidence blob, and this tool's whole purpose is
being a trustworthy audit record. Status is never touched here except the
one whitelist-flip case
below. This means a finding that stops being computed on a later run is
not auto-resolved - it is left for an analyst to disposition explicitly
rather than silently dropped.

Verified (Phase A close-out, 2026-09-09): the two historical live-data
collection runs that overlap in the real pilot dataset (2026-08-27..29 and
2026-08-27..28) predate this module and were never synced, so they could not
be used to observe this in practice. Instead, tests/test_findings.py's
test_backfill_reshaped_incident_boundary_creates_separate_finding_not_silent_merge
pins the intended behavior directly: a boundary-reshaping backfill produces a
second, distinct finding rather than a silent merge, and the original is left
open. Treat that test, not just this docstring, as the source of truth if this
behavior ever needs to change.
"""
import hashlib
import json
from datetime import datetime, timezone

from .rules import run_all_rules
from .storage.db import get_connection, init_schema

OPEN_STATUSES = ("open", "true_positive", "false_positive", "whitelisted")

_VOLATILE_EVIDENCE_KEYS = {
    "baseline_mean", "baseline_stdev", "baseline_observations",
    "baseline_mean_hour", "baseline_stdev_hours",
    # role_refresh_checked_at (out_of_context_transaction.py, Phase F) is
    # purely informational context, not part of a finding's substance - it
    # changes every day the role-context refresh job runs even when the
    # underlying "not currently assigned" condition hasn't changed at all.
    # Without this exclusion, a genuinely unchanged finding gets a new
    # finding_key (and thus reappears as a brand-new "open" row) on every
    # refresh, silently discarding whatever disposition an analyst already
    # made on the previous day's key - found by python-reviewer before
    # shipping.
    "role_refresh_checked_at",
    # directly_assigned_profiles / directly_assigned_profiles_error /
    # has_broad_access_profile (out_of_context_transaction.py, Phase F) are
    # the result of a LIVE per-user RFC lookup at detection time, not part
    # of what makes this finding "the same finding" - a user's directly-
    # assigned profiles can genuinely change day to day (an admin revokes
    # SAP_ALL, say), or the lookup can transiently fail one day and succeed
    # the next. Same reasoning as role_refresh_checked_at above: without
    # this exclusion, a value that's expected to drift over time would
    # spawn a brand-new finding_key (and thus a new "open" row) every time
    # it changed, rather than being treated as freshened context on the
    # SAME finding. Found from a real UAT Round 2 retest report (FIND-07):
    # the "T-* profiles are role-generated, not directly assigned" fix
    # changed this exact evidence shape, which meant every finding computed
    # before the fix kept its OLD finding_key forever (sync_findings() only
    # bumps last_seen_at/status on an existing row, never its evidence) -
    # so the stale, T-*-including evidence stayed frozen in the database
    # indefinitely instead of ever picking up the corrected computation.
    "directly_assigned_profiles", "directly_assigned_profiles_error", "has_broad_access_profile",
}


def _stable_evidence(evidence: dict | None) -> dict:
    return {k: v for k, v in (evidence or {}).items() if k not in _VOLATILE_EVIDENCE_KEYS}


def _finding_key(f: dict) -> str:
    raw = "|".join([
        f["rule_key"],
        f.get("source_system") or "",
        f.get("client") or "",
        f.get("user_id") or "",
        f["detected_at"],
        json.dumps(_stable_evidence(f.get("evidence")), sort_keys=True, default=str),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _active_whitelist_match(conn, f: dict) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT source_system, client, user_id FROM finding_whitelist "
        "WHERE rule_key = ? AND expires_at > ?",
        (f["rule_key"], now),
    ).fetchall()
    for row in rows:
        if row["source_system"] and row["source_system"] != f.get("source_system"):
            continue
        if row["client"] and row["client"] != f.get("client"):
            continue
        if row["user_id"] and row["user_id"] != f.get("user_id"):
            continue
        return True
    return False


def sync_findings(system_id: str | None = None, client: str | None = None) -> dict:
    init_schema()
    computed = run_all_rules(system_id=system_id, client=client)
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        new_count = 0
        for f in computed:
            key = _finding_key(f)
            is_whitelisted = _active_whitelist_match(conn, f)
            status = "whitelisted" if is_whitelisted else "open"
            cur = conn.execute(
                "INSERT OR IGNORE INTO findings "
                "(finding_key, rule_key, rule_label, severity, source_system, client, "
                " user_id, detected_at, summary, evidence_json, first_seen_at, "
                " last_seen_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key, f["rule_key"], f["rule_label"], f["severity"],
                    f.get("source_system"), f.get("client"), f.get("user_id"),
                    f["detected_at"], f["summary"], json.dumps(f.get("evidence") or {}),
                    now, now, status,
                ),
            )
            if cur.rowcount:
                new_count += 1
            elif is_whitelisted:
                # A whitelist entry created after this finding was already
                # persisted must still suppress it - otherwise "whitelist
                # this" only ever affects findings nobody has seen yet.
                # Never override a status an analyst already disposed
                # (true_positive/false_positive) - only a still-open finding
                # is eligible to flip to whitelisted here.
                conn.execute(
                    "UPDATE findings SET last_seen_at = ?, status = 'whitelisted', "
                    " summary = ?, evidence_json = ?, severity = ? "
                    "WHERE finding_key = ? AND status = 'open'",
                    (now, f["summary"], json.dumps(f.get("evidence") or {}), f["severity"], key),
                )
            else:
                conn.execute(
                    "UPDATE findings SET last_seen_at = ? WHERE finding_key = ?",
                    (now, key),
                )
                # Also refreshes summary/evidence_json, not just last_seen_at
                # (found in the same Round 2 UAT retest as the denylist
                # additions above - FIND-07): the identity hash only covers
                # STABLE evidence, so two computed findings that map to the
                # SAME finding_key can still carry different volatile-field
                # values (a live profile lookup's latest result, a fresher
                # role-refresh timestamp). Freezing the stored evidence at
                # whichever run happened to insert the row first meant an
                # already-open finding's displayed evidence/summary could
                # go stale forever, even once the underlying computation
                # (or the live data it reflects) had genuinely moved on.
                #
                # Deliberately scoped to status IN ('open', 'whitelisted') -
                # never true_positive/false_positive. A security-reviewer
                # pass on this exact fix caught a real gap in the first
                # version (which refreshed unconditionally, any status):
                # this tool's whole purpose is being a trustworthy audit
                # record, and a true_positive/false_positive disposition is
                # a considered human judgment made against a SPECIFIC
                # evidence blob - silently rewriting that evidence out from
                # under an already-closed finding, automatically, on every
                # scheduled collection job, with no trace of what changed,
                # would undermine exactly the auditability SAL exists to
                # provide. A still-open finding (or one auto-suppressed by a
                # whitelist rule, which nobody individually adjudicated) has
                # no such stake yet, so keeping ITS evidence current is a
                # straightforward improvement with no such downside.
                # severity is included in this same refresh (added
                # 2026-09-15 alongside downgrading two sensitive_table_
                # access/data_export cases to Low - see CHANGELOG): it
                # isn't part of the identity hash either, so a rule-code
                # change to what severity a given finding_key computes to
                # would otherwise never reach an already-inserted open
                # finding, exactly the same staleness FIND-07 already
                # fixed for summary/evidence_json above.
                conn.execute(
                    "UPDATE findings SET summary = ?, evidence_json = ?, severity = ? "
                    "WHERE finding_key = ? AND status IN ('open', 'whitelisted')",
                    (f["summary"], json.dumps(f.get("evidence") or {}), f["severity"], key),
                )
        conn.commit()
        return {"computed": len(computed), "new": new_count}
    finally:
        conn.close()


_IN_CLAUSE_COLUMNS = ("rule_key", "severity", "status")  # every column this
# module's own call sites are allowed to pass to _add_in_clause() below -
# `column` is always one of these hardcoded literals today anyway (never
# request-derived), but asserting it here means a future call site that
# somehow passed request input instead would fail loudly in dev/tests
# rather than silently becoming a SQL injection vector.


def _add_in_clause(clauses: list[str], params: list, column: str, values: str | list[str] | None) -> None:
    """Appends a `column IN (?, ?, ...)` clause when `values` is non-empty -
    a single string is treated as a one-item list, so existing single-value
    callers keep working unchanged. `column` is always a fixed, hardcoded
    string from this module's own code, never request input, so building
    the placeholder list dynamically from len(values) is safe - only the
    values themselves (parameterized, never interpolated) can vary.
    """
    assert column in _IN_CLAUSE_COLUMNS, f"unexpected column {column!r} passed to _add_in_clause"
    if values is None:
        return
    if isinstance(values, str):
        values = [values]
    values = [v for v in values if v]
    if not values:
        return
    clauses.append(f"{column} IN ({', '.join('?' for _ in values)})")
    params.extend(values)


def list_findings(limit: int = 200, offset: int = 0, rule: str | list[str] | None = None,
                   severity: str | list[str] | None = None, status: str | list[str] | None = None,
                   system_id: str | None = None, client: str | None = None,
                   user_id: str | None = None, finding_key: str | None = None) -> tuple[int, list[dict]]:
    """rule/severity/status each accept a single value (unchanged, existing
    callers) or a list - added for the Findings table's Excel-style
    column-header filters, where checking multiple boxes means "any of
    these" (SQL IN). user_id is a new, separate LIKE (contains) filter -
    unlike the others it's free text, not a fixed enum, so it isn't a
    checkbox list in the UI.

    finding_key looks up exactly one finding by its own primary key -
    added so the Activity page's finding_dispose entries (which only ever
    carried the opaque finding_key hash, with no way to see which actual
    finding that was) can link straight to it. Deliberately bypasses every
    other filter, including system_id/client scope: the key alone is
    already a complete, unique identifier, and an analyst following a link
    from Activity may currently have a *different* system selected in the
    UI than the one the disposed finding actually belongs to - requiring
    them to match first would turn "show me that finding" into "show me
    that finding, but only if you happen to already be looking at the
    right system," silently returning nothing instead.
    """
    init_schema()
    conn = get_connection()
    try:
        clauses, params = [], []
        if finding_key:
            clauses.append("finding_key = ?")
            params.append(finding_key)
        else:
            _add_in_clause(clauses, params, "rule_key", rule)
            _add_in_clause(clauses, params, "severity", severity)
            _add_in_clause(clauses, params, "status", status)
            if system_id:
                clauses.append("source_system = ?")
                params.append(system_id)
            if client:
                clauses.append("client = ?")
                params.append(client)
            if user_id:
                clauses.append("user_id LIKE ?")
                params.append(f"%{user_id}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(f"SELECT COUNT(*) c FROM findings {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM findings {where} "
            "ORDER BY CASE severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, "
            "detected_at DESC "
            "LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
            items.append(item)
        return total, items
    finally:
        conn.close()


def dispose_finding(finding_key: str, status: str, actor: str,
                     reason_code: str | None = None, notes: str | None = None) -> bool:
    init_schema()
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE findings SET status = ?, disposed_by = ?, disposed_at = ?, "
            "reason_code = ?, analyst_notes = ? WHERE finding_key = ?",
            (status, actor, datetime.now(timezone.utc).isoformat(), reason_code, notes, finding_key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_whitelist(rule_key: str, reason: str, created_by: str,
                   expires_at: str, system_id: str | None = None,
                   client: str | None = None, user_id: str | None = None) -> int:
    init_schema()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO finding_whitelist "
            "(rule_key, source_system, client, user_id, reason, created_by, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rule_key, system_id, client, user_id, reason, created_by,
             datetime.now(timezone.utc).isoformat(), expires_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_whitelist() -> list[dict]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM finding_whitelist ORDER BY expires_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_whitelist(entry_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM finding_whitelist WHERE id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()
