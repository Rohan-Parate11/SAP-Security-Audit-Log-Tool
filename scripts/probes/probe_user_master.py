"""Spike (Phase F planning, 2026-09-10): validate user-master/profile RFCs
against a live system before committing to any of them in a plan.

Findings from this spike (validated against S23):
  - BAPI_USER_GETLIST works and returns a real user roster (USERNAME,
    FIRSTNAME, LASTNAME, FULLNAME).
  - BAPI_USER_GET_DETAIL is BROKEN via pyrfc on this system/release: it
    raises `decimal.InvalidOperation` from inside pyrfc's own response
    unmarshalling (_cyrfc.pyx wrapStructure/wrapVariable), reproduced
    against two different real users (DDIC, BASIS001) - not a
    user-data quirk, a systemic incompatibility. Do not use it.
  - SUSR_GET_PROFILES_OF_USER_RFC works, but its real import parameter is
    USER_NAME, not USERNAME (found via RFC_GET_FUNCTION_INTERFACE - worth
    doing that instead of guessing a BAPI's parameter names from
    convention). Returns PROFILE assignments (e.g. SAP_ALL), not PFCG
    role names - a role's auto-generated profile is not the same as the
    role's own name. Raises USER_NOT_EXISTS for at least one value seen
    in events.user_id (BASIS001) that apparently isn't a real SU01
    record - not every audit-log user_id is a maintained user.
  - For actual PFCG role names (what Phase F needs for peer-grouping and
    role-authorized-tcode context), see probe_agr_tables.py instead -
    RFC_READ_TABLE against AGR_USERS/AGR_TCODES is the validated path.

Usage:
    python scripts\\probes\\probe_user_master.py SYSTEM_ID USER_ID
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, user_id: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            print("=== BAPI_USER_GETLIST (max 5 rows) ===")
            listing = conn.call("BAPI_USER_GETLIST", MAX_ROWS=5)
            for row in listing.get("USERLIST", []):
                print(row)
            print("RETURN:", listing.get("RETURN"))

            print("\n=== SUSR_GET_PROFILES_OF_USER_RFC (USER_NAME=%s) ===" % user_id)
            try:
                profiles = conn.call("SUSR_GET_PROFILES_OF_USER_RFC", USER_NAME=user_id)
                for key, value in profiles.items():
                    if isinstance(value, list):
                        print(f"{key}: list[{len(value)}]" + (f" e.g. {value[0]}" if value else " (empty)"))
                    else:
                        print(f"{key}: {value!r}")
            except SapConnectionError as exc:
                print(f"FAILED: {exc}")

            print("\n=== BAPI_USER_GET_DETAIL - known broken, not called ===")
            print("See this file's docstring: raises decimal.InvalidOperation via pyrfc.")

    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
