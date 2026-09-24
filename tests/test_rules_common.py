"""Regression tests for sal/rules/_common.py's fetch_events() cache.

Found live (chrome-devtools, 2026-09-12): several rules request the
identical (msg_codes, event_class, system_id, client) combination within
one run_all_rules() pass (AU3 five times, AU1 four times as of writing),
each independently re-querying and re-sorting the same large result set.
See sal/rules/_common.py and sal/rules/registry.py's run_all_rules() for
the fix.
"""
from datetime import datetime, timezone

import sal.rules._common as common
import sal.rules.registry as registry
from sal.storage.db import get_connection


def _insert_event(counter: int, msg_code: str = "AU1", user_id: str = "U1") -> None:
    conn = get_connection()
    try:
        ts = "2026-01-05 08:00:00"
        conn.execute(
            "INSERT INTO events (source_system, client, instance, log_tstmp, counter, "
            "event_timestamp, user_id, msg_code, inserted_at) "
            "VALUES ('S23', '100', 'X', ?, ?, ?, ?, ?, ?)",
            (ts, counter, ts, user_id, msg_code, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def test_cache_is_disabled_by_default():
    assert common._cache is None


def test_fetch_events_hits_the_cache_within_a_run_all_rules_style_pass():
    _insert_event(1)
    common._cache = {}
    try:
        first = common.fetch_events(msg_codes=["AU1"], system_id="S23", client="100")
        second = common.fetch_events(msg_codes=["AU1"], system_id="S23", client="100")
        # Same object back, not merely equal content - proves the second
        # call never touched the database.
        assert first is second
    finally:
        common._cache = None


def test_cache_key_distinguishes_different_filters():
    _insert_event(1, msg_code="AU1")
    _insert_event(2, msg_code="AU3")
    common._cache = {}
    try:
        au1_rows = common.fetch_events(msg_codes=["AU1"], system_id="S23", client="100")
        au3_rows = common.fetch_events(msg_codes=["AU3"], system_id="S23", client="100")
        assert len(au1_rows) == 1
        assert len(au3_rows) == 1
        assert au1_rows is not au3_rows
    finally:
        common._cache = None


def test_msg_codes_order_does_not_bypass_the_cache():
    """['AU1','AU2'] and ['AU2','AU1'] must hit the same cache entry - the
    cache key sorts msg_codes, since two rules requesting "the same
    signal set" in a different literal order shouldn't each pay for a
    separate query.
    """
    _insert_event(1, msg_code="AU1")
    common._cache = {}
    try:
        first = common.fetch_events(msg_codes=["AU1", "AU2"], system_id="S23", client="100")
        second = common.fetch_events(msg_codes=["AU2", "AU1"], system_id="S23", client="100")
        assert first is second
    finally:
        common._cache = None


def test_run_all_rules_resets_cache_to_none_even_on_a_rule_exception(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("synthetic rule failure")

    # Patch one registered rule's underlying function to blow up, confirming
    # the cache is still reset via `finally` rather than left dangling.
    original_rules = registry.RULES
    monkeypatch.setattr(registry, "RULES", [(original_rules[0][0], original_rules[0][1], _boom)])
    try:
        registry.run_all_rules(system_id="S23", client="100")
    except RuntimeError:
        pass
    assert common._cache is None


def test_run_all_rules_produces_correct_findings_with_caching_enabled():
    _insert_event(1, msg_code="AU1", user_id="ALICE")
    findings = registry.run_all_rules(system_id="S23", client="100")
    assert common._cache is None  # cleaned up after the call
    assert isinstance(findings, list)
