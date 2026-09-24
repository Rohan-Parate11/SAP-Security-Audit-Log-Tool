"""CLI: run all Phase 1 detection rules against stored SM20 events and print
findings, grouped by rule.

Usage:
    python scripts\\run_rules.py [SYSTEM_ID] [CLIENT]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sal.catalogues import seed_default_critical_transactions, seed_default_sensitive_tables
from sal.rules import RULES, run_all_rules


def main(system_id: str, client: str) -> int:
    seed_default_critical_transactions()
    seed_default_sensitive_tables()

    findings = run_all_rules(system_id=system_id, client=client)
    by_rule = {key: [] for key, _label, _fn in RULES}
    for f in findings:
        by_rule[f["rule_key"]].append(f)

    for key, label, _fn in RULES:
        rows = by_rule[key]
        print(f"\n=== {label}: {len(rows)} finding(s) ===")
        for f in rows[:25]:
            who = f["user_id"] or "(multiple users)"
            print(f"  [{f['severity']:6}] {f['detected_at']}  {who:15} {f['summary']}")
        if len(rows) > 25:
            print(f"  ... and {len(rows) - 25} more")

    return 0


if __name__ == "__main__":
    system = sys.argv[1] if len(sys.argv) > 1 else "S23"
    client = sys.argv[2] if len(sys.argv) > 2 else "100"
    raise SystemExit(main(system, client))
