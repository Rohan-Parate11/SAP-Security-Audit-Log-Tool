"""Spike: query RSAU_READ_LOG for a window we now know (via RFC_READ_TABLE)
contains real SAL_RFC records, to isolate the RSAU_READ_LOG-specific bug.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def try_call(conn, label, **kwargs):
    print(f"\n--- {label} ---")
    try:
        result = conn.call("RSAU_READ_LOG", **kwargs)
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return
    rows = result.get("ET_DATA", [])
    stats = result.get("ET_STAT", [])
    print(f"Rows: {len(rows)}  Stat: {len(stats)}")
    for row in rows[:10]:
        print(row)
    for stat in stats[:10]:
        print(stat)


def main(system_id: str) -> int:
    is_intv = {
        "DAT_FROM": "20260828",
        "DAT_TO": "20260828",
        "TIM_FROM": "200000",
        "TIM_TO": "203000",
    }
    is_class_all = {
        "MISC": "X", "LOGON": "X", "TASTART": "X", "REPSTART": "X",
        "RFCLOGIN": "X", "USERMGM": "X", "SYSTEM": "X", "RFCCALL": "X",
    }
    is_seve_all = {"LOW": "X", "MEDIUM": "X", "HIGH": "X"}

    try:
        with SapConnection(system_id) as conn:
            try_call(
                conn, "known-good window 2026-08-28 20:00-20:30, client 100, no attr filter",
                IS_INTV=is_intv, IS_CLASS=is_class_all, IS_SEVE=is_seve_all,
                IS_SEL_ATTR={},
            )
            try_call(
                conn, "known-good window + explicit USER=SAL_RFC",
                IS_INTV=is_intv, IS_CLASS=is_class_all, IS_SEVE=is_seve_all,
                IS_SEL_ATTR={
                    "USER": [{"SIGN": "I", "OPTION": "EQ", "LOW": "SAL_RFC", "HIGH": ""}],
                },
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
