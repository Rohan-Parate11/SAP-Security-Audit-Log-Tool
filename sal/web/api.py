"""JSON API for the SAL single-page UI. All pages render client-side from
these endpoints rather than full server-rendered pages, so filters/system
switches update in place instead of reloading the document.
"""
import re
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, request

from .. import (
    audit, audit_config, credentials, export, filtered_schedule, friendly_errors,
    itgc_events_report, itgc_report, jobs, retention, role_context, rules_catalog, schedule, sla,
)
from .. import findings as findings_svc
from .. import systems as systems_svc
from ..catalogues import (
    add_critical_transaction,
    add_sensitive_table,
    list_critical_transactions,
    list_critical_transactions_detailed,
    list_sensitive_tables,
    list_sensitive_tables_detailed,
    remove_critical_transaction,
    remove_sensitive_table,
)
from ..collectors import event_timestamp
from ..rules import RULES
from ..sap_connector import SapConnection, SapConnectionError
from ..storage.db import get_connection

api_bp = Blueprint("api", __name__, url_prefix="/api")

_DATE_RE = re.compile(r"^\d{8}$")
_TIME_RE = re.compile(r"^\d{6}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Attribution only, not access control - see sal/audit.py's module docstring.
ACTOR_COOKIE = "sal_actor"
_MAX_ACTOR_LEN = 80


def _current_actor() -> str | None:
    value = (request.cookies.get(ACTOR_COOKIE) or "").strip()
    return value or None


def _scope_from_args():
    system_id = request.args.get("system_id", "").strip().upper() or None
    client = request.args.get("client", "").strip() or None
    return system_id, client


def _multi_arg(name: str) -> list[str]:
    """A repeated query-string key (?status=queued&status=running) as a
    clean list - used by the Excel-style column-header filters, where
    checking several boxes in one column means "any of these". Capped at
    _MAX_MULTI_FILTER_VALUES (defined below, near events_export()'s own
    _split_multi() - the same cap, same reason: enough IN (...) placeholders
    can exceed SQLite's bound-parameter limit, an uncaught error Werkzeug's
    debugger would otherwise surface since run.py always runs debug=True).
    Silently truncated rather than 400ing like _split_multi() does - the
    checkbox UI driving this can realistically never check more than a
    handful of values (one column's whole known option set is a dozen or
    so at most), so this ceiling only ever matters against a hand-crafted
    URL, where truncating is an acceptable simplification over threading a
    400 through every one of this function's several call sites.
    """
    return [v.strip() for v in request.args.getlist(name) if v.strip()][:_MAX_MULTI_FILTER_VALUES]


def _severity_counts(findings: list[dict]) -> dict:
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        counts[f.get("severity", "Low")] = counts.get(f.get("severity", "Low"), 0) + 1
    return counts


@api_bp.get("/identity")
def get_identity():
    return jsonify({"actor": _current_actor()})


@api_bp.post("/identity")
def post_identity():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:_MAX_ACTOR_LEN]
    if not name:
        return jsonify({"ok": False, "error": "Name is required"}), 400

    resp = jsonify({"ok": True, "actor": name})
    resp.set_cookie(ACTOR_COOKIE, name, max_age=365 * 86400, samesite="Lax")
    return resp


@api_bp.get("/audit")
def audit_list():
    system_id, client = _scope_from_args()
    actor_filter = request.args.get("actor", "").strip() or None
    action_filter = request.args.get("action", "").strip() or None
    limit = min(int(request.args.get("limit", 200) or 200), 500)
    offset = max(int(request.args.get("offset", 0) or 0), 0)

    total, items = audit.list_entries(
        limit=limit, offset=offset, actor=actor_filter, action=action_filter,
        system_id=system_id, client=client,
    )
    return jsonify({"total": total, "items": items})


@api_bp.get("/audit/actions")
def audit_actions():
    return jsonify({"actions": audit.list_actions()})


@api_bp.get("/systems")
def systems():
    return jsonify({"systems": systems_svc.list_systems()})


@api_bp.post("/systems")
def post_system():
    data = request.get_json(silent=True) or {}
    system_id = (data.get("system_id") or "").strip().upper()
    environment = (data.get("environment") or "").strip()
    ashost = (data.get("ashost") or "").strip()
    sysnr = (data.get("sysnr") or "").strip()
    client = (data.get("client") or "").strip()
    description = (data.get("description") or "").strip() or None

    if not system_id or not ashost or not sysnr or not client:
        return jsonify({"ok": False, "error": "system_id, ashost, sysnr, and client are required"}), 400
    if environment not in systems_svc.ENVIRONMENTS:
        return jsonify({"ok": False, "error": f"environment must be one of {systems_svc.ENVIRONMENTS}"}), 400

    actor = _current_actor() or "unknown"
    try:
        # add_system() itself detects a duplicate (INSERT OR IGNORE +
        # rowcount) rather than relying on a separate check-then-insert,
        # which would race under Flask's threaded=True dev server.
        systems_svc.add_system(system_id, environment, ashost, sysnr, client, actor, description)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    jobs.register_daily_job(system_id, client or None)
    jobs.register_role_context_job(system_id)
    audit.record(actor, "system_add", system_id=system_id, client=client,
                 params={"environment": environment, "ashost": ashost, "client": client})
    return jsonify({"ok": True, "items": systems_svc.list_systems()}), 201


@api_bp.patch("/systems/<system_id>")
def patch_system(system_id):
    system_id = system_id.strip().upper()
    data = request.get_json(silent=True) or {}
    environment = (data.get("environment") or "").strip() or None
    if environment is not None and environment not in systems_svc.ENVIRONMENTS:
        return jsonify({"ok": False, "error": f"environment must be one of {systems_svc.ENVIRONMENTS}"}), 400

    # description distinguishes "key omitted" (leave unchanged, systems_svc.UNSET)
    # from "explicitly sent" (even "" clears it) - the other fields are all
    # NOT NULL columns, so collapsing "" to "unchanged" for them is fine.
    description = (data["description"].strip() or None) if "description" in data else systems_svc.UNSET
    ashost = (data.get("ashost") or "").strip() or None
    sysnr = (data.get("sysnr") or "").strip() or None
    client = (data.get("client") or "").strip() or None
    found = systems_svc.update_system(
        system_id, environment=environment, description=description,
        ashost=ashost, sysnr=sysnr, client=client,
    )
    if not found:
        return jsonify({"ok": False, "error": "Unknown system_id"}), 404

    updated = systems_svc.get_system(system_id)
    jobs.register_daily_job(system_id, updated.get("client") or None)
    jobs.register_role_context_job(system_id)
    audit.record(_current_actor() or "unknown", "system_update", system_id=system_id,
                 client=updated.get("client") or None,
                 params={"environment": updated["environment"], "description": updated["description"],
                         "ashost": updated["ashost"], "sysnr": updated["sysnr"], "client": updated["client"]})
    return jsonify({"ok": True, "items": systems_svc.list_systems()})


@api_bp.delete("/systems/<system_id>")
def delete_system(system_id):
    system_id = system_id.strip().upper()
    # Looked up before removing, same completeness fix as the other
    # audit-scope gaps this round - client is gone from the registry the
    # instant remove_system() succeeds, so it must be captured first.
    existing = systems_svc.get_system(system_id)
    deleted = systems_svc.remove_system(system_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Unknown system_id"}), 404
    jobs.unregister_daily_job(system_id)
    jobs.unregister_role_context_job(system_id)
    schedule.remove_schedule(system_id)
    for cfg in filtered_schedule.list_schedules(system_id):
        jobs.unregister_filtered_schedule_job(cfg["id"])
        filtered_schedule.remove_schedule(cfg["id"])
    # Otherwise an orphaned, still-decryptable row survives indefinitely:
    # invisible in the Password Manager UI (which only ever lists
    # currently-registered systems) yet still fetchable by direct API
    # call, and silently reactivated with no new credential_set audit
    # entry if a system with this same system_id is ever re-added later
    # (security-reviewer, MEDIUM).
    credentials.remove_credential(system_id)
    audit.record(_current_actor() or "unknown", "system_remove", system_id=system_id,
                 client=existing["client"] if existing else None)
    return jsonify({"ok": True, "items": systems_svc.list_systems()})


@api_bp.get("/systems/<system_id>/schedule")
def get_system_schedule(system_id):
    system_id = system_id.strip().upper()
    if systems_svc.get_system(system_id) is None:
        return jsonify({"ok": False, "error": "Unknown system_id"}), 404
    cfg = schedule.get_schedule(system_id)
    cfg["next_scheduled_run"] = jobs.next_scheduled_run(system_id)
    return jsonify({"item": cfg})


@api_bp.put("/systems/<system_id>/schedule")
def put_system_schedule(system_id):
    system_id = system_id.strip().upper()
    system = systems_svc.get_system(system_id)
    if system is None:
        return jsonify({"ok": False, "error": "Unknown system_id"}), 404

    data = request.get_json(silent=True) or {}
    interval_type = (data.get("interval_type") or "").strip().lower()
    actor = _current_actor() or "unknown"
    try:
        cfg = schedule.set_schedule(
            system_id, interval_type, actor,
            anchor_hour=data.get("anchor_hour"), anchor_minute=data.get("anchor_minute"),
            interval_hours=data.get("interval_hours"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Re-registers the live APScheduler job immediately with the new
    # cadence (replace_existing=True) - the same synchronous
    # write-then-reregister sequence system_update() already uses, so a
    # schedule change takes effect without an app restart.
    jobs.register_daily_job(system_id, system.get("client") or None)
    audit.record(actor, "schedule_update", system_id=system_id, client=system.get("client") or None,
                 params={
                     "interval_type": cfg["interval_type"], "anchor_hour": cfg["anchor_hour"],
                     "anchor_minute": cfg["anchor_minute"], "interval_hours": cfg["interval_hours"],
                 })
    cfg["next_scheduled_run"] = jobs.next_scheduled_run(system_id)
    return jsonify({"item": cfg})


# ---- Central credential store (sal/credentials.py) -------------------------
#
# Requested directly, 2026-09-16 (HOME-02): every read of an actual stored
# password is audit-logged as credential_view - the project owner's
# explicit, informed choice was that a stored password stays viewable
# through the UI (not write-only), given this app has no RBAC; logging
# every reveal is the one mitigation available for that choice. See
# sal/credentials.py's own module docstring for the full reasoning.

@api_bp.get("/credentials")
def list_credentials():
    """One row per registered system with its credential source - never
    the password itself, just where it resolves from (or "missing") - for
    the Password Manager page's overview list."""
    items = [
        {"system_id": s["system_id"], "description": s["description"],
         "environment": s["environment"], "source": credentials.credential_source(s["system_id"])}
        for s in systems_svc.list_systems()
    ]
    return jsonify({"items": items})


@api_bp.get("/credentials/<system_id>")
def get_credential(system_id):
    system_id = system_id.strip().upper()
    try:
        stored = credentials.get_credential(system_id)
    except credentials.CredentialStoreNotConfigured as exc:
        # Caught explicitly, not left to propagate (security-reviewer,
        # HIGH): run.py runs with debug=True unconditionally, and an
        # uncaught exception here would surface Werkzeug's interactive
        # traceback page - which prints each frame's local variables,
        # including _fernet()'s own SAL_CREDENTIAL_ENCRYPTION_KEY value,
        # to anyone who hits this exact failure mode (a rotated/missing
        # key, or ciphertext from a different key - both realistic
        # operational events, not hypothetical). That would leak the one
        # key that decrypts EVERY system's stored password, and - since
        # the exception fires before the line below - with no
        # credential_view audit entry at all, worse than the "every
        # reveal is logged" mitigation this feature is built around.
        return jsonify({"ok": False, "error": str(exc)}), 503
    if stored is None:
        return jsonify({"ok": False, "error": "No credential stored centrally for this system"}), 404
    audit.record(_current_actor() or "unknown", "credential_view", system_id=system_id)
    resp = jsonify({
        "system_id": system_id, "rfc_user": stored["rfc_user"], "password": stored["password"],
        "updated_by": stored["updated_by"], "updated_at": stored["updated_at"],
    })
    # A revealed password must never be cached (security-reviewer, LOW).
    resp.headers["Cache-Control"] = "no-store"
    return resp


@api_bp.post("/credentials/<system_id>")
def set_credential(system_id):
    system_id = system_id.strip().upper()
    if systems_svc.get_system(system_id) is None:
        return jsonify({"ok": False, "error": "Unknown system_id - add the system first"}), 404

    data = request.get_json(silent=True) or {}
    rfc_user = (data.get("rfc_user") or "").strip()
    password = data.get("password") or ""
    actor = _current_actor() or "unknown"
    try:
        credentials.set_credential(system_id, rfc_user, password, actor)
    except (ValueError, credentials.CredentialStoreNotConfigured) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    audit.record(actor, "credential_set", system_id=system_id, params={"rfc_user": rfc_user})
    return jsonify({"ok": True, "items": [
        {"system_id": s["system_id"], "description": s["description"],
         "environment": s["environment"], "source": credentials.credential_source(s["system_id"])}
        for s in systems_svc.list_systems()
    ]})


@api_bp.delete("/credentials/<system_id>")
def delete_credential(system_id):
    system_id = system_id.strip().upper()
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to remove a stored credential"}), 400

    removed = credentials.remove_credential(system_id)
    if not removed:
        return jsonify({"ok": False, "error": "No credential stored centrally for this system"}), 404
    audit.record(_current_actor() or "unknown", "credential_remove", system_id=system_id,
                 params={"reason": reason})
    return jsonify({"ok": True})


# ---- Recurring filtered collection schedules (sal/filtered_schedule.py) ---
#
# Genuinely separate from the single baseline schedule above - any number
# of saved, independently-cadenced FILTERED pulls per system. See
# sal/filtered_schedule.py's module docstring for why this can never reuse
# schedule_settings/mode="scheduled".

def _filtered_schedule_response(cfg: dict) -> dict:
    cfg = dict(cfg)
    cfg["next_scheduled_run"] = jobs.next_filtered_schedule_run(cfg["id"])
    return cfg


@api_bp.get("/filtered-schedules")
def get_filtered_schedules():
    system_id, client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    items = [_filtered_schedule_response(cfg) for cfg in filtered_schedule.list_schedules(system_id, client)]
    return jsonify({"items": items})


@api_bp.post("/filtered-schedules")
def post_filtered_schedule():
    system_id, client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    configured_ids = {s["system_id"] for s in systems_svc.list_systems()}
    if system_id not in configured_ids:
        return jsonify({"ok": False, "error": f"Unknown system '{system_id}'"}), 400

    data = request.get_json(silent=True) or {}
    actor = _current_actor() or "unknown"
    try:
        cfg = filtered_schedule.add_schedule(
            system_id, client, (data.get("name") or "").strip(), actor,
            interval_type=(data.get("interval_type") or "").strip().lower(),
            anchor_hour=data.get("anchor_hour"), anchor_minute=data.get("anchor_minute"),
            interval_hours=data.get("interval_hours"),
            user=data.get("user"), transaction_code=data.get("transaction_code"),
            report=data.get("report"), instance=data.get("instance"), msg_code=data.get("msg_code"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    jobs.register_filtered_schedule_job(cfg["id"])
    audit.record(actor, "filtered_schedule_add", system_id=system_id, client=client,
                 params={"id": cfg["id"], "name": cfg["name"]})
    return jsonify({"item": _filtered_schedule_response(cfg)}), 201


@api_bp.patch("/filtered-schedules/<int:schedule_id>")
def patch_filtered_schedule(schedule_id):
    existing = filtered_schedule.get_schedule(schedule_id)
    if existing is None:
        return jsonify({"ok": False, "error": "Unknown schedule id"}), 404

    data = request.get_json(silent=True) or {}
    actor = _current_actor() or "unknown"
    try:
        cfg = filtered_schedule.update_schedule(
            schedule_id, actor,
            name=data.get("name"),
            interval_type=(data.get("interval_type") or "").strip().lower() or None,
            anchor_hour=data.get("anchor_hour"), anchor_minute=data.get("anchor_minute"),
            interval_hours=data.get("interval_hours"), enabled=data.get("enabled"),
            user=data.get("user"), transaction_code=data.get("transaction_code"),
            report=data.get("report"), instance=data.get("instance"), msg_code=data.get("msg_code"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # A disabled schedule must not keep firing - unregistering (rather than
    # relying on run_filtered_schedule()'s own enabled check alone) means a
    # paused schedule doesn't even attempt a submission, not just a
    # discarded one.
    if cfg["enabled"]:
        jobs.register_filtered_schedule_job(schedule_id)
    else:
        jobs.unregister_filtered_schedule_job(schedule_id)
    audit.record(actor, "filtered_schedule_update", system_id=cfg["system_id"], client=cfg.get("client"),
                 params={"id": schedule_id, "name": cfg["name"], "enabled": bool(cfg["enabled"])})
    return jsonify({"item": _filtered_schedule_response(cfg)})


@api_bp.delete("/filtered-schedules/<int:schedule_id>")
def delete_filtered_schedule(schedule_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to remove a filtered schedule"}), 400

    removed = filtered_schedule.remove_schedule(schedule_id)
    if removed is None:
        return jsonify({"ok": False, "error": "Unknown schedule id"}), 404

    jobs.unregister_filtered_schedule_job(schedule_id)
    audit.record(_current_actor() or "unknown", "filtered_schedule_remove",
                 system_id=removed["system_id"], client=removed.get("client"),
                 params={"id": schedule_id, "name": removed["name"], "reason": reason})
    return jsonify({"ok": True})


@api_bp.post("/audit-config/check")
def post_audit_config_check():
    system_id, client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    configured_ids = {s["system_id"] for s in systems_svc.list_systems()}
    if system_id not in configured_ids:
        return jsonify({"ok": False, "error": f"Unknown system '{system_id}'"}), 400
    actor = _current_actor() or "unknown"
    # Direct, synchronous, timeout-bounded call - deliberately not a
    # sal/jobs.py job (see audit_config.py's docstring / Docs/CHANGELOG.md).
    result = audit_config.check_audit_config(system_id, client, actor=actor)
    audit.record(actor, "audit_config_check", system_id=system_id, client=client,
                 params={"status": result["status"]}, outcome=result["status"])
    return jsonify(result)


@api_bp.get("/audit-config")
def get_audit_config():
    system_id, client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    snapshot = audit_config.latest_snapshot(system_id, client)
    gaps = audit_config.coverage_gaps(system_id, client)
    return jsonify({"snapshot": snapshot, "gaps": gaps})


@api_bp.get("/role-context")
def get_role_context():
    system_id, client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    return jsonify({
        "counts": role_context.role_context_counts(system_id, client),
        "latest_refresh": role_context.latest_refresh(system_id, client),
        "next_scheduled_run": jobs.next_role_context_run(system_id),
        "history": role_context.list_refresh_runs(system_id, client, limit=20),
    })


@api_bp.post("/role-context/refresh")
def post_role_context_refresh():
    system_id, _client = _scope_from_args()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    configured_ids = {s["system_id"] for s in systems_svc.list_systems()}
    if system_id not in configured_ids:
        return jsonify({"ok": False, "error": f"Unknown system '{system_id}'"}), 400
    actor = _current_actor() or "unknown"
    # Direct, synchronous call - deliberately not a sal/jobs.py job (see
    # role_context.py's docstring), matching the audit-config check and
    # retention purge precedent for dateless/bulk operations.
    result = role_context.sync_role_context(system_id, actor=actor)
    audit.record(actor, "role_context_refresh", system_id=system_id, client=result.get("client"),
                 params={"status": result["status"]}, outcome=result["status"])
    return jsonify(result)


@api_bp.get("/role-context/user")
def get_role_context_user():
    """One user's full access picture: PFCG roles/role-menu tcodes (local,
    already bulk-synced) plus a live, on-demand lookup of profiles assigned
    directly to their user master record - see role_context.py's docstring
    ("Directly-assigned profiles") for why the latter can't be bulk-synced
    the same way and is fetched fresh on every call instead.
    """
    system_id, client = _scope_from_args()
    user_id = (request.args.get("user_id") or "").strip()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    if not user_id:
        return jsonify({"ok": False, "error": "user_id is required"}), 400
    configured_ids = {s["system_id"] for s in systems_svc.list_systems()}
    if system_id not in configured_ids:
        return jsonify({"ok": False, "error": f"Unknown system '{system_id}'"}), 400
    summary = role_context.user_access_summary(system_id, client, user_id)
    audit.record(_current_actor() or "unknown", "role_context_user_lookup",
                 system_id=system_id, client=client, params={"user_id": user_id},
                 outcome="ok" if summary["profiles_error"] is None else "error")
    return jsonify(summary)


@api_bp.get("/retention")
def get_retention():
    preview = retention.preview_purge()
    history = retention.list_purge_runs(limit=50)
    return jsonify({
        "policy": preview,
        "next_scheduled_run": jobs.next_retention_run(),
        "history": history,
    })


@api_bp.post("/retention/purge-now")
def post_retention_purge_now():
    actor = _current_actor() or "unknown"
    result = retention.run_purge(actor=actor)
    audit.record(actor, "retention_purge", params={
        "events_deleted": result["events_deleted"], "findings_deleted": result["findings_deleted"],
    }, result_count=result["events_deleted"] + result["findings_deleted"])
    return jsonify({"ok": True, "result": result})


@api_bp.get("/rules")
def rules():
    return jsonify({"rules": [{"key": key, "label": label} for key, label, _fn in RULES]})


@api_bp.get("/rules/export")
def rules_export():
    audit.record(_current_actor() or "unknown", "rules_catalog_export")
    data = rules_catalog.build_rules_catalog_workbook()
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sal_detection_rules.xlsx"},
    )


@api_bp.get("/dashboard")
def dashboard():
    # Critical-transaction/sensitive-table defaults are seeded once at
    # process startup (see create_app()), not per-request - they're static
    # after first insert, and re-seeding here on every dashboard load used
    # to be a measurable, compounding cost.
    system_id, client = _scope_from_args()

    _total, findings = findings_svc.list_findings(limit=100000, system_id=system_id, client=client)
    severity_counts = _severity_counts(findings)

    counts_by_rule = {}
    for f in findings:
        counts_by_rule[f["rule_key"]] = counts_by_rule.get(f["rule_key"], 0) + 1
    by_rule = [
        {"key": key, "label": label, "count": counts_by_rule.get(key, 0)}
        for key, label, _fn in RULES
    ]

    recent_high = [f for f in findings if f["severity"] == "High"][:10]

    conn = get_connection()
    try:
        clauses, params = [], []
        if system_id:
            clauses.append("source_system = ?")
            params.append(system_id)
        if client:
            clauses.append("client = ?")
            params.append(client)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        event_count = conn.execute(
            f"SELECT COUNT(*) c FROM events {where}", params
        ).fetchone()["c"]

        # Own clause (not appended to the shared `clauses` above) since
        # `events` has no deleted_at column - a soft-deleted run must not
        # surface here as the dashboard's headline "last collection"
        # (found in review: the point of soft-deleting a run is to hide
        # it, and this query previously ignored that entirely).
        last_run_where = f"{where} AND deleted_at IS NULL" if where else "WHERE deleted_at IS NULL"
        last_run_row = conn.execute(
            f"SELECT * FROM collection_runs {last_run_where} ORDER BY started_at DESC LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()

    open_findings = [f for f in findings if f["status"] == "open"]
    sla_buckets = {sev: {"on_track": 0, "at_risk": 0, "breached": 0} for sev in sla.SLA_BUSINESS_DAYS}
    overdue = []
    for f in open_findings:
        result = sla.classify(f["severity"], f["first_seen_at"])
        bucket = result["bucket"]
        if f["severity"] in sla_buckets and bucket in sla_buckets[f["severity"]]:
            sla_buckets[f["severity"]][bucket] += 1
        if bucket == "breached":
            overdue.append({
                "finding_key": f["finding_key"], "rule_label": f["rule_label"],
                "severity": f["severity"], "user_id": f["user_id"],
                "summary": f["summary"], "first_seen_at": f["first_seen_at"],
                "business_days_open": result["business_days_open"],
                "threshold_days": result["threshold_days"],
            })
    overdue.sort(key=lambda item: item["business_days_open"], reverse=True)

    audit.record(_current_actor() or "unknown", "view_dashboard",
                 system_id=system_id, client=client, result_count=len(findings))

    return jsonify({
        "totals": {
            "total": len(findings),
            "high": severity_counts["High"],
            "medium": severity_counts["Medium"],
            "low": severity_counts["Low"],
        },
        "by_rule": by_rule,
        "recent_high": recent_high,
        "event_count": event_count,
        "last_run": dict(last_run_row) if last_run_row else None,
        "critical_transaction_count": len(list_critical_transactions()),
        "sensitive_table_count": len(list_sensitive_tables()),
        "sla": {"buckets": sla_buckets, "most_overdue": overdue[:10]},
    })


@api_bp.get("/findings")
def findings_list():
    system_id, client = _scope_from_args()
    # getlist(): the Findings table's Excel-style column-header filters send
    # one query-string entry per checked value for the enum columns
    # (Rule/Severity/Status); User is a separate free-text contains filter.
    rule_filter = _multi_arg("rule")
    severity_filter = _multi_arg("severity")
    status_filter = _multi_arg("status")
    user_filter = request.args.get("user_id", "").strip() or None
    finding_key_filter = request.args.get("finding_key", "").strip() or None
    limit = min(int(request.args.get("limit", 200) or 200), 500)
    offset = max(int(request.args.get("offset", 0) or 0), 0)

    total, items = findings_svc.list_findings(
        limit=limit, offset=offset,
        rule=rule_filter, severity=severity_filter,
        status=status_filter, system_id=system_id, client=client, user_id=user_filter,
        finding_key=finding_key_filter,
    )

    audit.record(_current_actor() or "unknown", "findings_search",
                 system_id=system_id, client=client,
                 params={"rule": rule_filter, "severity": severity_filter,
                         "status": status_filter, "user_id": user_filter},
                 result_count=total)

    return jsonify({"total": total, "items": items})


@api_bp.get("/findings/export")
def findings_export():
    system_id, client = _scope_from_args()
    rule_filter = _multi_arg("rule")
    severity_filter = _multi_arg("severity")
    status_filter = _multi_arg("status")
    user_filter = request.args.get("user_id", "").strip() or None
    fmt = (request.args.get("format") or "csv").strip().lower()

    # No pagination here, unlike the paginated /findings list - an export is
    # meant to be the full matching set for a report, not one page of it.
    _total, items = findings_svc.list_findings(
        limit=100000,
        rule=rule_filter, severity=severity_filter,
        status=status_filter, system_id=system_id, client=client, user_id=user_filter,
    )
    rows = [export.flatten_finding(f) for f in items]

    audit.record(_current_actor() or "unknown", "findings_export",
                 system_id=system_id, client=client,
                 params={"format": fmt, "rule": rule_filter,
                         "severity": severity_filter, "status": status_filter, "user_id": user_filter},
                 result_count=len(rows))

    if fmt == "itgc":
        conn = get_connection()
        try:
            cr_clauses, cr_params = [], []
            if system_id:
                cr_clauses.append("source_system = ?")
                cr_params.append(system_id)
            if client:
                cr_clauses.append("client = ?")
                cr_params.append(client)
            # Same soft-delete exclusion as collection_runs_export() above -
            # a deleted run's metadata shouldn't resurface in an official
            # ITGC compliance workbook either.
            cr_clauses.append("deleted_at IS NULL")
            cr_where = f"WHERE {' AND '.join(cr_clauses)}" if cr_clauses else ""
            collection_runs = [dict(r) for r in conn.execute(
                f"SELECT * FROM collection_runs {cr_where} ORDER BY started_at DESC", cr_params,
            ).fetchall()]
        finally:
            conn.close()
        system_meta = systems_svc.get_system(system_id) if system_id else None
        data = itgc_report.build_itgc_workbook(
            items, collection_runs,
            system_id=system_id, client=client,
            environment=(system_meta or {}).get("environment"),
            generated_by=_current_actor() or "unknown",
        )
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sal_findings_itgc.xlsx"},
        )
    if fmt == "xlsx":
        data = export.rows_to_xlsx(export.FINDINGS_HEADERS, rows, sheet_title="Findings")
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sal_findings.xlsx"},
        )
    return Response(
        export.rows_to_csv(export.FINDINGS_HEADERS, rows),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sal_findings.csv"},
    )


@api_bp.post("/findings/sync")
def findings_sync():
    system_id, client = _scope_from_args()
    result = findings_svc.sync_findings(system_id=system_id, client=client)
    audit.record(_current_actor() or "unknown", "findings_sync",
                 system_id=system_id, client=client, result_count=result["new"])
    return jsonify(result)


@api_bp.post("/findings/<finding_key>/dispose")
def findings_dispose(finding_key):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in findings_svc.OPEN_STATUSES:
        return jsonify({"ok": False, "error": f"status must be one of {findings_svc.OPEN_STATUSES}"}), 400

    actor = _current_actor() or "unknown"
    reason_code = (data.get("reason_code") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None

    # Looked up before disposing so the audit row can carry the finding's
    # own scope - same gap, same fix, as delete_whitelist() above (a
    # python-reviewer pass on this round's other audit-scope fixes caught
    # that finding_dispose was the one significant auditor-facing action
    # left unscoped: true_positive/false_positive/whitelisted calls on a
    # still-selectable system+client would never show up in that system's
    # default-scoped Activity view).
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT source_system, client FROM findings WHERE finding_key = ?", (finding_key,)
        ).fetchone()
    finally:
        conn.close()

    found = findings_svc.dispose_finding(finding_key, status, actor, reason_code, notes)
    if not found:
        return jsonify({"ok": False, "error": "Unknown finding_key"}), 404

    audit.record(actor, "finding_dispose",
                 system_id=row["source_system"] if row else None,
                 client=row["client"] if row else None,
                 params={"finding_key": finding_key, "status": status, "reason_code": reason_code})
    return jsonify({"ok": True})


@api_bp.get("/whitelist")
def get_whitelist():
    return jsonify({"items": findings_svc.list_whitelist()})


@api_bp.post("/whitelist")
def post_whitelist():
    data = request.get_json(silent=True) or {}
    rule_key = (data.get("rule_key") or "").strip()
    reason = (data.get("reason") or "").strip()
    expires_at = (data.get("expires_at") or "").strip()
    if not rule_key or not reason or not expires_at:
        return jsonify({"ok": False, "error": "rule_key, reason and expires_at are required"}), 400

    actor = _current_actor() or "unknown"
    scope_system_id = (data.get("system_id") or "").strip().upper() or None
    scope_client = (data.get("client") or "").strip() or None
    entry_id = findings_svc.add_whitelist(
        rule_key=rule_key, reason=reason, created_by=actor, expires_at=expires_at,
        system_id=scope_system_id, client=scope_client,
        user_id=(data.get("user_id") or "").strip() or None,
    )
    # system_id/client included - found in UAT round 2: an audit row with
    # neither never matches the Activity page's default (system_id AND
    # client) scope filter, so this action silently never appeared there
    # even though it was being recorded (same gap as whitelist_remove below).
    audit.record(actor, "whitelist_add", system_id=scope_system_id, client=scope_client,
                 params={"rule_key": rule_key, "reason": reason, "expires_at": expires_at})
    return jsonify({"ok": True, "id": entry_id, "items": findings_svc.list_whitelist()})


@api_bp.delete("/whitelist/<int:entry_id>")
def delete_whitelist(entry_id):
    # Reason required, matching every other soft-delete/restore action in
    # this app (jobs, runs) - found in UAT: removing a whitelist entry
    # (which stops it suppressing matching findings) had no such
    # requirement, unlike adding one, which already requires a reason.
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to remove a whitelist entry"}), 400

    # Looked up before deleting so the audit row can carry the entry's own
    # scope - found in UAT round 2: recorded with neither system_id nor
    # client, this action's row never matched the Activity page's default
    # (system_id AND client) scope filter, so it silently never appeared
    # there even though it was being recorded (a critical, auditor-facing
    # action - this was flagged directly as a real concern, not cosmetic).
    conn = get_connection()
    try:
        entry = conn.execute(
            "SELECT source_system, client FROM finding_whitelist WHERE id = ?", (entry_id,)
        ).fetchone()
    finally:
        conn.close()

    findings_svc.remove_whitelist(entry_id)
    audit.record(_current_actor() or "unknown", "whitelist_remove",
                 system_id=entry["source_system"] if entry else None,
                 client=entry["client"] if entry else None,
                 params={"id": entry_id, "reason": reason})
    return jsonify({"ok": True, "items": findings_svc.list_whitelist()})


@api_bp.post("/connection-test")
def connection_test():
    data = request.get_json(silent=True) or {}
    system_id = (data.get("system_id") or "").strip().upper()
    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400

    # Looked up so the audit row can carry a client, not just system_id -
    # found in UAT round 2: without it, this action's row never matches the
    # Activity page's default (system_id AND client) scope filter, and so
    # silently never appeared there even though it was being recorded.
    system = systems_svc.get_system(system_id)
    client = system["client"] if system else None
    actor = _current_actor() or "unknown"
    try:
        with SapConnection(system_id) as conn:
            conn.ping()
            info = conn.call("RFC_SYSTEM_INFO")["RFCSI_EXPORT"]
            audit.record(actor, "connection_test", system_id=system_id, client=client, outcome="ok")
            return jsonify({
                "ok": True,
                "result": {
                    "system_id": info["RFCSYSID"],
                    "sap_release": info["RFCSAPRL"],
                    "host": info["RFCHOST"],
                    "db_host": info["RFCDBHOST"],
                    "os": info["RFCOPSYS"],
                },
            })
    except SapConnectionError as exc:
        # Must come before the bare RuntimeError catch below:
        # SapConnectionError subclasses RuntimeError (sal/sap_connector/
        # connection.py), so a live RFC failure - bad host, ping failure,
        # etc., with perfectly fine credentials - would otherwise be
        # caught by that broader clause first and misreported as
        # "credentials not maintained" (caught in review before shipping).
        audit.record(actor, "connection_test", system_id=system_id, client=client, outcome="error")
        return jsonify({"ok": False, "error": str(exc)})
    except RuntimeError as exc:
        # config.sap_system_config() raises this specifically when the
        # required SAL_SAP_<ID>_* env vars aren't set - reached from
        # SapConnection.__init__(), before __enter__()'s own try/except
        # (which only wraps the live RFC call) ever runs, so it needs its
        # own catch here or it escapes uncaught as an unhandled 500 (found
        # in UAT: a system with unmaintained credentials just "didn't
        # work," with no actionable message, instead of a clean error).
        audit.record(actor, "connection_test", system_id=system_id, client=client, outcome="error")
        return jsonify({
            "ok": False,
            "error": f"Credentials not maintained for system '{system_id}'. {exc} Set them in .env and test again.",
        })


@api_bp.post("/collect")
def collect():
    data = request.get_json(silent=True) or {}
    system_id = (data.get("system_id") or "").strip().upper()
    client = (data.get("client") or "").strip() or None
    dat_from = (data.get("dat_from") or "").strip()
    dat_to = (data.get("dat_to") or "").strip()
    tim_from = (data.get("tim_from") or "000000").strip() or "000000"
    tim_to = (data.get("tim_to") or "235959").strip() or "235959"

    if not system_id:
        return jsonify({"ok": False, "error": "System is required"}), 400
    configured_ids = {s["system_id"] for s in systems_svc.list_systems()}
    if system_id not in configured_ids:
        return jsonify({"ok": False, "error": f"Unknown system '{system_id}'"}), 400
    if not _DATE_RE.match(dat_from) or not _DATE_RE.match(dat_to):
        return jsonify({"ok": False, "error": "Date from/to must be in YYYYMMDD form"}), 400
    if not _TIME_RE.match(tim_from) or not _TIME_RE.match(tim_to):
        return jsonify({"ok": False, "error": "Time from/to must be in HHMMSS form"}), 400
    job_class = (data.get("job_class") or "B").strip().upper()
    if job_class not in jobs.JOB_CLASSES:
        return jsonify({"ok": False, "error": "job_class must be one of A, B, C"}), 400

    actor = _current_actor() or "unknown"
    # Phase B: submitted as a job (retried as one whole-range call, synced
    # once at the end - see sal/jobs.py's module docstring for why ad-hoc
    # jobs run as a single collect_and_store() call rather than the
    # day-chunked path scheduled jobs still use) rather than run
    # synchronously in this request, so a wide date range can't block or
    # time out the HTTP call. The UI polls GET /api/jobs/<id> for status
    # instead of getting one blocking response.
    job_name = (data.get("job_name") or "").strip() or None
    job_description = (data.get("job_description") or "").strip() or None

    job_id = jobs.submit_job(
        system_id=system_id, client=client, dat_from=dat_from, dat_to=dat_to,
        mode="adhoc", triggered_by=actor, tim_from=tim_from, tim_to=tim_to,
        user=data.get("user"), transaction_code=data.get("transaction_code"),
        report=data.get("report"), instance=data.get("instance"),
        msg_code=data.get("msg_code"),
        job_name=job_name, job_description=job_description, job_class=job_class,
    )
    audit.record(
        actor, "collect", system_id=system_id, client=client,
        params={
            "dat_from": dat_from, "dat_to": dat_to,
            "tim_from": tim_from, "tim_to": tim_to,
            "user": data.get("user"), "transaction_code": data.get("transaction_code"),
            "report": data.get("report"), "instance": data.get("instance"),
            "msg_code": data.get("msg_code"), "job_class": job_class,
            "job_name": job_name,
        },
        outcome="submitted",
    )

    return jsonify({"ok": True, "job_id": job_id, "status": "queued"}), 202


def _enrich_job(job: dict) -> dict:
    job = dict(job)
    # Additive, analyst-facing companion to the raw error_message (see
    # sal/friendly_errors.py) - None for a job with no error, or one whose
    # error doesn't match a known SAP error key. Never replaces the raw
    # message, which engineers/admins still need.
    job["error_message_friendly"] = friendly_errors.friendly_error(job.get("error_message"))
    job["eta_seconds"] = jobs.estimate_eta_seconds(job)
    job["next_scheduled_run"] = jobs.next_scheduled_run(job["system_id"])
    # Frequency this job's system is *currently* configured for (Slice B) -
    # not a per-job historical snapshot (schedule_settings holds one current
    # row per system, not per-job history), same simplification
    # next_scheduled_run above already makes. Only meaningful for
    # mode='scheduled' - an ad-hoc job was a one-time pull, not governed by
    # any recurring cadence.
    if job["mode"] == "scheduled":
        cfg = schedule.get_schedule(job["system_id"])
        job["schedule_interval_type"] = cfg["interval_type"]
        job["schedule_anchor_hour"] = cfg["anchor_hour"]
        job["schedule_anchor_minute"] = cfg["anchor_minute"]
        job["schedule_interval_hours"] = cfg["interval_hours"]
    else:
        job["schedule_interval_type"] = None
        job["schedule_anchor_hour"] = None
        job["schedule_anchor_minute"] = None
        job["schedule_interval_hours"] = None
    return job


@api_bp.get("/jobs/<int:job_id>")
def get_job(job_id):
    job = jobs.get_job(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"item": _enrich_job(job)})


@api_bp.get("/jobs")
def list_jobs():
    system_id, client = _scope_from_args()
    view = (request.args.get("view") or "").strip().lower()
    job_name = request.args.get("job_name", "").strip() or None
    # getlist(), not get(): the Excel-style column-header filters (Jobs/
    # Recovery tables) send one query-string entry per checked value
    # (?mode=scheduled&mode=adhoc) when more than one is checked -
    # jobs.list_jobs() treats an empty list the same as "no filter".
    mode = _multi_arg("mode")
    status = _multi_arg("status")
    job_class = [v.upper() for v in _multi_arg("job_class")]
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    if job_class and not set(job_class) <= set(jobs.JOB_CLASSES):
        return jsonify({"ok": False, "error": "job_class must be one of A, B, C"}), 400
    if date_from and not _ISO_DATE_RE.match(date_from):
        return jsonify({"ok": False, "error": "date_from must be in YYYY-MM-DD form"}), 400
    if date_to and not _ISO_DATE_RE.match(date_to):
        return jsonify({"ok": False, "error": "date_to must be in YYYY-MM-DD form"}), 400
    try:
        limit = min(int(request.args.get("limit", 20) or 20), 200)
        offset = max(int(request.args.get("offset", 0) or 0), 0)
    except ValueError:
        return jsonify({"ok": False, "error": "limit/offset must be integers"}), 400

    try:
        total, rows = jobs.list_jobs(system_id=system_id, client=client, limit=limit, offset=offset,
                                      job_name=job_name, mode=mode, status=status, job_class=job_class,
                                      date_from=date_from or None, date_to=date_to or None,
                                      view="deleted" if view == "deleted" else "active")
    except ValueError:
        # date_to matched _ISO_DATE_RE's shape but isn't a real calendar
        # date (e.g. "2026-02-30") - jobs.list_jobs() raises rather than
        # silently dropping the filter (found in review).
        return jsonify({"ok": False, "error": "date_to is not a valid date"}), 400
    items = [_enrich_job(j) for j in rows]
    return jsonify({"items": items, "total": total})


@api_bp.delete("/jobs/<int:job_id>")
def delete_job(job_id):
    """Soft-delete only, mirroring delete_collection_run()'s reasoning
    exactly: this hides the collection_jobs submission/tracking row, never
    the events/findings it helped collect, nor the collection_runs rows it
    produced (those keep their own independent soft-delete lifecycle -
    see sal/storage/db.py's schema comment). Requires a reason and refuses
    a queued/running job - the worker thread still needs that row intact
    while it's actively claimed.
    """
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to delete a job"}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM collection_jobs WHERE id = ? AND deleted_at IS NULL", (job_id,)
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "Job not found"}), 404
        if row["status"] in ("queued", "running"):
            return jsonify({"ok": False, "error": "Cannot delete a job that is still in progress"}), 409

        actor = _current_actor() or "unknown"
        conn.execute(
            "UPDATE collection_jobs SET deleted_at = ?, deleted_by = ?, delete_reason = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), actor, reason, job_id),
        )
        conn.commit()
        audit.record(actor, "job_delete", system_id=row["system_id"], client=row["client"],
                     params={"job_id": job_id, "job_name": row["job_name"], "reason": reason})
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.post("/jobs/<int:job_id>/restore")
def restore_job(job_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to restore a job"}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM collection_jobs WHERE id = ? AND deleted_at IS NOT NULL", (job_id,)
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "Deleted job not found"}), 404

        actor = _current_actor() or "unknown"
        conn.execute(
            "UPDATE collection_jobs SET deleted_at = NULL, deleted_by = NULL, delete_reason = NULL "
            "WHERE id = ?",
            (job_id,),
        )
        conn.commit()
        audit.record(actor, "job_restore", system_id=row["system_id"], client=row["client"],
                     params={"job_id": job_id, "job_name": row["job_name"], "reason": reason})
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.get("/collection-runs")
def collection_runs():
    system_id, client = _scope_from_args()
    # "view=deleted" flips this from the default active-only history list to
    # the restore picker's list of soft-deleted runs - see delete_collection_run
    # / restore_collection_run below for why this is soft-delete, not DELETE.
    view = (request.args.get("view") or "").strip().lower()
    job_id_raw = request.args.get("job_id", "").strip()
    job_name = request.args.get("job_name", "").strip() or None
    # getlist(): the Excel-style column-header filters (Recovery's "Deleted
    # collection runs" panel) send one query-string entry per checked value.
    mode = _multi_arg("mode")
    status = _multi_arg("status")
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    try:
        job_id = int(job_id_raw) if job_id_raw else None
    except ValueError:
        return jsonify({"ok": False, "error": "job_id must be an integer"}), 400
    if date_from and not _ISO_DATE_RE.match(date_from):
        return jsonify({"ok": False, "error": "date_from must be in YYYY-MM-DD form"}), 400
    if date_to and not _ISO_DATE_RE.match(date_to):
        return jsonify({"ok": False, "error": "date_to must be in YYYY-MM-DD form"}), 400
    try:
        limit = min(int(request.args.get("limit", 20) or 20), 200)
        offset = max(int(request.args.get("offset", 0) or 0), 0)
    except ValueError:
        return jsonify({"ok": False, "error": "limit/offset must be integers"}), 400

    conn = get_connection()
    try:
        clauses, params = [], []
        if system_id:
            clauses.append("cr.source_system = ?")
            params.append(system_id)
        if client:
            clauses.append("cr.client = ?")
            params.append(client)
        clauses.append("cr.deleted_at IS NOT NULL" if view == "deleted" else "cr.deleted_at IS NULL")
        if job_id is not None:
            clauses.append("cr.job_id = ?")
            params.append(job_id)
        if job_name:
            clauses.append("(cj.job_name LIKE ? OR cj.job_description LIKE ?)")
            params.extend([f"%{job_name}%", f"%{job_name}%"])
        if mode:
            clauses.append(f"cj.mode IN ({', '.join('?' for _ in mode)})")
            params.extend(mode)
        if status:
            clauses.append(f"cr.status IN ({', '.join('?' for _ in status)})")
            params.extend(status)
        # started_at is written as datetime.now(timezone.utc).isoformat()
        # ("...T...+00:00" - see sal/collectors/sm20.py) and compared here
        # as a plain lexical string range, not via SQLite's date()/time()
        # parsing (which only learned to understand a "+00:00" offset
        # suffix in SQLite 3.42) - the same approach sal/retention.py's own
        # cutoffs use, and for the same reason: date() silently returning
        # NULL on an older SQLite build would make this filter silently
        # match nothing rather than error - the exact "looked right,
        # returned zero rows" failure class this project has been burned
        # by before (see CLAUDE.md).
        if date_from:
            clauses.append("cr.started_at >= ?")
            params.append(f"{date_from}T00:00:00")
        if date_to:
            try:
                next_day = date.fromisoformat(date_to) + timedelta(days=1)
            except ValueError:
                return jsonify({"ok": False, "error": "date_to is not a valid date"}), 400
            clauses.append("cr.started_at < ?")
            params.append(f"{next_day.isoformat()}T00:00:00")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # LEFT JOIN (not INNER) since collection_runs.job_id is NULL for
        # any run predating that column or from scripts/collect_sm20.py's
        # CLI backfill path (bypasses sal/jobs.py entirely) - those runs
        # must still appear, just with no job_name/job_description/job_mode.
        # collection_jobs has its own "client" column (a different concept
        # - the job's own submitted scope, not this row's) - "cr."/"cj."
        # prefixes throughout avoid it silently shadowing collection_runs'.
        from_sql = "FROM collection_runs cr LEFT JOIN collection_jobs cj ON cr.job_id = cj.id " + where
        total = conn.execute(f"SELECT COUNT(*) AS c {from_sql}", params).fetchone()["c"]
        # run_number counts up from #1 within whatever this call's own
        # filters/scope resolve to (not the whole table's history) - a
        # stable "run #N of however many total *for this view*" label that
        # doesn't shift as new runs are added, computed before the outer
        # ORDER BY/LIMIT trims to one page.
        rows = conn.execute(
            "SELECT cr.*, ROW_NUMBER() OVER (ORDER BY cr.started_at ASC) AS run_number, "
            "cj.job_name AS job_name, cj.job_description AS job_description, cj.mode AS job_mode "
            f"{from_sql} ORDER BY cr.started_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            # Same additive companion field as _enrich_job() above - see
            # sal/friendly_errors.py.
            item["error_message_friendly"] = friendly_errors.friendly_error(item.get("error_message"))
            items.append(item)
        return jsonify({"items": items, "total": total})
    finally:
        conn.close()


@api_bp.delete("/collection-runs/<run_id>")
def delete_collection_run(run_id):
    """Soft-delete only - see sal/storage/db.py's schema comment on why a
    collection_runs row is safe to hide/restore without ever touching the
    events/findings it helped collect. Requires a reason (auditor-facing
    tool - every removal from the history list must be justified and
    attributable), and refuses to hide a run that's still in progress,
    checking not just this row's own status but every sibling run under the
    same job_id and the parent job itself - a wide job chunks into one
    collection_runs row per day, so a finished day-3 row can coexist with a
    still-running day-5 row under the same job.
    """
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to delete a collection run"}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM collection_runs WHERE run_id = ? AND deleted_at IS NULL", (run_id,)
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "Collection run not found"}), 404
        if row["status"] == "running":
            return jsonify({"ok": False, "error": "Cannot delete a run that is still in progress"}), 409
        if row["job_id"] is not None:
            job = conn.execute(
                "SELECT status FROM collection_jobs WHERE id = ?", (row["job_id"],)
            ).fetchone()
            if job is not None and job["status"] in ("queued", "running"):
                return jsonify({"ok": False,
                                "error": "Cannot delete: this run's job is still in progress"}), 409
            sibling_running = conn.execute(
                "SELECT 1 FROM collection_runs WHERE job_id = ? AND run_id != ? AND status = 'running'",
                (row["job_id"], run_id),
            ).fetchone()
            if sibling_running is not None:
                return jsonify({"ok": False,
                                "error": "Cannot delete: another day in this same job is still running"}), 409

        actor = _current_actor() or "unknown"
        conn.execute(
            "UPDATE collection_runs SET deleted_at = ?, deleted_by = ?, delete_reason = ? WHERE run_id = ?",
            (datetime.now(timezone.utc).isoformat(), actor, reason, run_id),
        )
        conn.commit()
        audit.record(actor, "collection_run_delete", system_id=row["source_system"], client=row["client"],
                     params={"run_id": run_id, "job_id": row["job_id"], "reason": reason})
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.post("/collection-runs/<run_id>/restore")
def restore_collection_run(run_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "A reason is required to restore a collection run"}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM collection_runs WHERE run_id = ? AND deleted_at IS NOT NULL", (run_id,)
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "Deleted collection run not found"}), 404

        actor = _current_actor() or "unknown"
        conn.execute(
            "UPDATE collection_runs SET deleted_at = NULL, deleted_by = NULL, delete_reason = NULL "
            "WHERE run_id = ?",
            (run_id,),
        )
        conn.commit()
        audit.record(actor, "collection_run_restore", system_id=row["source_system"], client=row["client"],
                     params={"run_id": run_id, "job_id": row["job_id"], "reason": reason})
        return jsonify({"ok": True})
    finally:
        conn.close()


@api_bp.get("/collection-runs/export")
def collection_runs_export():
    system_id, client = _scope_from_args()
    fmt = (request.args.get("format") or "csv").strip().lower()

    conn = get_connection()
    try:
        clauses, params = [], []
        if system_id:
            clauses.append("source_system = ?")
            params.append(system_id)
        if client:
            clauses.append("client = ?")
            params.append(client)
        # Soft-deleted runs are excluded here too (found in review) - the
        # whole point of deleting one is to hide it, and an export that
        # silently included it anyway (indistinguishable from an active
        # run, since these columns aren't even in COLLECTION_RUNS_HEADERS)
        # would defeat that. Deliberately not offering an "include deleted"
        # toggle here - view=deleted on the paginated endpoint above is
        # already where a deleted run's metadata/reason is inspectable.
        clauses.append("deleted_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # No LIMIT here (unlike the paginated view above) - an export should
        # be the full collection history, not just the 20 most recent runs.
        rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM collection_runs {where} ORDER BY started_at DESC", params,
        ).fetchall()]
    finally:
        conn.close()

    audit.record(_current_actor() or "unknown", "collection_runs_export",
                 system_id=system_id, client=client, params={"format": fmt},
                 result_count=len(rows))

    if fmt == "xlsx":
        data = export.rows_to_xlsx(export.COLLECTION_RUNS_HEADERS, rows, sheet_title="Collection Runs")
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sal_collection_runs.xlsx"},
        )
    return Response(
        export.rows_to_csv(export.COLLECTION_RUNS_HEADERS, rows),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sal_collection_runs.csv"},
    )


# SQLite has its own ceiling on bound parameters per statement
# (SQLITE_MAX_VARIABLE_NUMBER); a pathologically long comma-separated
# filter would otherwise raise an uncaught sqlite3.OperationalError deep
# inside events_export()'s query - and since run.py always runs Flask
# with debug=True, that surfaces Werkzeug's interactive debugger rather
# than a clean 400. Reject oversized lists explicitly instead.
_MAX_MULTI_FILTER_VALUES = 500


def _split_multi(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@api_bp.get("/events/export")
def events_export():
    """Raw SM20 events already collected into this app's own database,
    filtered by the same selection fields the Collect form's "Fetch from
    SAP" submits (sal/collectors/sm20.py's fetch_events()) - a query
    against local data, not a fresh RFC call, so an analyst can download
    "the data behind this ad-hoc run" (or any prior date range) without
    re-hitting SAP. Deliberately not scoped to a specific collection_run_id
    or job: an ad-hoc job runs its whole range as one collect_and_store()
    call (sal/jobs.py), but a failed-then-retried attempt still gets a
    fresh run_id per attempt, and a scheduled job still chunks by day into
    many more - re-querying by the same filters the user actually asked
    for is more robust than reconstructing "which run_id(s) count" for
    either shape after the fact.
    """
    system_id, client = _scope_from_args()
    fmt = (request.args.get("format") or "csv").strip().lower()
    dat_from = (request.args.get("dat_from") or "").strip()
    dat_to = (request.args.get("dat_to") or "").strip()
    tim_from = (request.args.get("tim_from") or "000000").strip() or "000000"
    tim_to = (request.args.get("tim_to") or "235959").strip() or "235959"

    if not system_id:
        return jsonify({"ok": False, "error": "system_id is required"}), 400
    if not _DATE_RE.match(dat_from) or not _DATE_RE.match(dat_to):
        return jsonify({"ok": False, "error": "Date from/to must be in YYYYMMDD form"}), 400
    if not _TIME_RE.match(tim_from) or not _TIME_RE.match(tim_to):
        return jsonify({"ok": False, "error": "Time from/to must be in HHMMSS form"}), 400

    # dat_from/tim_from are the same YYYYMMDD/HHMMSS shape as SAP's own
    # SAL_DATE/SAL_TIME, so the same conversion sal/collectors/sm20.py uses
    # to populate events.event_timestamp on write also builds matching
    # query bounds here, rather than a second copy of the slicing.
    ts_from = event_timestamp(dat_from, tim_from)
    ts_to = event_timestamp(dat_to, tim_to)

    clauses = ["source_system = ?", "event_timestamp BETWEEN ? AND ?"]
    params = [system_id, ts_from, ts_to]
    multi_filters = {}
    if client:
        clauses.append("client = ?")
        params.append(client)
    for arg_name, column in (
        ("user", "user_id"), ("transaction_code", "transaction_code"),
        ("report", "program"), ("instance", "instance"), ("msg_code", "msg_code"),
    ):
        values = _split_multi(request.args.get(arg_name))
        if len(values) > _MAX_MULTI_FILTER_VALUES:
            return jsonify({
                "ok": False,
                "error": f"Too many values for '{arg_name}' (max {_MAX_MULTI_FILTER_VALUES})",
            }), 400
        if values:
            multi_filters[arg_name] = values
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)
    where = " AND ".join(clauses)

    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM events WHERE {where} ORDER BY event_timestamp", params,
        ).fetchall()]
    finally:
        conn.close()

    audit.record(_current_actor() or "unknown", "events_export",
                 system_id=system_id, client=client,
                 params={"dat_from": dat_from, "dat_to": dat_to, "format": fmt, **multi_filters},
                 result_count=len(rows))

    if fmt == "itgc":
        system_meta = systems_svc.get_system(system_id) if system_id else None
        data = itgc_events_report.build_events_workbook(
            rows, system_id=system_id, client=client, dat_from=dat_from, dat_to=dat_to,
            filters={**multi_filters, "tim_from": tim_from, "tim_to": tim_to},
            environment=(system_meta or {}).get("environment"),
            generated_by=_current_actor() or "unknown",
        )
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sal_events_itgc.xlsx"},
        )
    if fmt == "xlsx":
        data = export.rows_to_xlsx(export.EVENTS_HEADERS, rows, sheet_title="Events")
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=sal_events.xlsx"},
        )
    return Response(
        export.rows_to_csv(export.EVENTS_HEADERS, rows),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sal_events.csv"},
    )


@api_bp.get("/catalogues/critical-transactions")
def get_critical_transactions():
    # Defaults are seeded once at process startup (see create_app()), not
    # per-request - see dashboard()'s comment above for why.
    return jsonify({"items": list_critical_transactions_detailed()})


@api_bp.post("/catalogues/critical-transactions")
def post_critical_transaction():
    data = request.get_json(silent=True) or {}
    tcode = (data.get("transaction_code") or "").strip()
    if not tcode:
        return jsonify({"ok": False, "error": "Transaction code is required"}), 400
    add_critical_transaction(tcode, (data.get("description") or "").strip(), added_by="ui")
    audit.record(_current_actor() or "unknown", "catalogue_add",
                 params={"catalogue": "critical-transactions", "code": tcode})
    return jsonify({"ok": True, "items": list_critical_transactions_detailed()})


@api_bp.delete("/catalogues/critical-transactions/<tcode>")
def delete_critical_transaction(tcode):
    remove_critical_transaction(tcode)
    audit.record(_current_actor() or "unknown", "catalogue_remove",
                 params={"catalogue": "critical-transactions", "code": tcode})
    return jsonify({"ok": True, "items": list_critical_transactions_detailed()})


@api_bp.get("/catalogues/sensitive-tables")
def get_sensitive_tables():
    # Defaults are seeded once at process startup (see create_app()), not
    # per-request - see dashboard()'s comment above for why.
    return jsonify({"items": list_sensitive_tables_detailed()})


@api_bp.post("/catalogues/sensitive-tables")
def post_sensitive_table():
    data = request.get_json(silent=True) or {}
    table_name = (data.get("table_name") or "").strip()
    if not table_name:
        return jsonify({"ok": False, "error": "Table name is required"}), 400
    add_sensitive_table(table_name, (data.get("description") or "").strip(), added_by="ui")
    audit.record(_current_actor() or "unknown", "catalogue_add",
                 params={"catalogue": "sensitive-tables", "code": table_name})
    return jsonify({"ok": True, "items": list_sensitive_tables_detailed()})


@api_bp.delete("/catalogues/sensitive-tables/<table_name>")
def delete_sensitive_table(table_name):
    remove_sensitive_table(table_name)
    audit.record(_current_actor() or "unknown", "catalogue_remove",
                 params={"catalogue": "sensitive-tables", "code": table_name})
    return jsonify({"ok": True, "items": list_sensitive_tables_detailed()})
