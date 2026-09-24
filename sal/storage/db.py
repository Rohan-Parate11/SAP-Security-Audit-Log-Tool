"""SQLite-backed storage for normalized SAL events.

SQLite is deliberately used for the Stage 1 MVP: no server to stand up, single
file, good enough for a pilot's data volume. Swapping to Postgres/SQL Server
later only touches this module.
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sal.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    source_system     TEXT NOT NULL,
    client            TEXT NOT NULL,
    instance          TEXT NOT NULL,
    log_tstmp         TEXT NOT NULL,
    counter           INTEGER NOT NULL,
    event_timestamp   TEXT NOT NULL,
    user_id           TEXT,
    user_email        TEXT,
    msg_code          TEXT,
    area              TEXT,
    event_class       TEXT,
    severity          TEXT,
    transaction_code  TEXT,
    program           TEXT,
    terminal          TEXT,
    ip_address        TEXT,
    message           TEXT,
    param1            TEXT,
    param2            TEXT,
    param3            TEXT,
    collection_run_id TEXT,
    inserted_at       TEXT NOT NULL,
    PRIMARY KEY (source_system, client, instance, log_tstmp, counter)
);

CREATE INDEX IF NOT EXISTS idx_events_user_time ON events(user_id, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_events_class ON events(event_class);
CREATE INDEX IF NOT EXISTS idx_events_msg ON events(msg_code);
CREATE INDEX IF NOT EXISTS idx_events_ip ON events(ip_address);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id        TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    client        TEXT,
    dat_from      TEXT,
    dat_to        TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,
    row_count     INTEGER,
    error_message TEXT,
    filters_json  TEXT
);

CREATE TABLE IF NOT EXISTS critical_transactions (
    transaction_code TEXT PRIMARY KEY,
    description       TEXT,
    added_by          TEXT,
    added_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensitive_tables (
    table_name  TEXT PRIMARY KEY,
    description TEXT,
    added_by    TEXT,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sal_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at   TEXT NOT NULL,
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    source_system TEXT,
    client        TEXT,
    params_json   TEXT,
    result_count  INTEGER,
    outcome       TEXT NOT NULL DEFAULT 'ok'
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON sal_audit_log(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON sal_audit_log(actor, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON sal_audit_log(action);

CREATE TABLE IF NOT EXISTS findings (
    finding_key    TEXT PRIMARY KEY,
    rule_key       TEXT NOT NULL,
    rule_label     TEXT NOT NULL,
    severity       TEXT NOT NULL,
    source_system  TEXT,
    client         TEXT,
    user_id        TEXT,
    detected_at    TEXT NOT NULL,
    summary        TEXT NOT NULL,
    evidence_json  TEXT,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open',
    disposed_by    TEXT,
    disposed_at    TEXT,
    reason_code    TEXT,
    analyst_notes  TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_rule ON findings(rule_key);
CREATE INDEX IF NOT EXISTS idx_findings_user_time ON findings(user_id, detected_at);

CREATE TABLE IF NOT EXISTS finding_whitelist (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key      TEXT NOT NULL,
    source_system TEXT,
    client        TEXT,
    user_id       TEXT,
    reason        TEXT NOT NULL,
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_whitelist_rule ON finding_whitelist(rule_key, expires_at);

CREATE TABLE IF NOT EXISTS collection_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id           TEXT NOT NULL,
    client              TEXT,
    mode                TEXT NOT NULL,
    filters_json        TEXT,
    status              TEXT NOT NULL DEFAULT 'queued',
    triggered_by        TEXT NOT NULL,
    submitted_at        TEXT NOT NULL,
    started_at          TEXT,
    finished_at         TEXT,
    last_completed_date TEXT,
    error_message       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON collection_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_system ON collection_jobs(system_id, submitted_at);

-- Environment/connector registry (Blueprint v2, Phase E, pulled forward).
-- Metadata only - no credential field. Passwords stay in .env, keyed by
-- SAL_SAP_<system_id>_PASSWD, so the app's own database never becomes a
-- second place SAP credentials could leak from.
CREATE TABLE IF NOT EXISTS systems (
    system_id   TEXT PRIMARY KEY,
    environment TEXT NOT NULL,
    description TEXT,
    ashost      TEXT NOT NULL,
    sysnr       TEXT NOT NULL,
    client      TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_systems_environment ON systems(environment);

-- Central credential store (requested directly, 2026-09-16, answering the
-- HOME-02 open question - see Docs/Open_Questions_For_Review.txt). One row
-- per system that has had a password saved through the UI; a system with
-- no row here keeps resolving credentials from .env exactly as before
-- (coexistence, not a forced migration - the project owner's explicit
-- choice). encrypted_passwd is Fernet ciphertext (sal/credentials.py),
-- never plaintext - the encryption key itself lives in SAL_CREDENTIAL_
-- ENCRYPTION_KEY (.env), outside this database, for the same reason SAP
-- credentials themselves were kept out of it in the first place.
CREATE TABLE IF NOT EXISTS system_credentials (
    system_id        TEXT PRIMARY KEY,
    rfc_user         TEXT NOT NULL,
    encrypted_passwd TEXT NOT NULL,
    updated_by       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

-- SM19 audit-configuration snapshots (Blueprint v2, Phase D). One row per
-- check, not just current-state, so coverage gaps can be understood
-- historically, not just right now.
CREATE TABLE IF NOT EXISTS audit_config_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id         TEXT NOT NULL,
    client            TEXT,
    captured_at       TEXT NOT NULL,
    status            TEXT NOT NULL,
    enabled           INTEGER,
    raw_config_json   TEXT,
    parsed_slots_json TEXT,
    error_message     TEXT,
    actor             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_config_system ON audit_config_snapshots(system_id, captured_at);

-- Data retention purge log (owner-decided policy, 2026-09-09 - see
-- Docs/Memory.md). One row per run, even an empty one - "which data was
-- purged, when" must always be answerable after the fact.
CREATE TABLE IF NOT EXISTS retention_purge_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT NOT NULL,
    actor            TEXT NOT NULL,
    events_cutoff    TEXT NOT NULL,
    events_deleted   INTEGER NOT NULL,
    findings_cutoff  TEXT NOT NULL,
    findings_deleted INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retention_runs_time ON retention_purge_runs(run_at);

-- PFCG role assignments (Blueprint v2, Phase F). Raw AGR_USERS rows with
-- their own validity dates, not collapsed to "current only" - lets a
-- caller ask "is this valid as of date X" as a query filter rather than
-- forcing a separate snapshot-history table. Does NOT retain history of
-- REMOVED assignments (see Docs/Memory.md) - SAP deletes an AGR_USERS row
-- outright when a role is unassigned rather than leaving a historical
-- trace; TO_DAT is for *scheduled future* de-provisioning, not a
-- revocation log. Replaced wholesale on each refresh (see
-- sal/role_context.py), not additive - old rows for a system/client are
-- deleted and new ones inserted in the same transaction.
CREATE TABLE IF NOT EXISTS user_roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id   TEXT NOT NULL,
    client      TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    role_name   TEXT NOT NULL,
    from_dat    TEXT,
    to_dat      TEXT,
    captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(system_id, client, user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(system_id, client, role_name);

-- PFCG role -> authorized transaction code ("role menu"). Same
-- replace-wholesale-on-refresh model as user_roles. A tcode appearing
-- here means only that it's assigned via a role's menu - it does not
-- mean full authorization-object-level access was verified (activity,
-- org-level values aren't checked here) - see out_of_context_transaction
-- rule's own docstring for why its wording is deliberately conservative.
CREATE TABLE IF NOT EXISTS role_tcodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id   TEXT NOT NULL,
    client      TEXT NOT NULL,
    role_name   TEXT NOT NULL,
    tcode       TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_role_tcodes_role ON role_tcodes(system_id, client, role_name);
CREATE INDEX IF NOT EXISTS idx_role_tcodes_tcode ON role_tcodes(system_id, client, tcode);

-- Role-context refresh log (mirrors retention_purge_runs) - one row per
-- attempt, even a failed one, so "when did we last successfully learn
-- who has what role" is always answerable, not just assumed current.
CREATE TABLE IF NOT EXISTS role_context_refresh_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id       TEXT NOT NULL,
    client          TEXT,
    run_at          TEXT NOT NULL,
    actor           TEXT NOT NULL,
    status          TEXT NOT NULL,
    user_role_rows  INTEGER,
    role_tcode_rows INTEGER,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_role_context_runs ON role_context_refresh_runs(system_id, client, run_at);

-- Per-system daily-collection cadence (Blueprint v2, Phase G "Slice B").
-- One row per system that has ever had its cadence explicitly set - a
-- system with no row here falls back to the SAL_DAILY_COLLECTION_TIME env
-- var / 02:00 default (see sal/schedule.py's get_schedule()), so upgrading
-- an existing install never silently deregisters anyone's daily job.
-- interval_type is 'daily' (cron at anchor_hour:anchor_minute, once/day)
-- or 'interval' (every interval_hours hours via APScheduler's interval
-- trigger) - see sal/schedule.py for the validation that keeps these two
-- modes' fields mutually consistent before a row is ever written here.
-- anchor_hour/anchor_minute and interval_hours are mutually exclusive per
-- row (NULL for whichever mode - 'daily' or 'interval' - doesn't apply).
-- sal/schedule.py's set_schedule() is the only writer and validates this
-- before every write, but the CHECK below is real DB-level insurance
-- anyway (found in review) - unlike most of this schema's other tables,
-- a row that violated this here wouldn't just be bad data sitting inert:
-- register_daily_job() would hand it straight to APScheduler, and a NULL
-- anchor_hour/anchor_minute on a 'daily' row makes CronTrigger fire
-- roughly once a second against a live SAP system rather than erroring.
CREATE TABLE IF NOT EXISTS schedule_settings (
    system_id      TEXT PRIMARY KEY,
    interval_type  TEXT NOT NULL DEFAULT 'daily',
    anchor_hour    INTEGER,
    anchor_minute  INTEGER,
    interval_hours INTEGER,
    updated_by     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    CHECK (
        (interval_type = 'daily' AND anchor_hour IS NOT NULL AND anchor_minute IS NOT NULL
         AND interval_hours IS NULL)
        OR
        (interval_type = 'interval' AND interval_hours IS NOT NULL
         AND anchor_hour IS NULL AND anchor_minute IS NULL)
    )
);

-- Recurring FILTERED collection schedules (sal/filtered_schedule.py) -
-- deliberately separate from schedule_settings above: that table is one
-- row per system (the single comprehensive baseline cadence); this one is
-- many rows per system (any number of saved, independently-scheduled
-- filtered pulls), so it needs its own surrogate id rather than an
-- upsert-by-system_id shape. Same interval_type/anchor/interval CHECK
-- discipline as schedule_settings, for the identical reason (a malformed
-- row would otherwise reach APScheduler as CronTrigger(hour=None), which
-- fires roughly once a second against a live SAP system rather than
-- erroring). enabled lets a schedule be paused without deleting its saved
-- filter/cadence definition.
CREATE TABLE IF NOT EXISTS filtered_schedules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id        TEXT NOT NULL,
    client           TEXT,
    name             TEXT NOT NULL,
    user_filter      TEXT,
    transaction_code TEXT,
    report           TEXT,
    instance         TEXT,
    msg_code         TEXT,
    interval_type    TEXT NOT NULL DEFAULT 'daily',
    anchor_hour      INTEGER,
    anchor_minute    INTEGER,
    interval_hours   INTEGER,
    enabled          INTEGER NOT NULL DEFAULT 1,
    created_by       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_by       TEXT,
    updated_at       TEXT,
    CHECK (
        (interval_type = 'daily' AND anchor_hour IS NOT NULL AND anchor_minute IS NOT NULL
         AND interval_hours IS NULL)
        OR
        (interval_type = 'interval' AND interval_hours IS NOT NULL
         AND anchor_hour IS NULL AND anchor_minute IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_filtered_schedules_system ON filtered_schedules(system_id);
"""


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    # timeout=120 (Python's sqlite3 default is 5s): sync_findings() holds one
    # write transaction open for its whole run - no incremental commits - and
    # a full day's re-evaluation is documented elsewhere (sal/rules/registry.py)
    # at ~98s. This is writer-vs-writer contention, not reader-vs-writer: a
    # plain SELECT sees the pre-transaction on-disk snapshot instantly in
    # SQLite's default rollback-journal mode (no wait), but nearly every
    # route - including a plain GET, via its own audit.record() call at the
    # end - also writes, on its own connection, and only one writer can hold
    # the RESERVED/EXCLUSIVE lock at a time. With the old 5s default, that
    # second write raised an uncaught "database is locked" OperationalError
    # whenever it raced a sync/refresh/purge running anywhere near that long -
    # surfacing to the browser as an unexplained 500 (found via a UAT report:
    # intermittent 500 on GET /api/findings while navigating/switching
    # themes, which just happened to coincide with one of those still
    # running). 120s comfortably covers the documented worst case.
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


# Path init_schema() last ran a real CREATE/migration pass for, or None if it
# never has (this process). Every statement in init_schema() is idempotent
# (CREATE TABLE/INDEX IF NOT EXISTS, PRAGMA-checked ALTER TABLE), so calling
# it repeatedly was always *correct* - but it's also called at the top of
# ~28 read/write functions across the codebase, on the theory that any of
# them might be the first call of the process. Without this cache, each of
# those calls opens a fresh sqlite3 connection and re-runs the full schema
# script plus several PRAGMA table_info() migration checks, even long after
# startup when there is nothing left to create - measurable, compounding
# overhead on hot paths like the dashboard, which fans out into dozens of
# calls per request via catalogue seeding.
#
# Keyed on the current DB_PATH value (not a bare "did this ever run" flag)
# because tests/conftest.py's isolated_db fixture monkeypatches DB_PATH to a
# brand-new tmp_path file for every single test function and then calls
# init_schema() itself - a global "ran once" flag would skip real schema
# creation for every test after the first and break the suite with "no such
# table" errors. Comparing against DB_PATH each call means a changed path
# (new test, or a real path change) always gets a real init pass.
_schema_ready_for: Path | None = None


def init_schema() -> None:
    global _schema_ready_for
    if _schema_ready_for == DB_PATH:
        return
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "collection_runs", "filters_json", "TEXT")
        _ensure_column(conn, "collection_runs", "actor", "TEXT")
        _ensure_column(conn, "collection_jobs", "days_completed", "INTEGER")
        _ensure_column(conn, "collection_jobs", "days_total", "INTEGER")
        _ensure_column(conn, "collection_jobs", "job_name", "TEXT")
        _ensure_column(conn, "collection_jobs", "job_description", "TEXT")
        # Priority (Blueprint v2 Phase G, "SM36/SM37 parity") - mirrors SAP's
        # own SM36 Job Class (A=High, B=Medium, C=Low): the single worker
        # thread claims queued jobs in job_class order (A before B before C)
        # before falling back to submission order, so the unfiltered
        # detection-feed baseline (submitted at job_class='A') can't get
        # stuck behind a pile of ad-hoc requests. DEFAULT 'B' backfills
        # every pre-existing row as Medium, matching what ad-hoc jobs
        # already defaulted to before this column existed.
        _ensure_column(conn, "collection_jobs", "job_class", "TEXT NOT NULL DEFAULT 'B'")
        # Job-level soft-delete (Recovery tab) - separate from and
        # independent of collection_runs' own soft-delete (Slice A): this
        # hides/restores the collection_jobs row itself (the submission/
        # tracking record), never the events/findings it helped collect
        # nor the collection_runs rows it produced, which keep their own
        # independent lifecycle. A queued/running job can't be deleted
        # (enforced in sal/web/api.py's delete_job()) - the worker thread
        # still needs that row untouched while it's actively claimed.
        _ensure_column(conn, "collection_jobs", "deleted_at", "TEXT")
        _ensure_column(conn, "collection_jobs", "deleted_by", "TEXT")
        _ensure_column(conn, "collection_jobs", "delete_reason", "TEXT")
        # Traces a per-day chunk back to the collection_jobs row that
        # spawned it, so "Recent collection runs" can show the job name/
        # description alongside each run - collection_runs never had this
        # link (a run only ever knew its own dat_from/dat_to/filters_json,
        # not which job it belonged to). NULL for runs predating this
        # column and for scripts/collect_sm20.py's CLI backfill path,
        # which deliberately bypasses sal/jobs.py entirely.
        _ensure_column(conn, "collection_runs", "job_id", "INTEGER")
        # Soft-delete (2026-09-13) - a run can be hidden from "Collection
        # History" and later restored, both actions requiring a reason
        # (see sal/web/api.py's delete_collection_run/restore_collection_run).
        # Deliberately never a hard DELETE: the row is metadata about a pull
        # that happened, not the collected SAP data itself (events are keyed
        # by their own (source_system, client, instance, log_tstmp, counter),
        # not by collection_run_id), so soft-delete costs nothing and keeps
        # the action recoverable on an auditor-facing tool.
        _ensure_column(conn, "collection_runs", "deleted_at", "TEXT")
        _ensure_column(conn, "collection_runs", "deleted_by", "TEXT")
        _ensure_column(conn, "collection_runs", "delete_reason", "TEXT")
        conn.commit()
    finally:
        conn.close()
    _schema_ready_for = DB_PATH
