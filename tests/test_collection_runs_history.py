"""Regression tests for Slice A: collection-run pagination/search/soft-delete.

Covers sal/web/api.py's rewritten collection_runs() (limit/offset/filters/
total, default-excludes soft-deleted rows) and the new
delete_collection_run()/restore_collection_run() endpoints - both require a
reason (auditor-facing tool - every removal from or return to Collection
History must be justified and attributable), and delete refuses a run
that's still in progress by checking not just the target row's own status
but every sibling row under the same job_id and the parent job itself (a
wide job chunks into one collection_runs row per day - see
sal/web/api.py's delete_collection_run docstring).
"""
from sal import audit
from sal.storage.db import get_connection
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def _insert_run(conn, run_id, started_at, status="success", job_id=None,
                 source_system="S23", client="100"):
    conn.execute(
        "INSERT INTO collection_runs (run_id, source_system, client, dat_from, dat_to, "
        "started_at, status, job_id) VALUES (?, ?, ?, '20260101', '20260101', ?, ?, ?)",
        (run_id, source_system, client, started_at, status, job_id),
    )


def _insert_job(conn, status="success", mode="adhoc"):
    cur = conn.execute(
        "INSERT INTO collection_jobs (system_id, client, mode, status, triggered_by, submitted_at) "
        "VALUES ('S23', '100', ?, ?, 'tester', '2026-01-01T00:00:00+00:00')",
        (mode, status),
    )
    return cur.lastrowid


def test_collection_runs_paginates_and_reports_total():
    conn = get_connection()
    try:
        for i in range(25):
            _insert_run(conn, f"run-{i}", f"2026-01-{i + 1:02d}T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()

    data = _client().get("/api/collection-runs?system_id=S23&client=100&limit=10&offset=0").get_json()

    assert data["total"] == 25
    assert len(data["items"]) == 10
    assert data["items"][0]["run_id"] == "run-24"  # newest first, unaffected by pagination


def test_collection_runs_filters_by_status_and_date_range():
    conn = get_connection()
    try:
        _insert_run(conn, "run-a", "2026-01-01T00:00:00+00:00", status="error")
        _insert_run(conn, "run-b", "2026-01-05T00:00:00+00:00", status="success")
        _insert_run(conn, "run-c", "2026-02-01T00:00:00+00:00", status="success")
        conn.commit()
    finally:
        conn.close()

    resp = _client().get(
        "/api/collection-runs?system_id=S23&client=100&status=success"
        "&date_from=2026-01-01&date_to=2026-01-31"
    )
    items = resp.get_json()["items"]

    assert [item["run_id"] for item in items] == ["run-b"]


def test_collection_runs_filters_by_job_name_and_mode():
    conn = get_connection()
    try:
        job_id = _insert_job(conn, mode="scheduled")
        conn.execute(
            "UPDATE collection_jobs SET job_name = 'Weekly SU01 spot-check' WHERE id = ?", (job_id,)
        )
        _insert_run(conn, "run-named", "2026-01-01T00:00:00+00:00", job_id=job_id)
        _insert_run(conn, "run-unnamed", "2026-01-02T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()
    client = _client()

    by_name = client.get("/api/collection-runs?system_id=S23&client=100&job_name=SU01").get_json()
    assert [item["run_id"] for item in by_name["items"]] == ["run-named"]

    by_mode = client.get("/api/collection-runs?system_id=S23&client=100&mode=scheduled").get_json()
    assert [item["run_id"] for item in by_mode["items"]] == ["run-named"]


def test_collection_runs_accepts_repeated_query_param_for_multi_value_status_and_mode():
    """Excel-style column-header filters (Recovery's "Deleted collection
    runs" panel) check multiple boxes at once - mode/status must each
    accept several values via a repeated query-string key, not just one."""
    conn = get_connection()
    try:
        scheduled_job = _insert_job(conn, mode="scheduled")
        adhoc_job = _insert_job(conn, mode="adhoc")
        _insert_run(conn, "run-a", "2026-01-01T00:00:00+00:00", status="error", job_id=scheduled_job)
        _insert_run(conn, "run-b", "2026-01-02T00:00:00+00:00", status="success", job_id=adhoc_job)
        _insert_run(conn, "run-c", "2026-01-03T00:00:00+00:00", status="running", job_id=adhoc_job)
        conn.commit()
    finally:
        conn.close()

    by_status = _client().get(
        "/api/collection-runs?system_id=S23&client=100&status=error&status=success"
    ).get_json()
    assert {item["run_id"] for item in by_status["items"]} == {"run-a", "run-b"}

    by_mode = _client().get(
        "/api/collection-runs?system_id=S23&client=100&mode=scheduled&mode=adhoc"
    ).get_json()
    assert {item["run_id"] for item in by_mode["items"]} == {"run-a", "run-b", "run-c"}


def test_collection_runs_date_range_filter_works_with_realistic_microsecond_timestamps():
    """Regression test: started_at is written as
    datetime.now(timezone.utc).isoformat() in production (microseconds and
    a "+00:00" suffix - see sal/collectors/sm20.py), not the clean
    "...T00:00:00+00:00" shape other tests use. The date_from/date_to
    filter must compare this as a lexical string range (see
    collection_runs()'s own comment on why), not via SQLite's date()/time()
    parsing - which silently returns NULL (and thus zero matching rows) on
    a stored value with microseconds + an offset suffix on any SQLite
    build older than 3.42.
    """
    conn = get_connection()
    try:
        _insert_run(conn, "run-in-range", "2026-03-15T13:45:07.123456+00:00")
        _insert_run(conn, "run-before", "2026-03-01T23:59:59.999999+00:00")
        _insert_run(conn, "run-after", "2026-04-01T00:00:00.000001+00:00")
        conn.commit()
    finally:
        conn.close()

    resp = _client().get(
        "/api/collection-runs?system_id=S23&client=100&date_from=2026-03-10&date_to=2026-03-20"
    )
    items = resp.get_json()["items"]

    assert [item["run_id"] for item in items] == ["run-in-range"]


def test_collection_runs_rejects_malformed_date_filters_and_job_id():
    bad_date_from = _client().get("/api/collection-runs?date_from=03/10/2026")
    assert bad_date_from.status_code == 400

    bad_date_to = _client().get("/api/collection-runs?date_to=2026-02-30")
    assert bad_date_to.status_code == 400

    bad_job_id = _client().get("/api/collection-runs?job_id=not-a-number")
    assert bad_job_id.status_code == 400


def test_collection_runs_job_id_filter_scopes_to_one_job():
    conn = get_connection()
    try:
        job_id = _insert_job(conn)
        _insert_run(conn, "run-in-job", "2026-01-01T00:00:00+00:00", job_id=job_id)
        _insert_run(conn, "run-other", "2026-01-02T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()

    items = _client().get(f"/api/collection-runs?job_id={job_id}").get_json()["items"]

    assert [item["run_id"] for item in items] == ["run-in-job"]


def test_delete_collection_run_requires_reason():
    conn = get_connection()
    try:
        _insert_run(conn, "run-x", "2026-01-01T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()

    resp = _client().delete("/api/collection-runs/run-x", json={})

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_delete_collection_run_rejects_running_row():
    conn = get_connection()
    try:
        _insert_run(conn, "run-running", "2026-01-01T00:00:00+00:00", status="running")
        conn.commit()
    finally:
        conn.close()

    resp = _client().delete("/api/collection-runs/run-running", json={"reason": "test"})

    assert resp.status_code == 409


def test_delete_collection_run_rejects_when_parent_job_still_running():
    conn = get_connection()
    try:
        job_id = _insert_job(conn, status="running")
        _insert_run(conn, "run-day1", "2026-01-01T00:00:00+00:00", status="success", job_id=job_id)
        conn.commit()
    finally:
        conn.close()

    resp = _client().delete("/api/collection-runs/run-day1", json={"reason": "test"})

    assert resp.status_code == 409


def test_delete_collection_run_rejects_when_sibling_row_still_running():
    """A wide job chunks into one collection_runs row per day - a finished
    day-1 row must not be deletable while day-2 of the *same* job_id is
    still running, even though the target row's own status is 'success'
    and the parent collection_jobs row (created separately here) isn't
    checked as 'running' in this scenario - the sibling-row check is what
    catches it.
    """
    conn = get_connection()
    try:
        job_id = _insert_job(conn, status="running")
        _insert_run(conn, "run-day1", "2026-01-01T00:00:00+00:00", status="success", job_id=job_id)
        _insert_run(conn, "run-day2", "2026-01-02T00:00:00+00:00", status="running", job_id=job_id)
        conn.commit()
    finally:
        conn.close()

    resp = _client().delete("/api/collection-runs/run-day1", json={"reason": "test"})

    assert resp.status_code == 409


def test_delete_collection_run_soft_deletes_with_reason_and_is_recoverable():
    conn = get_connection()
    try:
        _insert_run(conn, "run-del", "2026-01-01T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()
    client = _client()

    resp = client.delete("/api/collection-runs/run-del", json={"reason": "duplicate pull"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    active = client.get("/api/collection-runs?system_id=S23&client=100").get_json()["items"]
    assert active == []

    deleted = client.get(
        "/api/collection-runs?system_id=S23&client=100&view=deleted"
    ).get_json()["items"]
    assert deleted[0]["run_id"] == "run-del"
    assert deleted[0]["delete_reason"] == "duplicate pull"
    assert deleted[0]["deleted_by"]

    total, entries = audit.list_entries(action="collection_run_delete")
    assert total == 1
    assert '"reason": "duplicate pull"' in entries[0]["params_json"]


def test_restore_collection_run_requires_reason_and_only_restores_deleted_rows():
    conn = get_connection()
    try:
        _insert_run(conn, "run-active", "2026-01-01T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()
    client = _client()

    missing = client.post("/api/collection-runs/does-not-exist/restore", json={"reason": "oops"})
    assert missing.status_code == 404

    not_deleted = client.post("/api/collection-runs/run-active/restore", json={"reason": "oops"})
    assert not_deleted.status_code == 404

    client.delete("/api/collection-runs/run-active", json={"reason": "test"})

    no_reason = client.post("/api/collection-runs/run-active/restore", json={})
    assert no_reason.status_code == 400

    restored = client.post(
        "/api/collection-runs/run-active/restore", json={"reason": "was needed after all"}
    )
    assert restored.status_code == 200

    active = client.get("/api/collection-runs?system_id=S23&client=100").get_json()["items"]
    assert [item["run_id"] for item in active] == ["run-active"]

    total, _entries = audit.list_entries(action="collection_run_restore")
    assert total == 1
