"""Ad-hoc spike helper: inspect a remote-enabled function module's interface.

Usage:
    python scripts\\probe_function.py SYSTEM_ID FUNCTION_NAME
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, function_name: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            desc = conn.call(
                "RFC_GET_FUNCTION_INTERFACE",
                FUNCNAME=function_name,
            )
            print(f"Function module: {function_name}")
            for param in desc.get("PARAMS", []):
                print(
                    f"  {param['PARAMCLASS']:1} {param['PARAMETER']:<20} "
                    f"type={param.get('TYP', ''):<10} default={param.get('DEFAULT', '')}"
                )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
