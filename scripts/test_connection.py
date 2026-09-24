"""Stage 1 technical spike: validate RFC connectivity to an SAP system.

Usage:
    python scripts\\test_connection.py [SYSTEM_ID]

SYSTEM_ID defaults to S23 and must match a SAL_SAP_<SYSTEM_ID>_* profile in .env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str) -> int:
    print(f"Testing RFC connection to SAP system '{system_id}'...")
    try:
        with SapConnection(system_id) as conn:
            conn.ping()
            print("RFC_PING succeeded.")

            info = conn.call("RFC_SYSTEM_INFO")["RFCSI_EXPORT"]
            print(f"System ID:   {info['RFCSYSID']}")
            print(f"SAP Release: {info['RFCSAPRL']}")
            print(f"App server:  {info['RFCHOST']}")
            print(f"DB host:     {info['RFCDBHOST']}")
            print(f"OS:          {info['RFCOPSYS']}")
    except SapConnectionError as exc:
        print(f"Connection test FAILED: {exc}")
        return 1

    print("Connection test PASSED.")
    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    raise SystemExit(main(system))
