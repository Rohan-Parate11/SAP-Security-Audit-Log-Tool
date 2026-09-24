"""Regression tests: GET /api/jobs and GET /api/jobs/<id> surface an
additive error_message_friendly field (sal/friendly_errors.py) alongside
the raw error_message, for a job whose error matches a known SAP error key.

Kept as its own small test file (rather than added to tests/test_api.py)
to avoid colliding with other concurrent work touching that same file
during this UAT round's resolution pass.
"""
from sal.web import create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_get_job_includes_friendly_error_when_recognized():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(
        job_id, "error", None,
        "RFC call 'RSAU_API_GET_LOG_DATA' failed on system 'S23': 3 (rc=3): "
        "key=TSV_TNEW_PAGE_ALLOC_FAILED, message=No more memory available to "
        "add rows to an internal table.",
    )
    client = _client()

    item = client.get(f"/api/jobs/{job_id}").get_json()["item"]
    assert item["error_message"]  # raw text is still present, unmodified
    assert item["error_message_friendly"] is not None
    assert "ran out of memory" in item["error_message_friendly"]["explanation"]
    assert "suggestion" in item["error_message_friendly"]

    listed = client.get("/api/jobs?system_id=S23&client=100&view=active").get_json()["items"]
    match = next(i for i in listed if i["id"] == job_id)
    assert match["error_message_friendly"] is not None


def test_get_job_friendly_error_is_none_for_unrecognized_error():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "error", None, "some totally novel failure text")
    client = _client()

    item = client.get(f"/api/jobs/{job_id}").get_json()["item"]
    assert item["error_message_friendly"] is None


def test_get_job_friendly_error_is_none_when_job_succeeded():
    import sal.jobs as jobs_svc

    job_id = jobs_svc.submit_job(system_id="S23", client="100", dat_from="20260101",
                                  dat_to="20260101", mode="adhoc", triggered_by="tester")
    jobs_svc._claim_next_queued_job()
    jobs_svc._finish_job(job_id, "success", "20260101", None)
    client = _client()

    item = client.get(f"/api/jobs/{job_id}").get_json()["item"]
    assert item["error_message_friendly"] is None
