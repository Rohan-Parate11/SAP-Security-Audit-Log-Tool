"""Config catalogues (S1-12): transactions classified as critical/sensitive.

Stored in a table rather than hard-coded so an admin can extend it per
customer without a code change.
"""
from datetime import datetime, timezone

from .storage.db import get_connection, init_schema

DEFAULT_CRITICAL_TRANSACTIONS = {
    "SU01": "Maintain users",
    "PFCG": "Maintain roles",
    "SE16N": "Direct table display/edit",
    "SM19": "Security Audit Log configuration",
    "SM20": "Security Audit Log display",
    "SCC4": "Client administration",
    "STMS": "Transport Management System",
    "SE38": "ABAP program editor",
    "SA38": "Execute ABAP program",
    "SM30": "Table maintenance generator",
    "SM59": "RFC destination maintenance",
    "SU10": "Mass user maintenance",
}

DEFAULT_SENSITIVE_TABLES = {
    "USR02": "User logon/password hash data",
    "USR04": "User authorization profile assignments",
    "PA0002": "HR master data - personal data",
    "PA0008": "HR master data - payroll/compensation",
    "BSEG": "Accounting document line items",
    "BKPF": "Accounting document headers",
    "KNA1": "Customer master (general data)",
    "LFA1": "Vendor master (general data)",
    "T001": "Company codes",
}


def add_critical_transaction(tcode: str, description: str = "", added_by: str = "system") -> None:
    init_schema()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO critical_transactions "
            "(transaction_code, description, added_by, added_at) VALUES (?, ?, ?, ?)",
            (tcode.upper(), description, added_by, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_critical_transactions() -> list[str]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT transaction_code FROM critical_transactions").fetchall()
        return [row["transaction_code"] for row in rows]
    finally:
        conn.close()


def list_critical_transactions_detailed() -> list[dict]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT transaction_code, description, added_by, added_at "
            "FROM critical_transactions ORDER BY transaction_code"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def remove_critical_transaction(tcode: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM critical_transactions WHERE transaction_code = ?", (tcode.upper(),)
        )
        conn.commit()
    finally:
        conn.close()


def seed_default_critical_transactions() -> None:
    for tcode, description in DEFAULT_CRITICAL_TRANSACTIONS.items():
        add_critical_transaction(tcode, description)


def add_sensitive_table(table_name: str, description: str = "", added_by: str = "system") -> None:
    init_schema()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sensitive_tables "
            "(table_name, description, added_by, added_at) VALUES (?, ?, ?, ?)",
            (table_name.upper(), description, added_by, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_sensitive_tables() -> list[str]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT table_name FROM sensitive_tables").fetchall()
        return [row["table_name"] for row in rows]
    finally:
        conn.close()


def list_sensitive_tables_detailed() -> list[dict]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT table_name, description, added_by, added_at "
            "FROM sensitive_tables ORDER BY table_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def remove_sensitive_table(table_name: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sensitive_tables WHERE table_name = ?", (table_name.upper(),))
        conn.commit()
    finally:
        conn.close()


def seed_default_sensitive_tables() -> None:
    for table_name, description in DEFAULT_SENSITIVE_TABLES.items():
        add_sensitive_table(table_name, description)
