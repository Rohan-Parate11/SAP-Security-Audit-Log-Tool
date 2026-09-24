import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            result = conn.call("TH_SERVER_LIST")
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    for row in result.get("LIST", []):
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
