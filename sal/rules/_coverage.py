"""Rule -> SM19 audit-class coverage mapping (Blueprint v2, Phase D).

Maps each detection rule to the SM19 event class(es) it depends on, so
Phase D's coverage check can flag when the active audit configuration
doesn't capture what a rule assumes. Deliberately at the SM19 *class*
level (CLASS_LOGIN, CLASS_TCD, etc.) - RSAU_API_GET_AUDIT_CONFIG's
per-slot class flags (validated live against S23 during Phase D planning)
are self-describing, named boolean flags and safe to interpret. That same
RFC response also returns a MSGVECT byte vector for individual-message-
code-level detail, but that bit-encoding isn't documented anywhere
verifiable - guessing at it risks exactly what QA flagged during planning:
a false "you're covered" signal is worse than the blind spot this phase
exists to close. Message-code-level precision is a deliberate v2, not
attempted here.

Sourced directly from each rule's own fetch_events() call - grep
sal/rules/*.py for msg_codes=/event_class= to verify/update this mapping
if a rule's filtering logic ever changes. The class assignment for AU1/
AU2/AU3 (dialog logon / transaction start) is standard, well-documented
SAP audit message-code classification. DU9/AUY (generic table access /
data export) are mapped to "Other Events" with only moderate confidence -
flagged explicitly below, not asserted as fact.
"""

CLASS_LOGIN = "CLASS_LOGIN"          # Dialog logon
CLASS_RFC_LOGIN = "CLASS_RFC_LOGIN"  # RFC/CPIC logon
CLASS_TCD = "CLASS_TCD"              # Transaction start
CLASS_REP = "CLASS_REP"              # Report start
CLASS_USER = "CLASS_USER"            # User master record change
CLASS_SYST = "CLASS_SYST"            # System events
CLASS_RFC = "CLASS_RFC"              # RFC function calls
CLASS_OTHER = "CLASS_OTHER"          # Other events (generic table access, exports, etc.)

RULE_COVERAGE = {
    "login_attack": {
        "classes": {CLASS_LOGIN},
        "source": "msg_codes=['AU1','AU2','AUM'] (sal/rules/login_attack.py)",
        "confidence": "high",
    },
    "mass_user_changes": {
        "classes": {CLASS_USER},
        "source": "event_class='User master changes' (sal/rules/mass_user_changes.py)",
        "confidence": "high",
    },
    "new_source": {
        "classes": {CLASS_LOGIN},
        "source": "msg_codes=['AU1'] (sal/rules/new_source.py)",
        "confidence": "high",
    },
    "shared_ip": {
        "classes": {CLASS_LOGIN},
        "source": "msg_codes=['AU1'] (sal/rules/shared_ip_multi_user.py)",
        "confidence": "high",
    },
    "login_time": {
        "classes": {CLASS_LOGIN},
        "source": "msg_codes=['AU1'] (sal/rules/login_time.py)",
        "confidence": "high",
    },
    "login_frequency": {
        "classes": {CLASS_LOGIN},
        "source": "msg_codes=['AU1'] (sal/rules/daily_count_baseline.py)",
        "confidence": "high",
    },
    "activity_volume": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/daily_count_baseline.py)",
        "confidence": "high",
    },
    "unusual_transaction": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/first_time_transaction.py)",
        "confidence": "high",
    },
    "first_time_sensitive_transaction": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/first_time_transaction.py)",
        "confidence": "high",
    },
    "sensitive_table_access": {
        "classes": {CLASS_OTHER},
        "source": "msg_codes=['DU9'] (sal/rules/export.py)",
        "confidence": "moderate - class assignment not independently verified",
    },
    "data_export": {
        "classes": {CLASS_OTHER},
        "source": "msg_codes=['DU9','AUY'] (sal/rules/export.py)",
        "confidence": "moderate - class assignment not independently verified",
    },
    "out_of_context_transaction": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/out_of_context_transaction.py)",
        "confidence": "high - SM19 coverage only; also depends on sal/role_context.py's "
                      "AGR_USERS/AGR_TCODES refresh being current, which this SM19-based "
                      "mapping cannot express - see the Role Context panel on the Coverage page.",
    },
    "out_of_context_no_role_data": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/out_of_context_transaction.py)",
        "confidence": "high - SM19 coverage only; see out_of_context_transaction's note above.",
    },
    "critical_transaction_usage": {
        "classes": {CLASS_TCD},
        "source": "msg_codes=['AU3'] (sal/rules/critical_transaction_usage.py)",
        "confidence": "high",
    },
}


def required_classes_for_rule(rule_key: str) -> set[str]:
    entry = RULE_COVERAGE.get(rule_key)
    return set(entry["classes"]) if entry else set()
