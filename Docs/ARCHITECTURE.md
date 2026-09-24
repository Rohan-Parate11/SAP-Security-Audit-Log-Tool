# SAL Architecture

Living, code-derived architecture reference. `Docs/SAL_Architecture_Blueprint_v2.docx`
is the external consulting document (the roadmap and rationale); this file
describes what the running code actually does, kept current as the code changes.

Related: `PRD.md` (product requirements), `Phases.md` (delivery status),
`Rules.md` (detection rule catalog), `Design.md` (UI/UX design system),
`Memory.md` (durable decisions/lessons).

## Module map

```
sal/
  config.py          env-var loading (.env), SDK path setup - must load before pyrfc
  sap_connector/      RFC connection wrapper (SapConnection context manager)
  collectors/sm20.py  SM20 event extraction via RSAU_API_GET_LOG_DATA; collect_and_store()
  rules/              10 deterministic detection rules + registry.run_all_rules()
  findings.py         findings persistence, disposition, time-bound whitelisting
  jobs.py             job execution: chunking, retries, daily scheduler, worker thread
  systems.py          environment/connector registry (Development/Quality/Production/Sandbox)
  sla.py              business-day SLA classification for open findings
  audit_config.py     SM19 audit-config visibility - direct timeout-bounded RFC call, not a job
  rules/_coverage.py  rule -> SM19 event-class mapping (see Rules.md)
  retention.py         data retention purge (events 1yr, findings 7yr) - direct call, not a job
  role_context.py      PFCG role/tcode ingestion (Phase F) - direct call, not a job
  export.py           CSV/XLSX serialization
  itgc_report.py       ITGC-formatted findings workbook (cover sheet, control
                        matrix, workpaper, extraction log) - see CHANGELOG.md
  rules_catalog.py      plain-English detection-rules reference workbook
  xlsx_style.py          shared openpyxl styling for itgc_report/rules_catalog
  catalogues.py        critical-transaction / sensitive-table catalogues
  audit.py            application-level audit log (attribution, not access control)
  storage/db.py       SQLite schema + connection, no ORM
  web/                Flask app factory, JSON API (api.py), templates, static (app.js/css)
```

One small, focused module per concern - `findings.py`, `jobs.py`, `systems.py`,
`sla.py` each own one thing. New RFC-facing modules should follow the same
split: a thin collector/caller + a persistence layer, not one large file.

## Data flow

```
Live SAP (RFC) --collect_and_store()--> events table --run_all_rules()-->
  computed findings --sync_findings()--> findings table --dispose/whitelist-->
  analyst decisions --dashboard/export/SLA--> UI
```

- **Collection** happens three ways: the ad-hoc "Collect" UI form, a daily
  APScheduler job per system (both go through `sal/jobs.py`'s chunked
  job runner), and `scripts/collect_sm20.py` (a direct, unchunked CLI path
  for manual backfills - deliberately bypasses the job runner).
- **Detection** is deterministic only - 10 rules in `sal/rules/`, each
  filtering `events` by message code/event class/transaction code. No
  ML/LLM layer exists (Phase H, not started).
- **Persistence**: `sync_findings()` gives each computed finding a stable
  hash identity (rule_key + system + client + user + detected_at + stable
  evidence) so disposition/whitelist survive re-syncs. See `sal/findings.py`'s
  docstring for two documented, accepted-for-v1 identity edge cases.

## Storage (SQLite, no ORM)

Raw `sqlite3`, deliberate at pilot scale (`sal/storage/db.py`'s own docstring:
swapping to Postgres later only touches that one module - not yet justified).
Key tables: `events`, `collection_runs` (per-day chunk ledger), `collection_jobs`
(user-facing job record, added Phase B), `findings`, `finding_whitelist`,
`systems` (environment registry, added Phase E), `sal_audit_log`. All
system-scoped tables use a flat `source_system`/`system_id` TEXT column, no
foreign keys - `systems.py` is a lookup, not a referential parent.

## Job execution model (`sal/jobs.py`)

A single always-on background worker thread (`start_worker()`, started once
from `create_app()`, guarded against Werkzeug's reloader double-starting it)
drains a `collection_jobs` queue one job at a time - that serialization is
what keeps SQLite from seeing concurrent collection+sync writers, with no
extra lock needed. A job's date range is chunked into one `collect_and_store()`
call per day, retried up to 3 times per day, with incremental
`days_completed`/`days_total` progress written after each day (used for the
Jobs page's progress bar and a live-pace ETA estimate). The daily scheduler
(APScheduler) also lives here, not in the Flask app factory, so a system
added via the UI can register its own cron job immediately.

**This chunked/retried/progress-tracked model is for multi-day event pulls
specifically.** A single, dateless RFC call (e.g., Phase D's audit-config
check) should NOT be forced through it - see the Phase D council decision
in `CHANGELOG.md`: build a direct synchronous call with its own explicit
timeout and `try/except/finally` discipline instead. The data-retention
purge (`sal/retention.py`) follows the identical reasoning for a different
reason - it's a local, dateless bulk-delete, not an RFC call at all - and
is registered on the same scheduler under its own job id
(`register_retention_job()`/`next_retention_run()`), offset by an hour
from the default daily collection time so the two writers don't overlap.

## Frontend

Single Flask-rendered shell (`sal/web/templates/shell.html`) + one
`sal/web/static/js/app.js` vanilla-JS SPA - all page content is rendered
client-side into `<main id="app">` by setting `innerHTML`, then wiring up
`getElementById`/`querySelector` listeners. No framework, no build step.
See `Design.md` for the full design system (theming, components,
accessibility commitments) - not duplicated here.

## Security posture (current, deliberate pilot-scale state)

- **No RBAC.** `_current_actor()` reads a self-declared display-name
  cookie - attribution only, not an access boundary. Anyone with network
  access to the tool can act as anyone.
- **Credentials never enter the database.** SAP passwords live only in
  `.env` (`SAL_SAP_<system_id>_PASSWD`). The `systems` registry table
  stores connection metadata (host/sysnr/client/environment) but has no
  password column at all - structurally, not just by convention.
- **SAL_RFC currently has SAP_ALL** (full, unscoped access), deliberately,
  until the feature set (including Phase F) is complete - the planned
  methodology is to use SU53 authorization-failure traces to build a
  minimal role from real usage afterward, not to guess at one upfront.
- **Detection-only guardrail**: nothing in this codebase writes back to
  SAP or takes remediating action. This must never change without an
  explicit, deliberate decision.

## Testing

`pytest`, all tests under `tests/`. `tests/conftest.py`'s `isolated_db`
fixture (autouse) redirects `sal.storage.db`'s `DATA_DIR`/`DB_PATH` to a
per-test throwaway file - no test ever touches the real `data/sal.db`.
RFC-calling code is tested by monkeypatching the collector function
(`collect_and_store`), never by hitting live SAP. Current count: run
`python -m pytest tests/ -q` for the live number; as of this writing, 90.

## Phase roadmap status

See `Phases.md` for current status of every phase (A-H) - not duplicated
here to avoid two sources of truth for the same table.

## Detection rules

See `Rules.md` for the full catalog (10 implemented, 4 not yet, and why).
