"""Spike: RFC_READ_TABLE against RSAU_LOG with a WHERE clause and explicit fields."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def chunk_where(where: str, width: int = 72):
    return [{"TEXT": where[i:i + width]} for i in range(0, len(where), width)]


def main(system_id: str, where: str, rowcount: int) -> int:
    fields = [
        {"FIELDNAME": f} for f in
        ["LOG_TSTMP", "EVENT", "SLGMAND", "SID", "INSTANCE", "SLGLTRM2",
         "SLGUSER", "SLGTC", "SLGREPNA", "TERM_IPV6"]
    ]
    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "RFC_READ_TABLE",
                QUERY_TABLE="RSAU_LOG",
                DELIMITER="|",
                ROWCOUNT=rowcount,
                OPTIONS=chunk_where(where),
                FIELDS=fields,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    data = result.get("DATA", [])
    print(f"WHERE: {where}")
    print(f"{len(data)} data row(s):")
    for row in data:
        print(row["WA"])
    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    where = sys.argv[2] if len(sys.argv) > 2 else "SLGMAND = '100'"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    raise SystemExit(main(system, where, n))
