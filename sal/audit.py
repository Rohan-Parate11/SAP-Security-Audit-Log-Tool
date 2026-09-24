"""Application-level audit trail (S1-11): records who did what *inside SAL*
(searches, collection runs, connection tests, catalogue changes) - separate
from the SAP Security Audit Log events SAL collects and stores in ``events``.

The ``actor`` recorded here comes from a display-name cookie the web UI asks
for on first visit (see ``sal/web/api.py``'s identity endpoints). That is
attribution only, not access control - anyone can type any name. This module
does not enforce who is allowed to do what; it only records who said they did
it, so accesses to sensitive audit data can be reconstructed after the fact.
"""
import json
from datetime import datetime, timezone

from .storage.db import get_connection, init_schema


def record(actor: str, action: str, system_id: str | None = None, client: str | None = None,
           params: dict | None = None, result_count: int | None = None,
           outcome: str = "ok") -> None:
    init_schema()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sal_audit_log "
            "(occurred_at, actor, action, source_system, client, params_json, result_count, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                actor,
                action,
                system_id,
                client,
                json.dumps(params) if params else None,
                result_count,
                outcome,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_entries(limit: int = 200, offset: int = 0, actor: str | None = None,
                  action: str | None = None, system_id: str | None = None,
                  client: str | None = None) -> tuple[int, list[dict]]:
    init_schema()
    conn = get_connection()
    try:
        clauses, params = [], []
        if actor:
            clauses.append("actor = ?")
            params.append(actor)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if system_id:
            # OR source_system IS NULL - some actions (catalogue_add/remove,
            # rules_catalog_export, ...) aren't tied to any one SAP system,
            # so they're recorded with source_system=NULL. Scoping strictly
            # to `= ?` silently hid every one of those from the Activity tab
            # whenever a system happened to be selected in the nav bar
            # (nearly always) - they *were* being recorded, just filtered
            # out of view. Global entries should show regardless of scope.
            clauses.append("(source_system = ? OR source_system IS NULL)")
            params.append(system_id)
        if client:
            clauses.append("(client = ? OR client IS NULL)")
            params.append(client)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(
            f"SELECT COUNT(*) c FROM sal_audit_log {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM sal_audit_log {where} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return total, [dict(r) for r in rows]
    finally:
        conn.close()


def list_actions() -> list[str]:
    """Every distinct action string ever recorded - lets the Activity tab's
    filter dropdown build itself from what has actually happened rather
    than a hand-maintained list that silently drifts out of sync with new
    audit.record() call sites (found in review: several actions, including
    job_delete/job_restore, had no way to be filtered on because the
    frontend's list was never updated after they were added)."""
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT action FROM sal_audit_log ORDER BY action").fetchall()
        return [r["action"] for r in rows]
    finally:
        conn.close()
