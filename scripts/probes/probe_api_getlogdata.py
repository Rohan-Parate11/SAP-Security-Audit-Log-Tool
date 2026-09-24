"""Spike: try the modern RSAU_API_GET_LOG_DATA function against the known-good
window (2026-08-28 20:00-20:30, client 100) where RFC_READ_TABLE already
proved SAL_RFC's own records exist.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sal.sap_connector import SapConnection, SapConnectionError


def main(system_id: str) -> int:
    is_interval = {
        "DAT_FROM": "20260828",
        "DAT_TO": "20260828",
        "TIM_FROM": "200000",
        "TIM_TO": "203000",
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

    log_rows = result.get("ET_LOG", [])
    fstat = result.get("ET_FSTAT", [])
    ret = result.get("ET_RETURN", [])
    print(f"ET_LOG: {len(log_rows)} row(s)")
    for row in log_rows[:15]:
        print(row)
    print(f"\nET_FSTAT: {len(fstat)} row(s)")
    for row in fstat[:10]:
        print(row)
    print(f"\nET_RETURN: {len(ret)} row(s)")
    for row in ret[:10]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "S23"))
