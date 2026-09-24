import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            result = conn.call("RSAU_LIST_AUDIT_FILES")
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    info = result.get("AUDIT_FILE_INFO", [])
    lst = result.get("AUDIT_FILE_LIST", [])
    print(f"AUDIT_FILE_INFO: {len(info)} row(s)")
    for row in info[:20]:
        print(row)
    print(f"\nAUDIT_FILE_LIST: {len(lst)} row(s)")
    for row in lst[:20]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
