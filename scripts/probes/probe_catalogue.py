"""Spike: sample recent log data broadly and list distinct message types seen,
so we can map real MSG/CLASS codes (failed logon, user-master change, download,
etc.) instead of guessing from memory.
"""
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str, days_back: int) -> int:
    now = datetime.now()
    frm = now - timedelta(days=days_back)
    is_interval = {
        "DAT_FROM": frm.strftime("%Y%m%d"),
        "DAT_TO": now.strftime("%Y%m%d"),
        "TIM_FROM": "000000",
        "TIM_TO": "235959",
    }
    it_r_mandt = [{"SIGN": "I", "OPTION": "EQ", "LOW": "100", "HIGH": ""}]

    try:
        with SapConnection(system_id) as conn:
            result = conn.call(
                "RSAU_API_GET_LOG_DATA",
                IS_INTERVAL=is_interval,
                IT_R_MANDT=it_r_mandt,
            )
    except SapConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    rows = result.get("ET_LOG", [])
    print(f"Total rows: {len(rows)}")

    seen = {}
    counts = Counter()
    for row in rows:
        key = row["MSG"]
        counts[key] += 1
        if key not in seen:
            seen[key] = row

    print(f"\n{len(seen)} distinct MSG codes:\n")
    for msg, count in counts.most_common():
        row = seen[msg]
        print(
            f"{msg:4} x{count:<6} class={row['TXSUBCLSID']:<20} "
            f"severity={row['TXSEVERITY']:<8} sample=\"{row['SAL_DATA']}\""
        )
    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    raise SystemExit(main(system, days))
