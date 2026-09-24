"""Regression tests for sal/role_context.py (Blueprint v2, Phase F).

_fetch_role_context() is monkeypatched throughout - these tests target the
storage/replace/lookup/timeout/in-flight logic, not a live RFC call.
RFC_READ_TABLE against AGR_USERS/AGR_TCODES was validated live against S23
during Phase F planning; that validation is not repeated by these tests.

user_access_summary()'s directly-assigned-profile lookup (added 2026-09-13)
is tested the same way: _fetch_user_profiles()/_run_profile_fetch_with_timeout()
monkeypatched, not a live SUSR_GET_PROFILES_OF_USER_RFC call - that RFC was
validated live against S23 in scripts/probes/probe_user_master.py and again
during this feature's own investigation.
"""
import concurrent.futures
from datetime import date, timedelta

import sal.role_context as role_context


def _fake_config(system_id):
    return {"client": "100"}


def _returns(user_roles=None, role_tcodes=None, truncated=False):
    return lambda system_id: (user_roles or [], role_tcodes or [], truncated)


def test_sync_role_context_success_stores_rows_and_returns_counts(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_ROLE_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_ROLE_A", "TCODE": "SU01"}],
        ),
    )

    result = role_context.sync_role_context("s23", actor="tester")

    assert result["status"] == "success"
    assert result["system_id"] == "S23"
    assert result["user_role_rows"] == 1
    assert result["role_tcode_rows"] == 1
    assert role_context.authorized_tcodes_for_user("S23", "100", "U1") == {"SU01"}


def test_sync_role_context_replaces_stale_data_not_merges(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_OLD", "FROM_DAT": "20200101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_OLD", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_NEW", "FROM_DAT": "20260101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_NEW", "TCODE": "PFCG"}],
        ),
    )
    role_context.sync_role_context("S23")

    # The old role's tcode (SU01) must no longer be authorized - the
    # refresh replaces this system/client's rows wholesale, not additively.
    assert role_context.authorized_tcodes_for_user("S23", "100", "U1") == {"PFCG"}


def test_sync_role_context_failed_fetch_leaves_existing_data_untouched(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_ROLE_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_ROLE_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    def _boom(system_id):
        raise RuntimeError("RFC connection failed")

    monkeypatch.setattr(role_context, "_fetch_role_context", _boom)
    result = role_context.sync_role_context("S23", actor="tester")

    assert result["status"] == "error"
    assert "RFC connection failed" in result["error"]
    # A failed fetch must never touch the database - the previous
    # successful refresh's data must still be intact.
    assert role_context.authorized_tcodes_for_user("S23", "100", "U1") == {"SU01"}

    runs = role_context.list_refresh_runs("S23", "100")
    assert [r["status"] for r in runs] == ["error", "success"]


def test_sync_role_context_unconfigured_system_still_logs_a_run(monkeypatch):
    # config.sap_system_config() itself failing (an unconfigured system)
    # happens before `client` is known - the run must still be logged,
    # with a null client rather than crashing or silently vanishing.
    def _unconfigured(system_id):
        raise RuntimeError(f"Missing required environment variable(s) for SAP system '{system_id}'")

    monkeypatch.setattr(role_context.config, "sap_system_config", _unconfigured)

    result = role_context.sync_role_context("S99", actor="tester")

    assert result["status"] == "error"
    assert "Missing required" in result["error"]
    runs = role_context.list_refresh_runs("S99")
    assert len(runs) == 1
    assert runs[0]["client"] is None
    assert "S99" not in role_context._inflight  # must not leak the in-flight guard


def test_sync_role_context_rejects_duplicate_in_flight_refresh(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_inflight", {"S23"})

    result = role_context.sync_role_context("S23", actor="tester")

    assert result["status"] == "error"
    assert "already in progress" in result["error"]


def test_sync_role_context_truncation_is_reported_not_silently_success(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_A", "TCODE": "SU01"}],
            truncated=True,
        ),
    )

    result = role_context.sync_role_context("S23")

    assert result["status"] == "success_truncated"
    latest = role_context.latest_refresh("S23", "100")
    assert latest["status"] == "success_truncated"


def test_read_table_all_skips_malformed_rows_without_misaligning_fields(monkeypatch):
    # A row with fewer/more delimited values than expected fields must be
    # dropped, never zipped into the wrong columns.
    class _FakeConn:
        def call(self, fname, **kwargs):
            return {"DATA": [
                {"WA": "U1|Z_GOOD|20250101|99991231"},   # well-formed
                {"WA": "U2|Z_SHORT|20250101"},             # missing TO_DAT - malformed
                {"WA": "U3|Z_ALSO_GOOD|20250101|99991231"},
            ]}

    rows, truncated = role_context._read_table_all(_FakeConn(), "AGR_USERS", role_context._USER_ROLES_FIELDS)

    assert truncated is False
    assert len(rows) == 2
    assert {r["UNAME"] for r in rows} == {"U1", "U3"}
    assert all(r["TO_DAT"] == "99991231" for r in rows)  # no field-shifted garbage


def test_authorized_tcodes_for_user_returns_none_when_zero_role_rows(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_fetch_role_context", _returns())
    role_context.sync_role_context("S23")

    assert role_context.authorized_tcodes_for_user("S23", "100", "GHOST_USER") is None


def test_authorized_tcodes_for_user_returns_empty_set_not_none_when_role_expired(monkeypatch):
    # A role row that's simply past its own scheduled TO_DAT is NOT the
    # same as "zero role data" - the user has role history on record,
    # it's just not currently valid. This distinction is what lets the
    # detection rule tell "no data at all" apart from "roles exist, don't
    # cover this tcode" (see sal/rules/out_of_context_transaction.py).
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_EXPIRED", "FROM_DAT": "20200101", "TO_DAT": yesterday}],
            role_tcodes=[{"AGR_NAME": "Z_EXPIRED", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    authorized = role_context.authorized_tcodes_for_user("S23", "100", "U1")
    assert authorized == set()
    assert authorized is not None


def test_authorized_tcodes_for_user_ignores_future_dated_role(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y%m%d")
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_FUTURE", "FROM_DAT": tomorrow, "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_FUTURE", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    assert role_context.authorized_tcodes_for_user("S23", "100", "U1") == set()


def test_authorized_tcodes_for_user_normalizes_system_id(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    assert role_context.authorized_tcodes_for_user("s23", "100", "U1") == {"SU01"}


def test_authorized_tcodes_for_user_matches_any_client_when_none_given(monkeypatch):
    # python-reviewer caught this during the user_access_summary() review:
    # the query used to hardcode "client = ?", so a None client (SQL NULL)
    # never matched anything and silently looked like "no role data" -
    # matching role_context_counts()/latest_refresh()'s existing
    # conditional-clause convention instead.
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    assert role_context.authorized_tcodes_for_user("S23", None, "U1") == {"SU01"}


def test_role_context_counts_are_distinct_not_row_totals(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[
                {"UNAME": "U1", "AGR_NAME": "Z_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"},
                {"UNAME": "U2", "AGR_NAME": "Z_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"},
            ],
            role_tcodes=[{"AGR_NAME": "Z_A", "TCODE": "SU01"}, {"AGR_NAME": "Z_A", "TCODE": "PFCG"}],
        ),
    )
    role_context.sync_role_context("S23")

    assert role_context.role_context_counts("S23", "100") == {"users": 2, "roles": 1, "tcodes": 2}


def test_latest_refresh_returns_most_recent_run(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_fetch_role_context", _returns())
    role_context.sync_role_context("S23", actor="first")
    role_context.sync_role_context("S23", actor="second")

    latest = role_context.latest_refresh("S23", "100")
    assert latest["actor"] == "second"


def test_user_access_summary_combines_roles_tcodes_and_profiles(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_ROLE_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_ROLE_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")
    monkeypatch.setattr(role_context, "_fetch_user_profiles", lambda system_id, user_id: ["SAP_ALL", "Z_CUSTOM"])

    result = role_context.user_access_summary("S23", "100", "U1")

    assert result["has_role_data"] is True
    assert result["roles"] == ["Z_ROLE_A"]
    assert result["tcodes_via_roles"] == ["SU01"]
    assert result["profiles"] == ["SAP_ALL", "Z_CUSTOM"]
    assert result["profiles_error"] is None


def test_user_access_summary_normalizes_user_id_case(monkeypatch):
    # SAP usernames (AGR_USERS.UNAME) are stored uppercase - a lowercase
    # lookup must still match, not silently look like "no role data"
    # (security-reviewer caught this during this feature's own review).
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_ROLE_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_ROLE_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")
    seen_user_id = {}
    monkeypatch.setattr(
        role_context, "_fetch_user_profiles",
        lambda system_id, user_id: seen_user_id.setdefault("value", user_id) and ["SAP_ALL"],
    )

    result = role_context.user_access_summary("S23", "100", "u1")

    assert result["has_role_data"] is True
    assert result["roles"] == ["Z_ROLE_A"]
    assert seen_user_id["value"] == "U1"  # normalized before the RFC call too


def test_user_access_summary_no_role_data_still_returns_profiles(monkeypatch):
    # The exact real-world scenario this feature exists for: a user with
    # zero PFCG role/role-menu data on record can still have a directly
    # assigned profile (e.g. SAP_ALL) - the profile lookup must not be
    # gated on role data existing at all.
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_fetch_role_context", _returns())
    role_context.sync_role_context("S23")
    monkeypatch.setattr(role_context, "_fetch_user_profiles", lambda system_id, user_id: ["SAP_ALL"])

    result = role_context.user_access_summary("S23", "100", "GHOST_USER")

    assert result["has_role_data"] is False
    assert result["roles"] == []
    assert result["tcodes_via_roles"] == []
    assert result["profiles"] == ["SAP_ALL"]
    assert result["profiles_error"] is None


def test_user_access_summary_profile_fetch_error_does_not_hide_role_data(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(
        role_context, "_fetch_role_context",
        _returns(
            user_roles=[{"UNAME": "U1", "AGR_NAME": "Z_ROLE_A", "FROM_DAT": "20250101", "TO_DAT": "99991231"}],
            role_tcodes=[{"AGR_NAME": "Z_ROLE_A", "TCODE": "SU01"}],
        ),
    )
    role_context.sync_role_context("S23")

    def _boom(system_id, user_id):
        raise RuntimeError("USER_NOT_EXISTS")

    monkeypatch.setattr(role_context, "_fetch_user_profiles", _boom)

    result = role_context.user_access_summary("S23", "100", "U1")

    assert result["roles"] == ["Z_ROLE_A"]
    assert result["tcodes_via_roles"] == ["SU01"]
    assert result["profiles"] is None
    assert "USER_NOT_EXISTS" in result["profiles_error"]


def test_user_access_summary_profile_timeout_reported_not_raised(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_fetch_role_context", _returns())
    role_context.sync_role_context("S23")

    def _raise_timeout(system_id, user_id, timeout):
        # Real _run_profile_fetch_with_timeout only clears _profile_inflight
        # via its done-callback, which never fires here since the wrapper
        # itself is replaced - do it manually, matching
        # test_audit_config.py's identical timeout-test pattern.
        role_context._profile_inflight.discard((system_id, user_id))
        raise concurrent.futures.TimeoutError()

    monkeypatch.setattr(role_context, "_run_profile_fetch_with_timeout", _raise_timeout)

    result = role_context.user_access_summary("S23", "100", "U1")

    assert result["profiles"] is None
    assert "Timed out" in result["profiles_error"]


def test_user_access_summary_rejects_duplicate_in_flight_profile_lookup(monkeypatch):
    monkeypatch.setattr(role_context.config, "sap_system_config", _fake_config)
    monkeypatch.setattr(role_context, "_fetch_role_context", _returns())
    role_context.sync_role_context("S23")
    monkeypatch.setattr(role_context, "_profile_inflight", {("S23", "U1")})

    result = role_context.user_access_summary("S23", "100", "U1")

    assert result["profiles"] is None
    assert "already in progress" in result["profiles_error"]
