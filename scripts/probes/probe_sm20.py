"""Spike: call RSAU_READ_LOG directly and inspect the raw rows it returns.

Usage:
    python scripts\\probe_sm20.py SYSTEM_ID [DAYS_BACK]
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, days_back: int) -> int:
    dat_to = datetime.now()
    dat_from = dat_to - timedelta(days=days_back)

    is_intv = {
        "DAT_FROM": dat_from.strftime("%Y%m%d"),
        "DAT_TO": dat_to.strftime("%Y%m%d"),
        "TIM_FROM": "000000",
        "TIM_TO": "235959",
    }
    is_class = {
        "MISC": "X",
        "LOGON": "X",
        "TASTART": "X",
        "REPSTART": "X",
        "RFCLOGIN": "X",
        "USERMGM": "X",
        "SYSTEM": "X",
        "RFCCALL": "X",
    }
    is_seve = {"LOW": "X", "MEDIUM": "X", "HIGH": "X"}

    is_sel_attr = {
        "SERVER": [
            {"SIGN": "I", "OPTION": "EQ", "LOW": "ALINHANAS423_S23_00", "HIGH": ""}
        ],
    }

    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "RSAU_READ_LOG",
                IS_INTV=is_intv,
                IS_CLASS=is_class,
                IS_SEVE=is_seve,
                IS_SEL_ATTR=is_sel_attr,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    rows = result.get("ET_DATA", [])
    stats = result.get("ET_STAT", [])
    print(f"Rows returned: {len(rows)}")
    print(f"Stat entries:  {len(stats)}")

    for row in rows[:10]:
        print(row)

    if stats:
        print("\nFirst stat entry:")
        print(stats[0])

    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    raise SystemExit(main(system, days))
