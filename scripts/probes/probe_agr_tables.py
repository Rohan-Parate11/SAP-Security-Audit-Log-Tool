"""Spike (Phase F planning, 2026-09-10): validate reading AGR_USERS and
AGR_TCODES over RFC via RFC_READ_TABLE - the actual PFCG role-to-user and
role-to-tcode assignment tables, which is what Phase F's use cases (#6
peer-group deviation, #14 out-of-context tcode usage) need.

Both worked cleanly against S23:
  - AGR_USERS: UNAME, AGR_NAME (role name), FROM_DAT, TO_DAT - gives every
    user's role assignments with validity dates, in one bulk call rather
    than one RFC call per user.
  - AGR_TCODES: AGR_NAME, TCODE - gives every role's authorized
    transaction codes (its PFCG "menu"), also in one bulk call.

Together: a user's actually-authorized tcode set = the union of
AGR_TCODES.TCODE for every AGR_NAME in AGR_USERS where UNAME = that user
(and FROM_DAT/TO_DAT cover "now"). Cross-referencing that against AU3
(transaction started) events already in `events` is exactly use case #14.

Caveat (real, not yet resolved): RFC_READ_TABLE is a generic table read,
not a purpose-built BAPI - it requires S_TABU_DIS/S_TABU_NAM authority in
whatever SU53-derived scoped role eventually replaces SAL_RFC's current
SAP_ALL (see Docs/Memory.md item 0d). Confirm this explicitly stays true
when that scoping work happens later - don't assume it'll "just work"
under a narrower role without checking.

RFC_READ_TABLE also caps DATA row length (512 bytes for older releases,
wider on newer ones) and returns rows as a single delimited WA string
that must be split, not proper structured fields - both handled in this
probe; both need the same handling in the real collector.

Usage:
    python scripts\\probes\\probe_agr_tables.py SYSTEM_ID [USERNAME_FILTER]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def _read_table(conn, table: str, fields: list[str], where: str | None = None,
                 max_rows: int = 15) -> list[dict]:
    kwargs = {
        "QUERY_TABLE": table,
        "DELIMITER": "|",
        "FIELDS": [{"FIELDNAME": f} for f in fields],
        "ROWCOUNT": max_rows,
    }
    if where:
        kwargs["OPTIONS"] = [{"TEXT": where}]
    result = conn.call("RFC_READ_TABLE", **kwargs)
    rows = []
    for raw in result.get("DATA", []):
        values = raw["WA"].split("|")
        rows.append(dict(zip(fields, (v.strip() for v in values))))
    return rows


def main(system_id: str, username_filter: str | None = None) -> int:
    try:
        with SapConnection(system_id) as conn:
            where = f"UNAME = '{username_filter}'" if username_filter else None
            print(f"=== AGR_USERS (role assignments{f' for {username_filter}' if username_filter else ''}) ===")
            for row in _read_table(conn, "AGR_USERS", ["UNAME", "AGR_NAME", "FROM_DAT", "TO_DAT"], where):
                print(row)

            print("\n=== AGR_TCODES (role -> authorized tcodes, first 15) ===")
            for row in _read_table(conn, "AGR_TCODES", ["AGR_NAME", "TCODE"]):
                print(row)
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
