"""Registry tying a stable key + display label to each rule function, so the
CLI script and the web UI can both list/run "all rules" without duplicating
the list.
"""
from . import _common
from .login_attack import detect_login_attacks
from .mass_user_changes import detect_mass_user_changes
from .new_source import detect_new_sources
from .first_time_transaction import detect_first_time_transactions
from .shared_ip_multi_user import detect_shared_ip_multi_user
from .export import detect_sensitive_table_access, detect_data_exports
from .login_time import detect_unusual_login_time
from .daily_count_baseline import detect_unusual_login_frequency, detect_unusual_activity_volume
from .out_of_context_transaction import (
    detect_out_of_context_transactions,
    detect_out_of_context_no_role_data,
)
from .critical_transaction_usage import detect_critical_transaction_usage

RULES = [
    ("login_attack", "Potential login attacks / lockouts", detect_login_attacks),
    ("mass_user_changes", "Mass user changes", detect_mass_user_changes),
    ("new_source", "New source IP", detect_new_sources),
    ("unusual_transaction", "Unusual transaction (any tcode, after baseline)",
     lambda **kw: detect_first_time_transactions(only_critical=False, **kw)),
    ("first_time_sensitive_transaction", "First-time sensitive transaction",
     lambda **kw: detect_first_time_transactions(only_critical=True, **kw)),
    ("shared_ip", "Shared IP, multiple users", detect_shared_ip_multi_user),
    ("sensitive_table_access", "Sensitive table access", detect_sensitive_table_access),
    ("data_export", "Data exports", detect_data_exports),
    ("login_time", "Unusual login time", detect_unusual_login_time),
    ("login_frequency", "Unusual login frequency", detect_unusual_login_frequency),
    ("activity_volume", "Unusual activity volume", detect_unusual_activity_volume),
    ("out_of_context_transaction", "Out-of-context transaction usage", detect_out_of_context_transactions),
    ("out_of_context_no_role_data", "Transaction run with no role data on record",
     detect_out_of_context_no_role_data),
    ("critical_transaction_usage", "Critical transaction executed", detect_critical_transaction_usage),
]


def run_all_rules(system_id=None, client=None) -> list[dict]:
    # Several rules request the identical fetch_events() combination (AU3
    # five times, AU1 four times, as of this writing) - cache within this
    # one pass so each is only actually queried/sorted once. Safe because
    # nothing writes to `events` between rule calls in a single pass, so a
    # repeated call is guaranteed to return the same rows. Found live: on
    # a ~670K-row events table this redundancy alone made a single ad-hoc
    # day's sync_findings() take ~98s. Always reset in `finally` so a
    # mid-run exception can't leave stale caching on for whatever calls
    # fetch_events() next (a script, a test, another rule of a different
    # kind).
    _common._cache = {}
    try:
        all_findings = []
        for key, label, fn in RULES:
            for finding in fn(system_id=system_id, client=client):
                finding = dict(finding)
                finding["rule_key"] = key
                finding["rule_label"] = label
                all_findings.append(finding)
    finally:
        _common._cache = None

    # Stable sort twice: first by time (secondary, descending), then by
    # severity (primary) - groups by severity while keeping newest-first
    # within each group.
    severity_rank = {"High": 0, "Medium": 1, "Low": 2}
    all_findings.sort(key=lambda f: f["detected_at"], reverse=True)
    all_findings.sort(key=lambda f: severity_rank.get(f["severity"], 3))
    return all_findings
