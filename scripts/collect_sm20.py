"""CLI: run an SM20 collection and store it in the local SAL database.

Usage:
    python scripts\\collect_sm20.py SYSTEM_ID CLIENT DAYS_BACK
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sal.collectors import collect_and_store
from sal import findings as findings_svc


def main(system_id: str, client: str, days_back: int) -> int:
    now = datetime.now()
    frm = now - timedelta(days=days_back)

    summary = collect_and_store(
        system_id=system_id,
        client=client,
        dat_from=frm.strftime("%Y%m%d"),
        dat_to=now.strftime("%Y%m%d"),
    )

    # Mirrors sal/web/api.py's /collect handler: a successful collection is
    # only half the job - without this, findings sit uncomputed until
    # someone happens to trigger a sync through the UI (see Docs/PROJECT-CONTEXT.md,
    # Phase A root cause: this CLI path used to skip sync entirely).
    if summary.get("status") == "success":
        sync_result = findings_svc.sync_findings(system_id=system_id, client=client)
        summary["new_findings"] = sync_result["new"]
        summary["computed_findings"] = sync_result["computed"]

    print(summary)
    return 0 if summary.get("status") == "success" else 1


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    client = sys.argv[2] if len(sys.argv) > 2 else "100"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    raise SystemExit(main(system, client, days))
