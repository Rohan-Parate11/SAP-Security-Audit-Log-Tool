"""Central, encrypted SAP credential store (requested directly, 2026-09-16 -
answers the HOME-02 open question in Docs/Open_Questions_For_Review.txt).

This reverses a constraint this project held for most of its life
("credentials never enter SAL's own database") - a deliberate, informed
decision by the project owner, not an oversight. Two explicit choices
that shape this module:

  1. A stored password IS viewable again through the UI/API (not
     write-only) - the project owner's explicit call, made after being
     shown the tradeoff: this app has no RBAC (sal/web/api.py's
     _current_actor() is a self-declared cookie, attribution only), so
     anyone who can reach it can read any system's live SAP password on
     demand. Every read is audit-logged (credential_view) as the one
     mitigation available given that choice - see get_credential()'s
     callers in sal/web/api.py.
  2. .env keeps working unchanged for any system that has never had a
     password saved here - this module is additive, not a migration.
     sal.config.sap_system_config() checks here FIRST (via
     resolve_stored_config()) and only falls back to its original
     all-.env logic when this module has nothing for that system_id.

Encrypted at rest with Fernet (symmetric, authenticated encryption - the
`cryptography` package, already a transitive dependency of pyrfc in this
environment, now declared directly in requirements.txt since relying on
an undeclared transitive dependency is fragile). The encryption key
itself lives in SAL_CREDENTIAL_ENCRYPTION_KEY (.env), deliberately
OUTSIDE this database - the same principle that kept SAP credentials out
of sal.db in the first place, just one layer down: a stolen sal.db file
alone is not enough to decrypt anything in it.

Stores rfc_user alongside the encrypted password, not just the password -
sal.config.sap_system_config() has always needed both to build a
connection, and a system fully configured through this store (plus its
systems.py registry row for ashost/sysnr/client) is meant to need no
.env entry at all.
"""
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from . import config  # noqa: F401  (import side effect: loads .env via load_dotenv())
from .storage.db import get_connection, init_schema


class CredentialStoreNotConfigured(RuntimeError):
    """SAL_CREDENTIAL_ENCRYPTION_KEY is missing or invalid."""


def _fernet() -> Fernet:
    key = os.environ.get("SAL_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not key:
        raise CredentialStoreNotConfigured(
            "SAL_CREDENTIAL_ENCRYPTION_KEY is not set. Generate one and add it to .env: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise CredentialStoreNotConfigured(
            f"SAL_CREDENTIAL_ENCRYPTION_KEY is set but is not a valid Fernet key: {exc}"
        ) from exc


def set_credential(system_id: str, rfc_user: str, password: str, actor: str) -> None:
    system_id = system_id.strip().upper()
    rfc_user = (rfc_user or "").strip()
    if not system_id:
        raise ValueError("system_id is required")
    if not rfc_user or not password:
        raise ValueError("rfc_user and password are both required")

    encrypted = _fernet().encrypt(password.encode("utf-8")).decode("ascii")
    now = datetime.now(timezone.utc).isoformat()
    init_schema()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO system_credentials (system_id, rfc_user, encrypted_passwd, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(system_id) DO UPDATE SET "
            "rfc_user = excluded.rfc_user, encrypted_passwd = excluded.encrypted_passwd, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (system_id, rfc_user, encrypted, actor, now),
        )
        conn.commit()
    finally:
        conn.close()


def remove_credential(system_id: str) -> bool:
    """Deletes the stored credential (the system reverts to needing .env,
    if configured there) - returns False if nothing was stored."""
    system_id = system_id.strip().upper()
    init_schema()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM system_credentials WHERE system_id = ?", (system_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def has_stored_credential(system_id: str) -> bool:
    system_id = system_id.strip().upper()
    init_schema()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM system_credentials WHERE system_id = ?", (system_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_credential(system_id: str) -> dict | None:
    """Returns {"rfc_user", "password" (decrypted), "updated_by",
    "updated_at"} or None if nothing is stored for this system. The
    caller (sal/web/api.py) is responsible for audit-logging every call
    that reveals `password` to a UI request - see this module's own
    docstring for why that's the one mitigation available here.
    """
    system_id = system_id.strip().upper()
    init_schema()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT rfc_user, encrypted_passwd, updated_by, updated_at FROM system_credentials "
            "WHERE system_id = ?",
            (system_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        password = _fernet().decrypt(row["encrypted_passwd"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialStoreNotConfigured(
            f"Stored credential for '{system_id}' could not be decrypted - "
            "SAL_CREDENTIAL_ENCRYPTION_KEY may have changed since it was saved."
        ) from exc
    return {
        "rfc_user": row["rfc_user"], "password": password,
        "updated_by": row["updated_by"], "updated_at": row["updated_at"],
    }


def resolve_stored_config(system_id: str) -> dict | None:
    """Full RFC connection-params dict (ashost/sysnr/client/user/passwd)
    for a system that has a password stored here, or None if this system
    should fall back to sal.config.sap_system_config()'s original all-.env
    logic instead (nothing stored, or its systems.py registry row is
    missing for some reason - e.g. deleted after the credential was saved).

    ashost/sysnr/client come from sal.systems' registry (already
    maintained through the "Add/Edit system" UI, non-secret); user/passwd
    come from this store. The import below is deferred to call time, not
    module level, because sal.systems already imports sal.config at
    module level, and sal.config.sap_system_config() is what calls into
    this function - a module-level import here would be circular.
    """
    stored = get_credential(system_id)
    if stored is None:
        return None
    from . import systems
    sys_row = systems.get_system(system_id)
    if sys_row is None:
        return None
    return {
        "ashost": sys_row["ashost"], "sysnr": sys_row["sysnr"], "client": sys_row["client"],
        "user": stored["rfc_user"], "passwd": stored["password"],
    }


def credential_source(system_id: str) -> str:
    """"central" (stored here), "env" (falls back to a fully-configured
    .env profile), or "missing" (neither) - for the Password Manager
    page's overview list. Deliberately does not decrypt anything just to
    answer this - has_stored_credential() alone is enough.
    """
    if has_stored_credential(system_id):
        return "central"
    if bool(os.environ.get(f"SAL_SAP_{system_id.upper()}_PASSWD")):
        return "env"
    return "missing"
