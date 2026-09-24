"""Spike: try RFC_READ_TABLE directly against the audit log table(s) as a
fallback path, since RSAU_READ_LOG keeps returning 0 rows / 0 stat entries
over RFC despite 45M+ rows confirmed to exist via the GUI check report.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, table_name: str, rowcount: int) -> int:
    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "RFC_READ_TABLE",
                QUERY_TABLE=table_name,
                DELIMITER="|",
                ROWCOUNT=rowcount,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    fields = result.get("FIELDS", [])
    data = result.get("DATA", [])
    print(f"Table: {table_name}")
    print(f"{len(fields)} field(s):")
    for f in fields:
        print(f"  {f}")
    print(f"\n{len(data)} data row(s):")
    for row in data[:10]:
        print(row)
    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    table = sys.argv[2] if len(sys.argv) > 2 else "RSAU_LOG"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    raise SystemExit(main(system, table, n))
