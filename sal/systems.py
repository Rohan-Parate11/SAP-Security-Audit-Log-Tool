"""SAP system/environment registry (Blueprint v2, Phase E, pulled forward).

Stores non-secret connection metadata (environment, host, sysnr, client,
description) in the app's own database so systems can be added/edited via
the UI instead of hand-editing .env. This table itself still has no
password column - that remains structurally true - but as of 2026-09-16
a system's password CAN be centrally stored, encrypted, in the separate
sal/credentials.py-owned system_credentials table (a deliberate, informed
reversal of this project's original .env-only stance - see that module's
own docstring for the full reasoning and the tradeoffs the project owner
explicitly accepted). has_credentials() now reports true if EITHER that
store or SAL_SAP_<system_id>_PASSWD has something for this system - never
the value itself, just whether one exists. Every collection path (ad-hoc,
scheduled, CLI) still resolves credentials via sal.config.sap_system_
config(), which now also checks the central store first.

Backward compatibility: systems already configured purely via .env (like
S23, set up before this registry existed) are auto-registered on first use
via seed_from_env(), defaulted to the "Sandbox" environment since the
existing .env variables carry no environment classification - review and
correct that via the UI after upgrading.
"""
import os
from datetime import datetime, timezone

from . import config
from .storage.db import get_connection, init_schema

ENVIRONMENTS = ("Development", "Quality", "Production", "Sandbox")
_DEFAULT_SEED_ENVIRONMENT = "Sandbox"

# Sentinel distinguishing "field omitted from a partial update" (keep
# existing value) from "field explicitly set to empty" (clear it) - only
# meaningful for `description`, the one nullable column.
UNSET = object()

_seeded = False


def has_credentials(system_id: str) -> bool:
    # Deferred import - sal.credentials imports sal.config at module level,
    # and sal.config.sap_system_config() calls into sal.credentials too;
    # keeping this one deferred as well avoids relying on import-order
    # accidents to dodge a cycle.
    from . import credentials
    if credentials.has_stored_credential(system_id):
        return True
    return bool(os.environ.get(f"SAL_SAP_{system_id.upper()}_PASSWD"))


def seed_from_env(actor: str = "system") -> None:
    """Backfill the registry with any system discoverable from .env that
    doesn't already have a row here - keeps pre-existing installs working
    without requiring a manual re-add through the UI.
    """
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        existing_ids = {row["system_id"] for row in conn.execute("SELECT system_id FROM systems")}
        for env_system in config.list_configured_systems():
            system_id = env_system["system_id"]
            if system_id in existing_ids:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO systems "
                "(system_id, environment, description, ashost, sysnr, client, "
                " created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    system_id, _DEFAULT_SEED_ENVIRONMENT,
                    env_system.get("description") or system_id,
                    os.environ.get(f"SAL_SAP_{system_id}_ASHOST", ""),
                    os.environ.get(f"SAL_SAP_{system_id}_SYSNR", ""),
                    env_system.get("client") or "",
                    actor, now, now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _ensure_seeded() -> None:
    """seed_from_env() does real DB work (a SELECT + N potential INSERTs)
    every time it runs - fine as a one-time startup cost, wasteful if paid
    on every read (list_systems() used to call it unconditionally, including
    from POST /api/collect's system_id validation on every ad-hoc submit).
    Cached per-process; .env-discovered systems don't change without a
    restart anyway, so a stale cache within one process run is not a
    real-world concern.
    """
    global _seeded
    if _seeded:
        return
    seed_from_env()
    _seeded = True


def list_systems() -> list[dict]:
    _ensure_seeded()
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM systems ORDER BY environment, system_id"
        ).fetchall()]
    finally:
        conn.close()
    for row in rows:
        row["has_credentials"] = has_credentials(row["system_id"])
    return rows


def get_system(system_id: str) -> dict | None:
    _ensure_seeded()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM systems WHERE system_id = ?", (system_id.strip().upper(),)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    result = dict(row)
    result["has_credentials"] = has_credentials(result["system_id"])
    return result


def add_system(system_id: str, environment: str, ashost: str, sysnr: str,
                client: str, created_by: str, description: str | None = None) -> None:
    init_schema()
    system_id = system_id.strip().upper()
    if not system_id:
        raise ValueError("system_id is required")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        # INSERT OR IGNORE + rowcount, not a separate get_system() pre-check
        # then plain INSERT - two concurrent requests for the same new
        # system_id could otherwise both pass the pre-check before either
        # commits, and the loser's plain INSERT would raise an unhandled
        # IntegrityError (500) instead of a clean "already exists" error.
        cur = conn.execute(
            "INSERT OR IGNORE INTO systems "
            "(system_id, environment, description, ashost, sysnr, client, "
            " created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (system_id, environment, description, ashost, sysnr, client,
             created_by, now, now),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"System '{system_id}' already exists")
    finally:
        conn.close()


def update_system(system_id: str, environment: str | None = None,
                   description=UNSET, ashost: str | None = None,
                   sysnr: str | None = None, client: str | None = None) -> bool:
    system_id = system_id.strip().upper()
    existing = get_system(system_id)
    if existing is None:
        return False
    if environment is not None and environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}")

    fields = {
        "environment": environment if environment is not None else existing["environment"],
        "description": existing["description"] if description is UNSET else description,
        "ashost": ashost if ashost is not None else existing["ashost"],
        "sysnr": sysnr if sysnr is not None else existing["sysnr"],
        "client": client if client is not None else existing["client"],
    }
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE systems SET environment = ?, description = ?, ashost = ?, "
            "sysnr = ?, client = ?, updated_at = ? WHERE system_id = ?",
            (fields["environment"], fields["description"], fields["ashost"],
             fields["sysnr"], fields["client"], datetime.now(timezone.utc).isoformat(),
             system_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_system(system_id: str) -> bool:
    init_schema()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM systems WHERE system_id = ?", (system_id.strip().upper(),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
