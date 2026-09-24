"""Spike: search for RFC-enabled function modules matching a name pattern."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, pattern: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "RFC_FUNCTION_SEARCH",
                FUNCNAME=pattern,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    rows = result.get("FUNCTIONS", [])
    print(f"{len(rows)} matches for '{pattern}'")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
