import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str) -> int:
    try:
        with SapConnection(system_id) as conn:
            print("Writing test event (RSAU_WRITE_TEST_EVENT)...")
            try:
                write_result = conn.call("RSAU_WRITE_TEST_EVENT")
                print(f"Write result: {write_result}")
            except SapConnectionError as exc:
                print(f"Write call failed/not usable: {exc}")

            time.sleep(2)

            now = datetime.now()
            frm = now - timedelta(minutes=10)
            result = conn.call(
                "RSAU_READ_LOG",
                IS_INTV={
                    "DAT_FROM": frm.strftime("%Y%m%d"),
                    "DAT_TO": now.strftime("%Y%m%d"),
                    "TIM_FROM": "000000",
                    "TIM_TO": "235959",
                },
                IS_CLASS={
                    "MISC": "X", "LOGON": "X", "TASTART": "X", "REPSTART": "X",
                    "RFCLOGIN": "X", "USERMGM": "X", "SYSTEM": "X", "RFCCALL": "X",
                },
                IS_SEVE={"LOW": "X", "MEDIUM": "X", "HIGH": "X"},
                IS_SEL_ATTR={},
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    rows = result.get("ET_DATA", [])
    stats = result.get("ET_STAT", [])
    print(f"\nRows returned: {len(rows)}")
    print(f"Stat entries:  {len(stats)}")
    for row in rows[:10]:
        print(row)
    for stat in stats[:10]:
        print(stat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
