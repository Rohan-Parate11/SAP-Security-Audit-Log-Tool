"""Spike: tightly-scoped RSAU_READ_LOG query for our own just-made RFC logon,
to isolate whether the read path itself works at all.
"""
import sys
from datetime import datetime, timedelta
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
    for row in rows[:5]:
        print(row)
    for stat in stats[:5]:
        print(stat)


def main(system_id: str) -> int:
    now = datetime.now()
    frm = now - timedelta(minutes=5)

    is_intv = {
        "DAT_FROM": frm.strftime("%Y%m%d"),
        "DAT_TO": now.strftime("%Y%m%d"),
        "TIM_FROM": frm.strftime("%H%M%S"),
        "TIM_TO": now.strftime("%H%M%S"),
    }
    is_class_all = {
        "MISC": "X", "LOGON": "X", "TASTART": "X", "REPSTART": "X",
        "RFCLOGIN": "X", "USERMGM": "X", "SYSTEM": "X", "RFCCALL": "X",
    }
    is_seve_all = {"LOW": "X", "MEDIUM": "X", "HIGH": "X"}

    try:
        with SapConnection(system_id) as conn:
            # This very connection is itself an RFC logon on client 100 as SAL_RFC,
            # which Filter 01 (client=*, user=*, RFC/CPIC Logon checked) should log.
            conn.ping()

            try_call(
                conn, "wide window, all classes, no attr filter, no MANDT",
                IS_INTV=is_intv, IS_CLASS=is_class_all, IS_SEVE=is_seve_all,
                IS_SEL_ATTR={},
            )

            try_call(
                conn, "explicit MANDT=100",
                IS_INTV=is_intv, IS_CLASS=is_class_all, IS_SEVE=is_seve_all,
                IS_SEL_ATTR={
                    "MANDT": [{"SIGN": "I", "OPTION": "EQ", "LOW": "100", "HIGH": ""}],
                },
            )

            try_call(
                conn, "explicit MANDT=100 + USER=SAL_RFC",
                IS_INTV=is_intv, IS_CLASS=is_class_all, IS_SEVE=is_seve_all,
                IS_SEL_ATTR={
                    "MANDT": [{"SIGN": "I", "OPTION": "EQ", "LOW": "100", "HIGH": ""}],
                    "USER": [{"SIGN": "I", "OPTION": "EQ", "LOW": "SAL_RFC", "HIGH": ""}],
                },
            )

            try_call(
                conn, "today full day, all classes, no attr filter",
                IS_INTV={
                    "DAT_FROM": now.strftime("%Y%m%d"),
                    "DAT_TO": now.strftime("%Y%m%d"),
                    "TIM_FROM": "000000",
                    "TIM_TO": "235959",
                },
                IS_CLASS=is_class_all, IS_SEVE=is_seve_all, IS_SEL_ATTR={},
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
