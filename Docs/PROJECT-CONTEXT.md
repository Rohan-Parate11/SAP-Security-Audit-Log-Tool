# PROJECT-CONTEXT.md

## Project name and purpose
SAL (Security Audit Log Analysis) — a SAP security monitoring tool. It
connects to live SAP systems over RFC, collects Security Audit Log (SM20)
events, runs deterministic detection rules against them, and gives analysts
a dashboard, findings/disposition workflow, job monitoring, and an SLA/aging
view. Detection-only — nothing in this codebase writes back to SAP.

See `ARCHITECTURE.md` for the code-level module map and data flow, and
`.claude/skills/sal-phase-workflow/SKILL.md` for the process used to build
each phase.

## Tech stack
- Backend: Python, Flask, raw `sqlite3` (no ORM)
- SAP connectivity: `pyrfc`, RFC-only, multiple systems supported via an
  environment-tagged registry (`sal/systems.py`) — Development/Quality/
  Production/Sandbox
- Extraction FM: `RSAU_API_GET_LOG_DATA` (validated; `RSAU_READ_LOG` does
  not work over RFC — confirmed, not assumed)
- Storage: single SQLite file (`data/sal.db`)
- Frontend: vanilla JS SPA (`sal/web/static/js/app.js`) + one Flask shell
  template, no framework, no external CDN dependencies. Light/dark theme
  via CSS variables + an explicit in-app toggle (persisted per-browser)
- Job execution: a single background worker thread (`sal/jobs.py`) draining
  a chunked, retried, progress-tracked job queue; APScheduler for daily runs
- Detection: 11 deterministic use cases (12 rule keys), no ML/LLM yet
- 90 automated tests (`pytest`), added alongside each feature

## Current phase
Phases A, B, C, D, and E are all complete, tested, and verified live, plus
several features built outside the blueprint's own phase lettering (Jobs
monitoring, SLA/aging dashboard, a full UI redesign, data retention,
repo/doc reorganization). Phase F's first slice — role/authorization
context ingestion and the out-of-context-transaction use case (#14) — is
also complete; peer-group deviation (#6) and GRC EAM (#10) remain, on
different tracks (see below). **See `Phases.md` for the authoritative,
current status of every phase — not duplicated here.**

## Key constraints
- Detection-only, read-only against SAP.
- **SAL_RFC currently has SAP_ALL** (full, unscoped access) on the
  monitored system(s), deliberately, until the tool's feature set
  (including the rest of Phase F: #6 peer-group deviation, #10 GRC EAM)
  is complete. The planned methodology: once feature-complete, use SU53
  authorization-failure traces to identify exactly which authorization
  objects are actually used, then build a minimal custom role from that
  real usage rather than guessing at one upfront. Do not build the scoped
  role before then. Concretely confirmed now that Phase F's role-context
  ingestion (`sal/role_context.py`) uses `RFC_READ_TABLE` — a generic
  table read, not a purpose-built BAPI — the eventual scoped role must
  explicitly include `S_TABU_DIS`/`S_TABU_NAM` authority for the
  `AGR_USERS`/`AGR_TCODES` tables specifically, not just whatever SU53
  happens to surface from other paths. Same applies to the
  directly-assigned-profile lookup added 2026-09-13
  (`SUSR_GET_PROFILES_OF_USER_RFC`, called from `user_access_summary()`) —
  add it to this same future authorization-tracing exercise.
- **Role/authorization data is now stored locally too** (Phase F):
  `user_roles`/`role_tcodes` hold a full map of who has which SAP role
  and what each role authorizes (~20k/~171k rows on the real system this
  was validated against) — a comprehensive privilege map, not just an
  activity log. This raises the confidentiality stakes of `data/sal.db`
  somewhat but doesn't change its trust model: the same file already held
  SM20 event history, protected the same (filesystem-level, non-RBAC)
  way (security-reviewer's assessment during Phase F review).
- **Directly-assigned-profile lookup (added 2026-09-13,
  `GET /api/role-context/user`)** is a live, on-demand, unthrottled RFC
  call (`SUSR_GET_PROFILES_OF_USER_RFC`) for *any* free-text `user_id` -
  unlike the bulk-synced role/tcode data above, it is not limited to
  usernames already on record locally. security-reviewer flagged this as
  a step up from the Phase F precedent immediately above: combined with
  this app's already-accepted no-RBAC/no-rate-limiting posture, anyone who
  can reach this endpoint can (a) use `USER_NOT_EXISTS` vs. success as an
  oracle to enumerate valid SAP usernames, and (b) for any valid one,
  instantly learn whether it holds `SAP_ALL`/`SAP_NEW` - i.e., identify
  the highest-value privileged accounts in the SAP landscape live,
  on demand, for arbitrary input, not just previously-synced ones.
  Deliberately NOT restricted to known/already-synced users - a user with
  a directly-assigned profile and zero PFCG roles at all (a real,
  supported case this feature exists for) would otherwise be invisible to
  the lookup entirely, defeating its own purpose. Accepted as-is for now,
  consistent with the project's existing no-RBAC decision
  (`Docs/Open_Questions_For_Review.txt`) rather than solved here; every
  lookup is at least attributed via the existing `sal_audit_log` trail
  (`role_context_user_lookup`). Revisit if this tool is ever exposed
  beyond a trusted internal network, or reconsider narrowing scope
  (e.g. only lookup users with prior SM20 activity) if this proves to be
  a real-world concern in practice.
- Multiple SAP systems are now expected (a four-environment landscape:
  Development/Quality/Production/Sandbox), managed via the Systems page —
  not a single hardcoded system anymore. Credentials still live only in
  `.env`, keyed by system ID; the database never stores a password.
- **Data retention (decided, SOX-driven, implemented 2026-09-09)**:
  normalized `events` retained 1 year (matches what auditors actually ask
  for), then purged. `findings`/disposition history retained 7 years (SOX
  audit-trail standard) — kept longer than raw events since disposition
  history has ongoing audit value after the underlying events age out. No
  raw/unparsed SAP payload is stored at all; confirmed this is sufficient
  for the future NL-query/LLM layer (Phase H), which will query the
  existing normalized tables, not a raw evidence layer. Enforced by a
  daily purge job (`sal/retention.py`) plus a manual trigger on the
  "Retention" page; every run (including empty ones) is logged to
  `retention_purge_runs` for full after-the-fact auditability.
- No RBAC yet — self-declared display-name attribution only, deliberate at
  pilot scale, to be revisited once the tool is used by more than one
  analyst.
- SQLite is deliberate at pilot scale; not yet justified to migrate.

## What "done" looks like (current standing bar, not just current phase)
- Every new feature ships with: a written plan, a dev-team four-lens
  review (and a council round if the review surfaces a genuine technical
  tension), tests alongside the implementation, an independent
  `python-reviewer`/`security-reviewer` pass with findings actually fixed
  (not just noted), any new UI built via `a11y-architect` against a
  finalized API contract, live browser verification (not just passing
  tests), and a `CHANGELOG.md` entry.
- Every review pass on this project so far has found at least one real
  bug before shipping — treat that as the expected outcome of the process
  working, not a sign something went wrong.
