"""Spike: check which values a user has for a given authorization object.

Usage:
    python scripts\\probe_authcheck.py SYSTEM_ID USER_NAME AUTH_OBJECT
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, user_name: str, auth_object: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "SUSR_USER_AUTH_FOR_OBJ_GET",
                USER_NAME=user_name,
                SEL_OBJECT=auth_object,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    print(f"FULLY_AUTHORIZED: {result.get('FULLY_AUTHORIZED')!r}")
    values = result.get("VALUES", [])
    print(f"{len(values)} value row(s):")
    for row in values:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
