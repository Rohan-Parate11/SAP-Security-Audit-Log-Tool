"""Use case #14: suspicious/out-of-context transaction usage.

Signal: AU3 (transaction started), restricted to the critical-transaction
catalogue - same scoping as use case #11's first_time_sensitive_transaction.
Checking every tcode a user ever ran against role menus would be noisy;
critical transactions are where an authorization gap actually matters.

For each critical-transaction AU3 event, cross-references the tcode
against the user's CURRENTLY authorized set
(sal.role_context.authorized_tcodes_for_user() - a join of user_roles x
role_tcodes, valid as of today, not as of when the event happened - see
role_context.py's own docstring for why point-in-time reconstruction
isn't attempted). Three distinct outcomes, never conflated:

  - Covered by a current role: no finding.
  - Roles exist, but none include this tcode: "out_of_context_transaction".
  - Zero role rows on record for this user at all:
    "out_of_context_no_role_data" - a deliberately separate rule_key (see
    registry.py - both wrap this module's shared _detect(), the same
    pattern first_time_transaction.py uses for #4 vs #11), so an analyst
    can tell "this person's roles don't cover it" apart from "this person
    currently has no SAP role assignments on record at all," which is the
    more unusual of the two.

Because sync_findings() re-evaluates every retained event on every run,
not just new ones, an event that was fully covered when it happened
surfaces as a NEW finding the next time role context refreshes and the
user's access no longer covers it. This is deliberate, not a bug - it's
exactly how the tool answers a real, owner-confirmed audit scenario
(2026-09-10): "show me everyone who ran a critical transaction in the
audit window, including anyone whose access has since changed." Every
finding's evidence names the role-refresh timestamp it was checked
against and the event's own timestamp, so an analyst (or auditor) can see
both "when it happened" and "as of when we know they no longer have it."

Wording is deliberately conservative: "not currently assigned via any
role" - never "not authorized" or "unauthorized." A tcode appearing in a
role's PFCG menu is not the same as full authorization-object-level
access (activity, org-level values aren't checked here) - overclaiming
precision in a security tool is worse than a slightly hedged finding.
"""
from ..catalogues import list_critical_transactions
from ..role_context import authorized_tcodes_for_user, directly_assigned_profiles, latest_refresh
from ._common import fetch_events

# Profiles assigned straight to a user's master record (SU01's own
# Profiles tab) bypass PFCG roles entirely and grant broad access no role
# menu shows - SAP_ALL is "everything," SAP_NEW is "everything newly
# released each SAP release," so either one directly assigned is worth
# calling out on its own, not just as a quiet possibility.
_BROAD_ACCESS_PROFILES = ("SAP_ALL", "SAP_NEW")

# SAP auto-generates one profile per PFCG role, conventionally named
# "T-<8 hex digits>", and SUSR_GET_PROFILES_OF_USER_RFC returns it exactly
# the same way it returns a profile assigned straight to the user's master
# record via SU01's own Profiles tab - the RFC has no "how did this user
# get this profile" field to tell the two apart. Requested directly after
# a live finding flagged a T-* profile as "directly assigned" when it was
# actually just the auto-generated profile for a role the user legitimately
# holds (already visible in the role-gap message above it). Excluding
# T-* here is a naming-convention heuristic, not a true role-to-profile
# relational check - the tool doesn't ingest SAP's actual role-to-profile
# mapping (a different RFC/table, not yet validated against a live
# system - see CLAUDE.md's rule against guessing SAP internals). SAP_ALL/
# SAP_NEW and any other custom-named profile are untouched by this filter.
_ROLE_GENERATED_PROFILE_PREFIX = "T-"


def _profile_note(system_id: str, user_id: str, profiles_cache: dict) -> tuple[str, dict]:
    """Live per-user profile lookup, requested directly: a role-only
    "out of context" finding shouldn't require a separate manual lookup to
    notice the user might have direct-profile access covering the same
    tcode anyway (see sal/role_context.py's "Directly-assigned profiles"
    docstring section for why this can't be bulk-synced ahead of time).
    Cached per user within one _detect() call - sync_findings() re-scans
    every retained event on every run, so without this cache the same
    user could trigger a live RFC call once per matching event instead of
    once per run.
    """
    key = (system_id, user_id)
    if key not in profiles_cache:
        profiles_cache[key] = directly_assigned_profiles(system_id, user_id)
    all_profiles, profiles_error = profiles_cache[key]
    # None (a failed lookup) is distinct from [] (checked, found nothing) -
    # the filter below must preserve that, not collapse both to [].
    profiles = (
        [p for p in all_profiles if not p.startswith(_ROLE_GENERATED_PROFILE_PREFIX)]
        if all_profiles is not None else None
    )

    broad = sorted(set(profiles or []) & set(_BROAD_ACCESS_PROFILES))
    if profiles_error:
        note = f"could not check for directly-assigned profiles ({profiles_error})"
    elif broad:
        note = (
            f"also has {' and '.join(broad)} assigned directly to their user master record "
            "(not via any role) - this alone may grant far broader access than the role gap above"
        )
    else:
        note = (
            "a profile assigned directly to their user master record (not via any role) "
            "could also be granting this access - not covered by the role check above"
        )
    evidence = {
        "directly_assigned_profiles": profiles,
        "directly_assigned_profiles_error": profiles_error,
        "has_broad_access_profile": bool(broad),
    }
    return note, evidence


def _detect(system_id, client, want_no_role_data: bool):
    critical = set(list_critical_transactions())
    if not critical:
        return []

    rows = fetch_events(msg_codes=["AU3"], system_id=system_id, client=client)
    findings = []
    authorized_cache: dict[tuple, set | None] = {}
    refresh_cache: dict[tuple, dict | None] = {}
    profiles_cache: dict[tuple, tuple] = {}

    for ev in rows:
        tcode = ev["transaction_code"]
        user_id = ev["user_id"]
        if not tcode or tcode not in critical or not user_id:
            continue

        ev_system = ev["source_system"]
        ev_client = ev["client"]

        user_key = (ev_system, ev_client, user_id)
        if user_key not in authorized_cache:
            authorized_cache[user_key] = authorized_tcodes_for_user(ev_system, ev_client, user_id)
        authorized = authorized_cache[user_key]

        if authorized is not None and tcode in authorized:
            continue  # covered by a current role - no finding

        is_no_role_data = authorized is None
        if is_no_role_data != want_no_role_data:
            continue

        refresh_key = (ev_system, ev_client)
        if refresh_key not in refresh_cache:
            refresh_cache[refresh_key] = latest_refresh(ev_system, ev_client)
        refresh = refresh_cache[refresh_key]
        refresh_at = (
            refresh["run_at"] if refresh and refresh["status"] in ("success", "success_truncated")
            else None
        )
        refresh_note = (
            f"checked against role data refreshed {refresh_at}" if refresh_at
            else "no successful role-context refresh has completed yet for this system"
        )

        profile_note, profile_evidence = _profile_note(ev_system, user_id, profiles_cache)

        if is_no_role_data:
            summary = (
                f"{user_id} ran {tcode} on {ev['event_timestamp']}, but currently has no "
                f"SAP role assignments on record at all ({refresh_note}); {profile_note}"
            )
        else:
            summary = (
                f"{user_id} ran {tcode} on {ev['event_timestamp']}, which is not currently "
                f"assigned via any of their SAP roles ({refresh_note}); {profile_note}"
            )

        findings.append({
            "rule": "out_of_context_no_role_data" if is_no_role_data else "out_of_context_transaction",
            "severity": "High",
            "user_id": user_id,
            "source_system": ev_system,
            "client": ev_client,
            "detected_at": ev["event_timestamp"],
            "summary": summary,
            "evidence": {
                "transaction_code": tcode,
                "event_timestamp": ev["event_timestamp"],
                "role_refresh_checked_at": refresh_at,
                "no_role_data": is_no_role_data,
                **profile_evidence,
            },
        })

    return findings


def detect_out_of_context_transactions(system_id=None, client=None):
    return _detect(system_id, client, want_no_role_data=False)


def detect_out_of_context_no_role_data(system_id=None, client=None):
    return _detect(system_id, client, want_no_role_data=True)
