"""Data retention & purge (owner-decided policy, 2026-09-09 - see Docs/Memory.md).

`events`: retained 365 days from event_timestamp, then purged - matches
what auditors actually request per the owner's own answer.
`findings` (the disposition-history record): retained 7 years (2555 days)
from first_seen_at, then purged - kept far longer than raw events since
disposition history has ongoing audit value after the underlying events
age out (SOX audit-trail standard, per owner confirmation). Deleting a
finding does not touch finding_whitelist - whitelist entries have their
own independent expires_at lifecycle already.

Deliberately NOT routed through sal/jobs.py's chunked event-collection
model - this is a simple, dateless bulk-delete on local SQLite data, not a
multi-day RFC pull. Runs on its own daily APScheduler job (registered
alongside the existing daily collection scheduler, at a different time -
see jobs.py - to avoid two unrelated writers touching the same tables at
once) and can also be triggered on demand from the Retention page. Every
run - whether it deletes anything or not - is logged to
retention_purge_runs, so "which data was purged, when" is always
answerable, not just previewable before the fact.

Cutoff format note: `events.event_timestamp` is written by
sal/collectors/sm20.py as a naive "YYYY-MM-DD HH:MM:SS" string (SAP's own
SAL_DATE/SAL_TIME, not yet confirmed to be UTC), while `findings.first_seen_at`
is written as `datetime.now(timezone.utc).isoformat()` (a "T" separator,
microseconds, and a "+00:00" suffix) - see sal/findings.py's sync_findings().
Both columns are compared with a plain SQL "<", which is lexical, not
chronological - it only agrees with chronological order when both sides
share the same string shape. events_cutoff below is therefore built with
strftime to match the collector's shape exactly (a mismatched cutoff here
previously caused every same-day row to be treated as eligible regardless
of time-of-day, over-purging by up to a day on every run - caught by
python-reviewer before shipping). findings_cutoff is left as .isoformat()
since first_seen_at already matches that shape.
"""
import logging
from datetime import datetime, timedelta, timezone

from .storage.db import get_connection, init_schema

logger = logging.getLogger(__name__)

EVENTS_RETENTION_DAYS = 365
FINDINGS_RETENTION_DAYS = 365 * 7


def _cutoffs() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    events_cutoff = (now - timedelta(days=EVENTS_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    findings_cutoff = (now - timedelta(days=FINDINGS_RETENTION_DAYS)).isoformat()
    return events_cutoff, findings_cutoff


def preview_purge() -> dict:
    """Counts of rows currently eligible for purge, without deleting
    anything - what the Retention page shows before any run happens.
    """
    init_schema()
    events_cutoff, findings_cutoff = _cutoffs()
    conn = get_connection()
    try:
        events_eligible = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE event_timestamp < ?", (events_cutoff,)
        ).fetchone()["c"]
        findings_eligible = conn.execute(
            "SELECT COUNT(*) c FROM findings WHERE first_seen_at < ?", (findings_cutoff,)
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "events_retention_days": EVENTS_RETENTION_DAYS,
        "findings_retention_days": FINDINGS_RETENTION_DAYS,
        "events_cutoff": events_cutoff,
        "events_eligible": events_eligible,
        "findings_cutoff": findings_cutoff,
        "findings_eligible": findings_eligible,
    }


def run_purge(actor: str = "system") -> dict:
    """Delete rows past their retention threshold and log the run.
    Always inserts a retention_purge_runs row, even if nothing was
    eligible - an empty run is still a recorded fact, not silence.
    """
    init_schema()
    now = datetime.now(timezone.utc).isoformat()
    events_cutoff, findings_cutoff = _cutoffs()
    conn = get_connection()
    try:
        events_deleted = conn.execute(
            "DELETE FROM events WHERE event_timestamp < ?", (events_cutoff,)
        ).rowcount
        findings_deleted = conn.execute(
            "DELETE FROM findings WHERE first_seen_at < ?", (findings_cutoff,)
        ).rowcount
        conn.execute(
            "INSERT INTO retention_purge_runs "
            "(run_at, actor, events_cutoff, events_deleted, findings_cutoff, findings_deleted) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, actor, events_cutoff, events_deleted, findings_cutoff, findings_deleted),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("Retention purge run by %s: %d events, %d findings deleted",
                actor, events_deleted, findings_deleted)
    return {
        "run_at": now, "actor": actor,
        "events_deleted": events_deleted, "findings_deleted": findings_deleted,
    }


def list_purge_runs(limit: int = 50) -> list[dict]:
    init_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM retention_purge_runs ORDER BY run_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
