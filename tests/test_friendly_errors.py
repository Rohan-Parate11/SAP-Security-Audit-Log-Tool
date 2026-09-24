"""Regression tests for sal/friendly_errors.py."""
import sal.friendly_errors as friendly_errors


def test_recognizes_the_exact_error_a_uat_tester_reported():
    raw = (
        "RFC call 'RSAU_API_GET_LOG_DATA' failed on system 'S23': 3 (rc=3): "
        "key=TSV_TNEW_PAGE_ALLOC_FAILED, message=No more memory available to "
        "add rows to an internal table. [MSG: class=, type=, number=, v1-4:=;;;]"
    )
    result = friendly_errors.friendly_error(raw)
    assert result is not None
    assert "ran out of memory" in result["explanation"]
    assert "narrower date range" in result["suggestion"]


def test_recognizes_communication_failure():
    raw = "RFC call 'RSAU_API_GET_LOG_DATA' failed on system 'S23': key=COMMUNICATION_FAILURE, message=..."
    result = friendly_errors.friendly_error(raw)
    assert result is not None
    assert "network connection" in result["explanation"]


def test_recognizes_logon_failure():
    raw = "Failed to connect to SAP system 'S23': key=LOGON_FAILURE, message=Logon failed"
    result = friendly_errors.friendly_error(raw)
    assert result is not None
    assert "rejected the logon" in result["explanation"]


def test_recognizes_time_out():
    raw = "RFC call 'RSAU_API_GET_LOG_DATA' failed on system 'S23': key=TIME_OUT, message=..."
    result = friendly_errors.friendly_error(raw)
    assert result is not None


def test_unknown_error_key_returns_none_rather_than_guessing():
    raw = "RFC call 'RSAU_API_GET_LOG_DATA' failed on system 'S23': key=SOME_NEW_UNSEEN_ERROR, message=..."
    assert friendly_errors.friendly_error(raw) is None


def test_message_with_no_key_at_all_returns_none():
    assert friendly_errors.friendly_error("A plain database is locked error") is None


def test_empty_or_none_message_returns_none():
    assert friendly_errors.friendly_error("") is None
    assert friendly_errors.friendly_error(None) is None
