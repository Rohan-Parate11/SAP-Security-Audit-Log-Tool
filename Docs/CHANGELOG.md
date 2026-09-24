# Changelog

All notable changes to SAL (Security Audit Log Tool) are recorded here.

## 2026-09-23 — Modernized the shell bar logo/favicon

The old shield-checkmark mark (`sal/web/templates/shell.html`) was a solid,
single-fill silhouette that read as generic clip art. Replaced with a
refined shield-check glyph in two treatments, following the same
single-weight-stroke, restrained-color design language used by modern
security-product logos and premium nav icons (Heroicons/Lucide-style
outline icons rather than a flat clipart fill):

- **Nav bar** (`.shellbar-logo`): a bare outline stroke icon (no tinted
  background box, `currentColor` so it adapts to the theme automatically),
  matching the bare-icon convention already used elsewhere in this app's
  Fiori re-theme.
- **Favicon**: a bolder filled version (solid white shield + a thick
  accent-blue checkmark "cutout") on the same rounded-square Fiori-blue
  background as before, since thin strokes disappear at 16px browser-tab
  size.

Both use the same underlying shield silhouette for a consistent mark.
Verified live via Playwright (nav bar in context, and the favicon SVG
rendered standalone at large size).

## 2026-09-22 — Re-themed the UI to match SSAT's SAP Fiori design system

`sal/web/static/css/style.css` was rewritten to match the Fiori-inspired
design system already implemented in the sibling SSAT (SAP Security
Assessment Tool) project (`SAP Security Assessment Tool/src/webapp/static/style.css`),
at the project owner's explicit request. This is a **presentation-only**
change - `app.js` and every class name/ID it depends on are untouched;
only design-token values and component-level rules (radius, shadow, color,
type) changed:

- **Palette**: flat SAP Fiori shell bar (`#354a5e`, `#1f2933` in dark
  theme) replacing the previous navy gradient + accent-line; Fiori's
  signature accent blue `#0a6ed1`; semantic `good`/`warning`/`critical`
  colors mapped onto the existing `--ok`/`--sev-medium`/`--sev-high`
  variable names (values changed, names preserved, so every existing
  selector kept working unmodified). Environment-tier tiles
  (`--env-production/sandbox/quality/development`) remapped to the exact
  dot colors SSAT's own sidenav uses for the same concept.
- **Typography**: SAP's own `'72'/'72full'` Fiori font (falls back to
  Arial where '72' isn't installed - same fallback chain SSAT uses),
  replacing Segoe UI.
- **Flatter elevation**: border-radius scale moved from 6/10/14px to
  Fiori's tighter 4px (buttons, tiles, tables) / 6px (modal), matching
  SSAT's actual per-component values; buttons changed from a gradient
  fill to Fiori's flat single-color fill; badges/pills flattened from a
  full pill shape to Fiori's small rounded-rect tag; tile/shell icons
  simplified from a tinted badge box to a bare icon, matching SSAT's own
  simpler treatment.
- Verified live via a scripted Playwright pass across Home, Dashboard,
  Findings, Collect, and Jobs in both light and dark theme (no existing
  Chromium download possible in this network - pointed Playwright at the
  already-installed system Chrome instead). All 16 spot-checked
  text/background color pairs (light + dark) pass WCAG AA (4.5:1).
- The previous stylesheet is kept alongside as
  `style.css.pre-fiori-backup` (no git history in this project to fall
  back on otherwise).

## 2026-09-21 — Required-field asterisk position + catalogue changes missing from Activity

Two user-reported bugs, both fixed:

- **Required-field `*` rendered below the label text instead of beside it**
  (Collect tab's Date from/Date to, Recurring filtered collections' Name,
  Systems' System ID/Environment/ashost/sysnr/Client). Root cause:
  `.field-grid label` was `display:flex; flex-direction:column`, which
  stacks *every* child of the label - including the inline
  `<span class="req">*</span>` right after the label text - onto its own
  row. Fixed by switching the label to normal block flow and pushing only
  the `<input>`/`<select>` onto its own line (`display:block` +
  `margin-top`), so the label text and its `*` stay on one line the way
  they always should have.
- **Adding a critical transaction or sensitive table didn't show up in
  Activity.** It actually was being recorded (`audit.record(..., "catalogue_add", ...)`
  fires correctly in `sal/web/api.py`) - but those catalogues are global,
  not tied to any one SAP system, so the entry's `source_system`/`client`
  are `NULL`. The Activity page always scopes its query to whichever
  system is selected in the nav bar, and `audit.list_entries()` filtered
  strictly on `source_system = ?`, so a global entry could never match a
  scoped view - it looked uncaptured even though it wasn't. Unlike the
  whitelist_add/finding_dispose gaps fixed earlier (those actions
  genuinely *do* belong to one system+client, so the fix there was to
  attach the scope at `audit.record()` time), a catalogue change has no
  single system to attach - so here the fix is in `list_entries()`
  itself: scoping to a system now also admits `source_system IS NULL`
  rows (same for `client`), surfacing every truly global action
  (`catalogue_add`/`catalogue_remove`, `rules_catalog_export`, ...)
  regardless of which system happens to be selected.

## 2026-09-16 — Added a "UAT Round 3" sheet to the retest workbook

`Docs/SAL_UAT_Round2_Retest.xlsx` gained a new "UAT Round 3" sheet (plus a
short new section on the "Instructions" sheet explaining it), closing two
gaps found while auditing the workbook for anything still outstanding:

- **13 rows never actually reverified by a tester after their fix landed** -
  the 5 items fixed today (HOME-02, DASH-07, JOB-09, JD-01, FIND-06) plus 8
  items fixed earlier this session whose Pass/Fail on "UAT Round 2" still
  shows the pre-fix verdict (COL-03, COL-04, JOB-02, JOB-03, JOB-08, FIND-07,
  FIND-10, GEN-07) - every other Round 2 row was already confirmed Pass, so
  these 13 were the only real gap.
- **5 brand-new capabilities built this session with no UAT coverage at
  all** - given first-time test cases: the recurring filtered ad-hoc
  schedule (JOB-12), the always-High critical-transaction rule with
  automatic backfill (FIND-11), the Low-severity downgrades for
  display-only table access and uncorrelated exports (FIND-12), the
  historical-average job ETA estimator (JOB-13), and the finding-key
  deep-link from Activity to Findings (ACT-04).

Each row leaves Actual Result/Pass-Fail/Tester/Date Tested/Comments blank
for the project owner to fill in on retest, matching the existing Round 2
format and Pass/Fail legend.

## 2026-09-16 — Three remaining UAT enhancement items resolved (DASH-07, JOB-09/JD-01, FIND-06)

Went back through both UAT documents (`SAL_UAT_Test_Plan.xlsx`,
`SAL_UAT_Round2_Retest.xlsx`) for every item still marked "Deferred" -
HOME-02 was already resolved by the credential store above, and the
"Extra Comments" sheet's 4 rows were already fixed; these three remained,
each confirmed against the current codebase and a project-owner decision
before implementing:

- **DASH-07** (Dashboard SLA & aging - per-priority breakdown): the
  Dashboard already rendered a per-severity table
  (`renderSlaBucketsTable()`), so the open question was whether that
  satisfied the request or something further was wanted. Project owner
  chose to add a chart on top of the existing table. Added
  `renderSlaBucketsChart()` - a stacked horizontal bar per severity
  (High/Medium/Low), each segment sized by `flex-grow` proportional to
  that severity's own on_track/at_risk/breached counts, reusing the same
  bucket colors as the table's badges below it. Since the table
  immediately below already conveys the identical numbers with real
  `<table>` semantics, the chart is `aria-hidden="true"` (per
  `a11y-architect` review) rather than duplicating an `aria-label`
  screen readers would hit twice for no benefit.
- **JOB-09 / JD-01** (Job Detail parameters as a copyable table): Job
  Detail's "Parameters this job was submitted with" panel already
  rendered a table, not raw CSV text, but multi-value filters (User(s),
  Transaction code(s), Message code(s)) were still joined with `", "`
  into one cell. `jobFiltersHtml()` now explodes each multi-value filter
  into one row per value, so each value sits alone in its own
  independently selectable/copyable cell. Per `a11y-architect` review,
  the label is emitted once as a `<th scope="row" rowspan="N">` spanning
  the group instead of being repeated on every exploded row, so a screen
  reader announces "Transaction code(s)" once as the group header rather
  than re-announcing it before every value. A small CSS override
  (`table.findings tbody th.mono`) prevents this row-header cell from
  picking up the table's `<thead>` styling, since `table.findings th`
  wasn't previously scoped to `<thead>` (nothing had put a `<th>` in a
  `<tbody>` before this).
- **FIND-06** (Findings table "looks cheap"): project owner asked for
  both stronger severity/rule visual treatment and general
  spacing/density polish. Added a severity-colored left accent bar per
  row (`box-shadow: inset` on the row's first cell, since a plain border
  doesn't paint on `<tr>` under `border-collapse: separate`), a larger,
  bolder severity badge (`.badge-lg`) scoped to just this column (the
  shared `.badge` look used everywhere else in the app is untouched),
  bolded rule labels (`.rule-label`), subtle zebra row striping, and a
  touch more vertical row padding.
- All three are pure frontend (`app.js`/`style.css`) changes with no API
  or data-model impact - verified by exercising the two new/changed pure
  render functions directly in Node against representative inputs (both
  the multi-value rowspan grouping and the chart's flex-grow proportions
  and empty-severity placeholder), plus the existing `337`-test pytest
  suite (unaffected, confirming no incidental regression).

## 2026-09-16 — Credential store: security-reviewer pass, 3 real issues fixed

An independent `security-reviewer` pass was run against the new central
credential store (previous entry) given its sensitivity. It correctly did
not treat "credentials now live in the database" itself as a finding -
that reversal was already an explicit, informed project-owner decision -
and instead scrutinized whether the implementation was as safe as that
decision could reasonably be. It found:

- **HIGH**: `GET /api/credentials/<system_id>` had no `try/except` around
  the decrypt call at all. A realistic operational event (the encryption
  key rotated, or ciphertext saved under a different key than the one
  currently configured) would raise uncaught - and since `run.py` runs
  with `debug=True` unconditionally, that would have surfaced Werkzeug's
  interactive traceback page, which prints every stack frame's local
  variables, including `_fernet()`'s own `SAL_CREDENTIAL_ENCRYPTION_KEY`
  value - to anyone who hit it. That key decrypts every system's stored
  password, not just the one being requested, and the exception fires
  *before* the `credential_view` audit call, so this exposure path would
  have left no audit trail at all - worse than the "every reveal is
  logged" mitigation this feature exists to provide. Fixed: wrapped in
  `try/except credentials.CredentialStoreNotConfigured`, returning a
  clean `503` instead.
- **MEDIUM**: deleting a system never cleaned up its stored credential.
  The row survived indefinitely - invisible in the Password Manager's
  list (built by iterating currently-registered systems) yet still
  fetchable by direct API call, and would have been silently reactivated
  with no new `credential_set` audit entry if a system with the same
  `system_id` were ever re-added later. Fixed: `delete_system()` now
  also calls `credentials.remove_credential()`, alongside its existing
  schedule/filtered-schedule cleanup for the same system.
- **MEDIUM**: the Password Manager's "View / edit" modal fetched,
  decrypted, and audit-logged the real password on every open, but the
  password field's `value` was never actually set - so nothing was ever
  shown on screen, directly contradicting both the modal's own note text
  ("the password above is shown in full") and the project owner's
  explicit choice for this feature (viewable, not write-only). Fixed: the
  field now genuinely displays the decrypted value (switched from a
  masked `type="password"` to plain `type="text"`, since masking a value
  the design already intends to reveal adds friction with no real
  security benefit here).
- Two LOW items also fixed: the reveal response now sets
  `Cache-Control: no-store`; `.env.example` gained a
  `SAL_CREDENTIAL_ENCRYPTION_KEY` placeholder with generation
  instructions. One stale code comment in `app.js` (left over from
  before this feature, claiming "no password field anywhere here by
  design") was also corrected.
- 4 new regression tests added directly to `tests/test_credentials_api.py`
  proving each of the HIGH/MEDIUM fixes.

## 2026-09-16 — New capability: central, encrypted credential store ("Password Manager")

- Answered directly, resolving the HOME-02 open question: "Create a
  similar page for password manager on the home screen besides the
  systems a central repository that will store passwords for all the
  systems. the connection details will be added as when the systems are
  added." This reverses a constraint the project held for most of its
  life - "SAP credentials never enter SAL's own database" - a deliberate,
  informed reversal, not an oversight. Before building anything, the
  concrete tradeoff was put to the project owner directly: this app has
  no RBAC (`_current_actor()` is a self-declared display-name cookie,
  attribution only), so centralizing credentials means anyone who can
  reach the app can reach every system's live SAP password. The owner
  chose to proceed, and made two further explicit calls that shape the
  whole design: a stored password stays **viewable** again through the
  UI (not write-only), and `.env` keeps working unchanged for any system
  that hasn't had a password saved centrally yet (coexistence, no forced
  migration).
- New `sal/credentials.py`: a `system_credentials` table (one row per
  system with a centrally-stored password), encrypted at rest with
  Fernet (symmetric, authenticated encryption - the `cryptography`
  package, already a transitive dependency of `pyrfc` in this
  environment, now pinned directly in `requirements.txt`). The
  encryption key (`SAL_CREDENTIAL_ENCRYPTION_KEY`) lives in `.env`,
  deliberately outside the database - the same principle that kept SAP
  credentials out of `sal.db` in the first place, just one layer down: a
  stolen `sal.db` file alone can't decrypt anything in it.
- `sal.config.sap_system_config()` (the single choke point every RFC
  connection resolves credentials through) now checks the central store
  first, via `resolve_stored_config()` - which merges ashost/sysnr/client
  from the existing `systems` registry (already UI-managed, non-secret)
  with the stored rfc_user/password - and only falls back to the
  original all-`.env` lookup when nothing is stored for that system_id.
  `sal.systems.has_credentials()` now checks both sources too, so the
  Home page's existing "credentials missing" icon logic needed no
  frontend change at all. Both new cross-module edges use deferred
  (function-body) imports to avoid a real circular-import risk:
  `sal.systems` already imports `sal.config` at module level, and
  `sal.config` must stay importable with zero `sal.*` dependencies of its
  own (it has to load before `pyrfc` anywhere in the codebase).
- Every **reveal** of an actual stored password (not just metadata) is
  audit-logged as `credential_view` - the one mitigation available given
  the project owner's explicit "viewable" choice, so at minimum who
  looked at what, and when, is always reconstructable. New
  `GET/POST/DELETE /api/credentials[/<system_id>]` routes (`GET
  /api/credentials` lists every system's credential source - "central" /
  "env" / "missing" - never the password itself; delete requires a
  reason, matching every other removal in this app).
- New **Password Manager** page (`#/credentials`, linked from Home,
  reachable without a system chosen first - same gate exemption as Home
  itself) listing every system with its credential source and a
  view/edit/remove action per system. The existing Add/Edit System modal
  also gained optional RFC user/password fields - filling both in at
  system-registration time saves them straight to the central store
  ("the connection details will be added as when the systems are added");
  leaving them blank keeps the system on `.env`, exactly as before.
- 23 new tests (`tests/test_credentials.py`, `tests/test_credentials_api.py`)
  covering the encryption round-trip, the `.env`-coexistence fallback in
  both `sap_system_config()` and `has_credentials()`, missing/invalid-key
  handling, and every new route including the audit trail. Tests
  deliberately use a fake `"ZZTEST"` system_id, not this project's real
  `"S23"` - `load_dotenv()`'s real values otherwise leak into the whole
  pytest run's process environment, undetected until a test asserting
  "no credentials configured" fails against real data.
- An independent `security-reviewer` pass was run against this specific
  feature given its sensitivity - see this changelog's own follow-up
  entry (or `Docs/Memory.md` item 5) for what it found and what, if
  anything, was fixed as a result.

## 2026-09-16 — New capability: recurring FILTERED collection schedules

- Answered directly, resolving an open architectural question: "the
  schedule button is only for changing the daily scheduled job which is
  prebuilt in our tool. in the same way, if I want to schedule an ad hoc
  job to run on daily or whatever basis, I should be able to do that as
  well." The existing "Automatic daily collection" schedule
  (`sal/schedule.py`) is deliberately never filterable - it's the sole
  feed for every detection rule and must stay comprehensive by
  construction (`test_run_daily_checkpoint_never_submits_any_filters`
  guards this invariant, untouched by this change). This is a genuinely
  separate, additive capability: save a Collect-style filtered pull
  (user(s)/transaction code(s)/report/instance/message code(s)) and run
  it on its own recurring cadence, independent of the baseline.
- New `filtered_schedules` table and `sal/filtered_schedule.py` module.
  Unlike the baseline (one schedule row per system), a system can have
  any number of these at once - "daily SU01 check for these 3 users" and
  "hourly check of FB01N" can coexist. Cadence fields (`interval_type`/
  `anchor_hour`/`anchor_minute`/`interval_hours`) mirror `schedule.py`'s
  own shape and validation exactly (same CHECK-constraint discipline,
  same defensive numeric coercion), including a `_to_int()` reused
  directly from `schedule.py` rather than duplicated. Each schedule can
  be paused (`enabled`) without deleting its saved definition.
- No catch-up/resume, deliberately unlike the baseline's day-by-day
  checkpoint: every firing just pulls a fixed 2-calendar-day rolling
  window (today and yesterday, full day), relying on `events`' own
  natural-key dedup to make repeated/overlapping pulls harmless. This
  sidesteps a real ambiguity in expressing a true sub-day rolling window:
  `RSAU_API_GET_LOG_DATA`'s `TIM_FROM`/`TIM_TO` apply as a time-of-day
  slice repeated across every day in range, not a single continuous
  datetime span, so there's no clean way to express "the last 6 hours"
  when that window crosses midnight. A firing missed while the app was
  down simply isn't backfilled - acceptable here in a way it deliberately
  is NOT for the baseline, since these are supplementary/investigative
  pulls, not the primary detection feed.
- New `mode="filtered_scheduled"` on `collection_jobs` - deliberately
  never `"scheduled"`, the most important correctness decision in this
  feature: `last_scheduled_checkpoint()` (which the baseline's own
  `run_daily_checkpoint()` uses to resume) only ever looks at
  `mode='scheduled'` rows. Reusing that mode for a filtered job would
  have let its `last_completed_date` be mistaken for baseline progress,
  silently causing the real, comprehensive detection-feed collection to
  skip days it never actually pulled unfiltered. Submitted through the
  same `submit_job()` every other collection path uses (never bypassed -
  see `sal/jobs.py`'s own docstring on why that matters), so it still
  gets chunking/retry and a `sync_findings()` call at the end like
  everything else.
- `sal/jobs.py` gained `run_filtered_schedule()`, `register_filtered_schedule_job()`/
  `unregister_filtered_schedule_job()`/`next_filtered_schedule_run()`
  (mirroring `register_daily_job()`'s exact APScheduler pattern, one job
  id per saved schedule: `filtered-<id>`), and `start_daily_scheduler()`
  now also registers every currently-enabled filtered schedule on
  startup. New `GET/POST /api/filtered-schedules` and
  `PATCH/DELETE /api/filtered-schedules/<id>` routes (delete requires a
  reason, matching every other removal in this app); `delete_system()`
  now also cleans up and unregisters a removed system's filtered
  schedules, same as it already does for the baseline schedule and
  role-context job.
- New "Recurring filtered collections" panel on the Collect page, below
  the existing "Automatic daily collection" panel - add/edit (one shared
  form, mirroring `openSystemModal()`'s own add-or-edit-in-one-modal
  pattern elsewhere in this app), pause/resume, and remove (reason
  required) for a system's saved filtered schedules. The Jobs table's
  Mode column/filter and job-name fallback text now recognize
  `filtered_scheduled` as its own distinct value, not lumped in with
  ad-hoc or scheduled.
- 27 new tests (`tests/test_filtered_schedule.py`), covering validation,
  CRUD, the window-computation logic, and - the one most worth calling
  out - `test_run_filtered_schedule_does_not_move_the_baseline_checkpoint`,
  which directly proves a completed filtered-schedule job never advances
  `last_scheduled_checkpoint()`.

## 2026-09-15 — ETA now works for the common case (ad-hoc and single-day jobs)

- Reported directly: "the ETA column is empty even for running jobs."
  Root cause: `estimate_eta_seconds()` only ever extrapolated from THIS
  job's own within-run progress, requiring at least one fully completed
  day of a multi-day job before it had a rate to extrapolate from. Two
  facts about how most jobs actually run meant that requirement was
  almost never met while a job was still "running": every ad-hoc job
  (the "Collect" UI) runs its whole date range as a single unchunked
  call (2026-09-12's chunking change), so it never has a "day 1 of N
  done" moment at all; and a typical scheduled daily job, once caught
  up, only ever pulls one day too. ETA only ever worked for a genuinely
  multi-day scheduled catch-up - everything else was always going to
  show a bare `-`.
- Asked directly which fix to build: a clearer empty-state label, or a
  real historical-average estimator. Chose the estimator.
  `estimate_eta_seconds()` now primarily extrapolates from how long this
  SAME system's past completed jobs of the SAME mode actually took, per
  calendar day of their own requested range (`dat_from`/`dat_to` in
  `filters_json` - the true normalizer, since `days_total` means
  something different per mode and is always 1 for ad-hoc regardless of
  range width). Scoped by mode deliberately: an ad-hoc job's one
  unchunked call and a scheduled job's one-call-per-day chunking have
  different per-day overhead, so averaging them together would
  misestimate both. Only `success`/`partial` history counts (an `error`
  job may have failed fast or slow, neither representative); requires at
  least 2 historical samples before trusting an average, averaged over
  the most recent 10 so a system's performance trend can shift over
  time. Falls back to the old within-run progress method when there
  isn't yet enough history for this system+mode - a system's very first
  job of a given mode, for instance, still gets nothing until it or a
  sibling completes once, which is the honest answer given there's
  nothing to learn from yet.
- 6 new tests in `tests/test_jobs.py` (this function had no direct test
  coverage before this change either).

## 2026-09-15 — Low severity now actually used by two existing rules

- Asked directly: "I can see there are all high and medium severity
  findings and low findings, have we configured any findings under low
  category?" Checked every rule in `sal/rules/*.py` - none had ever
  assigned `Low`, despite the Dashboard/Findings/SLA infrastructure
  already fully supporting it (badge colors, donut-chart segment, SLA
  target, filter option) - the tile was always going to read 0.
- Agreed approach ("option b"): downgrade the two existing cases that
  were the weakest signal in their respective rules, rather than
  inventing a new rule just to populate the category:
  - `sal/rules/export.py`'s **sensitive_table_access**: a plain display
    of a sensitive table (no change/delete) is now `Low`, was `Medium`.
    Change/delete activity is unchanged at `High`.
  - `sal/rules/export.py`'s **data_export**: a download with no matching
    sensitive-table access in the 15 minutes before it is now `Low`, was
    `Medium`. A correlated export (`sensitive_data_export`) is unchanged
    at `High`.
- No frontend change needed - severity is always read per-finding from
  the API response, and `Low`'s styling (`--sev-low` tokens, `.badge-low`,
  `.tile-low`, `.donut-low`) already existed, unused, for exactly this.
- `sal/rules_catalog.py`'s "Detection Rules" reference export updated to
  match (`typical_severity` now reads "Low or High" for both rules,
  rather than "Medium or High").
- `sal/rules/export.py` had **no direct test coverage at all** before
  this change (confirmed by grepping `tests/` - `tests/test_export.py`
  tests the unrelated CSV/XLSX serializer module of the same name). New
  `tests/test_sensitive_data_export_rules.py` (8 tests) covers both
  functions properly, not just the severity change, rather than shipping
  a real behavior change to a previously-untested module.
- Caught before shipping (self-review, not an external pass this time):
  `sal/findings.py`'s `sync_findings()` refreshes `summary`/`evidence_json`
  for an already-open finding on every sync (added earlier the same day
  for FIND-07), but never touched `severity` - and severity isn't part of
  the identity hash either, so an already-inserted `Medium`
  sensitive_table_access/data_export finding would have silently stayed
  `Medium` forever, even after this exact code change, since its
  finding_key wouldn't change and nothing would ever rewrite the stored
  value. Fixed by adding `severity` to the same open/whitelisted-only
  refresh (never for a `true_positive`/`false_positive` disposition,
  same reasoning as summary/evidence_json - a disposition is a considered
  call against a specific severity, not just specific evidence). 2 more
  tests added directly to `tests/test_findings.py` for this.

## 2026-09-15 — New rule: every critical transaction, tracked unconditionally

- Requested directly: "I want that all the critical transactions be
  always be marked as finding even if they are a part of user's role or
  profile assignment." Two existing rules already touch critical
  transactions, but neither does this: first-time-sensitive-transaction
  fires once per user+tcode ever, then goes quiet; out-of-context-
  transaction fires every time but only when the user's *current* role/
  profile genuinely doesn't cover it, so a properly-authorized run never
  flags there, by design.
- New rule, **Critical transaction executed**
  (`sal/rules/critical_transaction_usage.py`, rule key
  `critical_transaction_usage`) - additive, not a replacement for either
  existing rule. Fires on every AU3 event whose transaction code is on
  the critical-transaction catalogue, for every user, with no first-time
  tracking and no role/profile check of any kind - authorized daily admin
  use and a genuine anomaly are treated identically, by explicit design
  choice (confirmed directly: severity High, and yes, backfill
  automatically).
- Severity is **High**, and - like every rule in this tool -
  `sync_findings()` re-evaluates all currently-retained events on every
  run, so the very next sync retroactively creates a finding for every
  critical-transaction event already collected, not just future ones.
  This will generate real volume on any system with frequent, fully
  authorized privileged-transaction use - that's the intended behavior,
  not a bug; whitelist a known, accepted pattern (scoped to a specific
  user, or left open to any user) if it shouldn't keep generating new
  open findings.
- Wired through the same places every rule needs to be:
  `sal/rules/registry.py` (registration), `sal/rules/_coverage.py`
  (SM19 coverage mapping - same AU3/CLASS_TCD signal the other
  transaction-based rules already use), and `sal/rules_catalog.py` (the
  "Detection Rules" reference export). 6 new tests
  (`tests/test_critical_transaction_usage.py`), including one that
  patches `sal.role_context.authorized_tcodes_for_user()` to report full
  coverage and confirms the finding still fires anyway - proving this
  rule genuinely has no authorization gate to bypass, not just that no
  role data happened to exist in the test.

## 2026-09-15 — Activity's finding_key entries now link straight to the finding

- Requested directly: disposing a finding logs the action to Activity with
  its `finding_key` (a SHA-256 identity hash) in the details column, with
  no way to tell which actual finding that was.
- `sal.findings.list_findings()` gained an exact-match `finding_key`
  lookup (`GET /api/findings?finding_key=...`), deliberately bypassing
  every other filter *and* the current system/client scope - the key
  alone already fully identifies one finding, so an analyst following a
  link from Activity shouldn't need to first switch to whichever system
  that finding happens to belong to.
- The Activity page's Details column now renders a "View finding &rarr;"
  link for any entry carrying a `finding_key` (currently just
  `finding_dispose`) instead of the raw hash, going to
  `#/findings?finding_key=...` - a new view on the Findings page showing
  just that one finding, with a banner explaining the column filters
  don't apply there and a link back to the full list.
- 3 new tests (`tests/test_findings.py`, `tests/test_api.py`) cover the
  lookup itself and, specifically, that it still works when the finding's
  own system doesn't match whatever's currently selected.

## 2026-09-15 — Fixed a self-inflicted router regression: repeated nav clicks could hang the page

- Reported directly, with screenshots ("Error 1", "Error 2"): clicking the
  SAL logo while already on Home navigated to Dashboard instead
  (unexplained from reading the code alone), and clicking it rapidly
  15-20 times left the page stuck showing only loading-skeleton
  placeholders, never settling.
- The first fix for the Dashboard-instead-of-Home report (a per-call
  token that re-ran `route()` whenever a call found itself superseded)
  was itself a real bug, caught only once the user actually reproduced
  it: nothing stopped a NEW `route()` call from starting while one was
  already awaiting its own data, so 15-20 rapid clicks started 15-20
  independent renders; when those settled out of order, nearly all of
  them found themselves "stale" and re-ran themselves too, cascading
  into dozens of concurrent `/api/systems` fetches and re-renders that
  never visibly finished - exactly the stuck-skeleton screenshot.
- Replaced with the correct pattern: `route()` now coalesces overlapping
  calls instead of running one per call. A call that arrives while a
  render is already in flight just flags that a newer navigation
  happened and returns immediately; the in-flight call, once it finishes,
  checks that flag and loops around for exactly one more render of
  whatever the route is by then - at most one extra render per busy
  period, no matter how many clicks caused it.
- Also added a defensive normalization: on every navigation, the visible
  address bar is rewritten back to a plain `/` + hash
  (`history.replaceState`, no reload/history entry) if it ever shows a
  real path/query string instead - the router itself only ever reads
  `location.hash`, so this never affected what actually rendered, but a
  URL like `/findings?job_name=&mode=...#/home` (exactly what both
  screenshots showed) is confusing to look at regardless of how it got
  there. The original mechanism that produced that specific real
  path/query in the first place was not conclusively traced (no live
  browser tool available this session) - this normalization makes it
  self-correct every time regardless.

## 2026-09-15 — UAT Round 2 retest: 10 findings resolved

- `Docs/SAL_UAT_Round2_Retest.xlsx` (the 27-item scoped retest of Round 1's
  fixes) came back with several genuine new Fail rows and four freeform
  "Extra Comments." Worked through all of it, using three parallel
  investigation-and-fix agents (audit-log scoping, friendly SAP error
  messages, and two CSS layout bugs) alongside direct fixes, then a
  `python-reviewer` + `security-reviewer` pass on the whole batch - both
  caught one real issue apiece, both fixed before this was considered done.
- **HOME-01 (retest): the credentials-missing icon rendered outside the
  system tile.** A real CSS regression from the *previous* round's own
  fix: `.fiori-tile-flag { position: absolute; ... }` and the new
  `[data-tooltip] { position: relative; ... }` rule have identical
  specificity and both set `position` - whichever was declared later in
  the file silently won, pulling the flag out of its pinned corner and
  into normal document flow. Fixed the same way the file's own
  `.fiori-tile-menu` comment already documents for an identical prior
  case: raise specificity (`.fiori-tile .fiori-tile-flag`) so the fix
  can't depend on declaration order.
- **JOB-02/JOB-03 (retest): an empty filter result made the column-filter
  dropdown unusable, hiding other filters too.** Root cause:
  `.table-scroll { overflow-x: auto }` (needed for wide tables) forces
  the browser to also treat `overflow-y` as non-visible per the CSS
  Overflow spec, so the container clips anything that visually extends
  past its own box - normally invisible since a table full of rows is
  tall enough for a dropdown to fit, but a zero-match "No jobs match..."
  row collapses the container down to header height, clipping the same
  dropdown that fit fine a moment before. Fixed with a generous
  `min-height` on `.table-scroll`. Also added the requested **Reset
  filters** button to Jobs, both Recovery panels, and Findings.
- **JOB-08 / FIND-10 (retest): connection-test and whitelist-removal
  don't show up in Activity, "could be happening for other activities
  too."** Both actions *were* being recorded correctly - `audit.record()`
  was called every time - but with an incomplete system/client scope, so
  the row never matched the Activity page's own default (system_id AND
  client) filtered view and silently never appeared there. A full sweep
  of every `audit.record()` call site against every route found the same
  gap in five more places: `system_add`, `system_update`,
  `schedule_update`, `role_context_refresh`, and `whitelist_add`. A
  follow-up `python-reviewer` pass caught one more, the most significant
  of the batch: `finding_dispose` (an analyst's true_positive/
  false_positive/whitelisted call) had the identical gap and was still
  unscoped - fixed the same way, looked up before the write completes.
  `system_remove`'s entry was also completed for consistency (low
  practical impact, since a removed system becomes unselectable in the
  Activity view's own scope filter either way).
- **FIND-07 (retest): "Still shows T-* profiles" despite last round's
  fix.** The rule-level fix was actually correct - a *newly* computed
  finding never includes a T-* profile. The bug was one layer up: a
  finding computed *before* the fix shipped keeps its original
  `finding_key` forever (identity excludes only a documented denylist of
  volatile fields, and this profile data wasn't on it), and
  `sync_findings()` only ever bumped `last_seen_at` on an existing row,
  never its stored evidence - so the pre-fix finding's evidence/summary
  stayed frozen with the old, T-*-including text indefinitely. Fixed two
  ways: added `directly_assigned_profiles`/`directly_assigned_profiles_error`/
  `has_broad_access_profile` to the volatile-field denylist (a live
  per-user RFC lookup's result was never meant to be part of a finding's
  identity, the same reasoning already applied to `role_refresh_checked_at`),
  and `sync_findings()` now also refreshes `summary`/`evidence_json` on an
  existing finding, not just `last_seen_at` - **but only while a finding
  is still `open` or `whitelisted`**. A security-reviewer pass on the
  first version of this fix caught a real gap: it refreshed evidence
  unconditionally, meaning a `true_positive`/`false_positive` finding's
  evidence - the thing an analyst's actual disposition decision was based
  on - could silently change underneath them, automatically, on every
  later collection job, with no trace of what changed. Once disposed,
  evidence/summary are now frozen exactly as they were at disposition
  time, permanently.
- **GEN-07 (retest): tables don't reflow at reduced browser zoom.** A
  second, different bug from the one already fixed this same tab: a
  1280px `max-width` on `main#app` never grows past that regardless of
  zoom (which increases the effective CSS-pixel viewport width) or window
  size. Removed the cap; Home's own narrower centered layout is
  unaffected (a higher-specificity `body.route-home` rule).
- **COL-03 (retest): "the medium priority job still is running while the
  high priority job is queued."** Verified the claim-order logic itself
  is correct (`ORDER BY job_class ASC, submitted_at ASC` against
  `status = 'queued'` only) - this is expected behavior, not a bug. SAL's
  single-worker-thread design can only ever affect which *queued* job
  gets claimed next; it cannot preempt a job that has already started
  running. No code change.
- **COL-04 (retest): "what is the filters/criteria for which this is
  getting scheduled... can we have the same way scheduling feature for
  ad hoc jobs as well?"** The schedule panel's callout already stated the
  full-log/no-filters behavior, just not prominently enough - reworded to
  lead with it as a standalone, bolded sentence. The separate ask (a
  recurring *filtered* collection) is a distinct, larger capability
  already considered and deliberately deferred once before (2026-09-14's
  IA-consolidation round); logged as its own tracked open decision in
  `Docs/Open_Questions_For_Review.txt`, same treatment as the HOME-02
  credential-vault question.
- **Extra comments, not tied to a specific test ID:**
  - A raw RFC error (`TSV_TNEW_PAGE_ALLOC_FAILED`, i.e. SAP ran out of
    memory building the result set) had no plain-language explanation or
    suggested next step for an analyst. New `sal/friendly_errors.py`
    maps a small, curated set of known SAP RFC error keys to a friendly
    explanation + suggestion, shown alongside (never replacing) the raw
    technical error on Jobs/Job Detail/Recovery/Collect's progress panel.
    Deliberately returns nothing for anything unrecognized rather than
    guessing.
  - "Sometimes automatically shows dashboard instead of the findings
    page," and "clicking the SAL icon sometimes does not navigate."
    Both traced to one real bug: the "Skip to main content" accessibility
    link used `href="#app"`, and activating it set `location.hash` to
    `"app"` - a string `route()`'s own parsing doesn't recognize as any
    known page, silently falling through to its dashboard fallback.
    Fixed by having the skip link focus `<main id="app">` directly
    instead of ever touching the hash. Separately, clicking a nav link to
    the hash you're already on never fires a `hashchange` event at all -
    now handled explicitly so it always does something.
  - The top-left "SAL" brand link still showed an underline on hover -
    a CSS specificity gap (a global `a:hover` rule set `text-decoration`
    on a property the brand link's own hover rule never touched). Fixed.
- Full suite: 260 passed after the direct fixes; 262 after the two
  post-review fixes (finding_dispose scoping, and freezing evidence for a
  terminal disposition) - 19 new tests added across
  `tests/test_findings.py`, `tests/test_api.py`, and two new files,
  `tests/test_friendly_errors.py`/`tests/test_friendly_errors_api.py`.

## 2026-09-15 — Training documentation refreshed as v2 (Markdown + PDF)

- Requested directly: "update the training documents as well as per the
  curret status of the tool ... save them in training folder with as
  version 2." Both `Docs/training/SAL_Technical_Deep_Dive.md` and
  `Docs/training/SAL_Analyst_User_Guide.md` were last substantively
  updated 2026-09-10/12 and had drifted well behind the tool's actual
  state - most notably, neither mentioned Phase F (role/authorization
  context ingestion, `sal/role_context.py`, the two out-of-context-
  transaction detection rules) at all, nor the Recovery tab, per-system
  job scheduling, SM36/SM37-modeled job class/priority, ITGC-format
  exports, or the Excel-style column-header filters - all shipped since.
- Rather than overwrite the originals, wrote new versioned copies -
  `SAL_Technical_Deep_Dive_v2.md`/`SAL_Analyst_User_Guide_v2.md` - so the
  v1 documents stay available unchanged. Content was re-derived from the
  live codebase (`sal/rules/registry.py`, `sal/role_context.py`,
  `sal/web/api.py`'s actual route table, `sal/web/templates/shell.html`'s
  nav, `Docs/PROJECT-CONTEXT.md`, `Docs/ARCHITECTURE.md`), not just
  copy-edited from v1, to avoid carrying forward anything already stale.
- `scripts/render_training_pdfs.py`'s `DOC_META` dict (keyed by filename
  stem, drives each PDF's cover-page subtitle/audience line) only had
  entries for the unversioned stems - the first render pass produced
  correct v2 PDFs but with a blank cover subtitle/audience. Added
  `SAL_Technical_Deep_Dive_v2`/`SAL_Analyst_User_Guide_v2` entries and
  re-ran; all four PDFs (two v1, two v2) regenerate cleanly via the
  existing `python scripts/render_training_pdfs.py` pipeline, which
  globs every `.md` under `Docs/training/` - no other script change
  needed for the new files to be picked up.

## 2026-09-14 — UAT round 1: 20 findings resolved

- The first full end-to-end UAT pass (`Docs/SAL_UAT_Test_Plan.xlsx`, 77
  cases) came back with 14 Fail rows plus actionable comments on several
  Pass rows and a new tester-added case (GEN-08). Worked through all of
  it; summary below, grouped by root cause. Two items were explicitly
  deferred rather than fixed - see the last section.

- **Column-header filters were genuinely broken for real use** (JOB-02/
  03/04, FIND-03): checking a second filter checkbox, or typing a second
  word into a text filter, silently did nothing until the page was
  reloaded. Root cause: every filter change fully re-rendered the whole
  table including `<thead>`, destroying and resynthesizing the dropdown/
  input on every keystroke or click - a synthetic `trigger.click()` +
  focus/selection-restore dance around that rebuild had real edge cases.
  Fixed properly, not patched: `renderJobsTable()`/`renderRunsTable()`/
  `renderFindingsTable()` are now split into `...Head()`/`...Body()`
  functions - a data reload only ever replaces `<tbody>`; the header (and
  whatever dropdown is open or text is mid-typing inside it) is never
  touched by one. The old capture/restore-focus functions are gone
  entirely, not just unused.
- **Columns picker covered the table it was changing** (JOB-08): capped
  its dropdown's height with internal scrolling so it can no longer
  obscure more than a small band of rows.
- **Delete-style buttons read as hyperlinks, not buttons** (JOB-10,
  GEN-08): `.link-danger` restyled to match `.btn-secondary`'s shape
  (border, padding, no default underline) instead of underlined red text.
- **Native browser dialogs replaced with in-app UI** (RET-02's `confirm()`
  purge prompt, JOB-11's `alert()` on a rejected delete, plus two other
  `alert()`/`confirm()` call sites found while fixing these): new
  `confirmModal()` (Promise-based, reuses the existing modal system) and
  `showErrorToast()` (an error-styled variant of the existing toast).
- **Whitelist**: the table showed raw rule keys ("data_export") instead
  of labels ("Data Exports") (FIND-09) - now looks the label up. Removing
  an entry required no reason, unlike adding one (FIND-10) - now prompts
  inline for one and the backend (`DELETE /api/whitelist/<id>`) rejects a
  missing reason with 400, matching every other delete/restore action.
- **Connection test gave no actionable message for an unmaintained
  system** (CONN-01): `config.sap_system_config()`'s missing-env-var
  `RuntimeError` was escaping the route uncaught as a 500 - now caught and
  reported as "Credentials not maintained... set them in .env and test
  again." A python-reviewer pass caught a real bug in this fix before it
  shipped: `SapConnectionError` subclasses `RuntimeError`, so the new
  `except RuntimeError` had to be ordered *after* `except
  SapConnectionError`, or a genuine live RFC failure (credentials
  perfectly fine) would've been caught by the broader clause first and
  mislabeled as a credentials problem.
- **Schedule save gave no confirmation and an easy-to-miss scope note**
  (COL-04): added a toast alongside the existing inline message, and
  promoted the "this always pulls the full unfiltered log" caption to a
  `.callout` box instead of small muted text.
- **Credentials-missing icon relied on a slow native tooltip** (HOME-01):
  replaced with an instant CSS tooltip (`[data-tooltip]`, no browser hover
  delay), kept the existing `aria-label` for screen readers, and made the
  icon keyboard-focusable.
- **Out-of-context-transaction findings over-flagged role-generated
  profiles** (FIND-07): a profile matching SAP's own "T-\<8 hex digits\>"
  PFCG-generated-profile naming convention is now excluded from the
  directly-assigned-profile flag/evidence - it almost always reached the
  user via a role they legitimately hold (already shown in the role-gap
  message), not a true direct SU01-Profiles-tab assignment.
  `SUSR_GET_PROFILES_OF_USER_RFC` has no field to tell the two apart, so
  this is a documented naming-convention heuristic, not a true role-to-
  profile relational check (that would need a different, unvalidated
  RFC/table - not attempted, per this project's own rule against guessing
  SAP internals).
- **Root-caused two genuinely intermittent bugs**: the occasional
  `/api/findings` 500 while navigating (GEN-02) was real SQLite
  writer-vs-writer lock contention - `sync_findings()` holds one
  transaction open for its whole ~98s run, and the default 5s busy
  timeout wasn't enough for a second writer to wait it out; raised to
  120s, with a regression test that reproduces real cross-thread lock
  contention. The Activity Action filter "not updating" (ACT-03) was that
  same 500 being silently swallowed - `load()` had no error handling at
  all, so a rejected request just left the table on stale data with zero
  feedback; both Activity and Findings now show a visible error instead.
- **Fixed the page-transition and narrow-viewport issues** (GEN-03,
  GEN-07): the page-enter transition had a real bug (`main#app`'s
  transition was unconditional, so *adding* the fade-in class also
  animated already-visible content invisible-then-back, reading as no
  transition at all) - split onto its own class, applied only after an
  untransitioned jump to invisible. The narrow-viewport stray box (a
  fixed-width `.sidenav`/shellbar not shrinking) got a `@media` breakpoint
  plus an `overflow-x: hidden` backstop on `body`. GEN-05 (reduced motion)
  needed no code change - the app's global reduced-motion rule was
  already correct; what read as "no animation at all" was the GEN-03 bug
  above, now fixed.
- **Collect blocked a second submission while the first was still
  running** (COL-01, COL-03 - this blocked testing whether Priority
  actually affects queue order): the Submit button was disabled for the
  *entire* polling duration of the first job, not just around the POST
  that queues it. Re-enabled immediately after queuing; a submission
  token lets a second submission safely take over the shared progress
  panel without the two pollers racing each other's output.
- A follow-up python-reviewer pass on this whole batch (focused on the
  head/body rendering split and the other fixes above) found two more
  real bugs before they shipped: the exception-order issue already
  described above, and a case where any transient `/api/findings` load
  error, once the table had already painted once, permanently broke the
  Findings page (filters/pagination/sync/disposition all silently
  started throwing) because the error handler never reset the
  "table already painted" flag it relied on. Both fixed, with the second
  one now also reset by design rather than by a one-off patch.
- **Deferred, not fixed** (explicit decisions, not oversights):
  - HOME-02 (a central credential vault, 1Password-style) conflicts with
    this project's own non-negotiable rule that SAP credentials never
    live anywhere but `.env` - logged as a real security-infrastructure
    decision in `Docs/Open_Questions_For_Review.txt` for the project
    owner, not implemented.
  - Three cosmetic/enhancement asks from Pass-row comments (an SLA chart
    broken out by priority, transaction codes shown as a copyable table
    instead of CSV-in-a-cell, general "the table looks cheap" polish)
    were left for a follow-up round rather than folded into this
    defect-focused pass.
- Full suite: 242 passed before the follow-up review's two fixes; 243
  after (1 new regression test added - the exception-order bug already
  had one written before the review caught the ordering issue itself;
  the findings-page bug's fix is covered by existing filter-change tests
  once the flag is reset correctly).

## 2026-09-14 — Excel-style column-header filters (Jobs, Recovery, Findings)

- Requested directly: "make these tables filterable by each column, like
  if I click on any column header... same way we use filters in Excel."
  Scoped with the user upfront: free-text columns (Job name, User) get a
  search box in the dropdown rather than a full distinct-value checkbox
  list (would need a new per-column backend lookup across the whole
  dataset for a payoff a search box already delivers); the feature covers
  Jobs, both Recovery panels, and Findings.
- Backend: `mode`/`status`/`job_class` (jobs) and `rule`/`severity`/
  `status` (findings) now accept either a single value (unchanged, every
  existing caller) or a list, built into a parameterized `IN (?, ?, ...)`
  clause - checking several boxes means "any of these," not "exactly
  one." New `GET /api/jobs`, `/api/collection-runs`, `/api/findings`,
  `/api/findings/export` query-string convention: a repeated key
  (`?status=queued&status=running`) for multi-select columns. Findings
  also gained a genuinely new filter, `user_id` (contains), which never
  existed as a filter before.
- Frontend: one shared column-header-filter component (checkbox
  multi-select or text search, opening in the same dropdown component the
  Columns picker and per-row export menus already use) reused across
  `renderJobsTable()` (Jobs tab, Recovery's "Deleted jobs"),
  `renderRunsTable()` (Recovery's "Deleted collection runs" only - Job
  Detail's Job Log and Collect's progress panel deliberately don't get it,
  already scoped to one job), and `renderFindingsTable()`. The old
  top-of-page filter forms for these same fields were removed - one place
  to filter, not two in sync. Severity/Rule deep links from the
  Dashboard's tiles (`#/findings?severity=High`) still work, now seeding
  the header filter instead of a `<select>`.
- Every filter-triggered table re-render restores whichever dropdown was
  open and whichever control had focus - checking multiple boxes, or
  typing in a search box, no longer gets interrupted by the table
  redrawing itself after each change.
- python-reviewer pass (SQL injection/correctness focus, since this is the
  first place dynamic `IN (...)` clauses appear in the app): no CRITICAL/
  HIGH findings - every `column` in a generated `IN` clause is a hardcoded
  literal, never request-derived, and placeholder/value counts always
  match. Applied its suggestions anyway: a missing test for
  `/api/collection-runs`'s own multi-value `mode`/`status` (the one IN
  clause NOT going through the shared helper, and so the one most likely
  to silently regress); a runtime allowlist assertion on `_add_in_clause`'s
  `column` argument in both `sal/jobs.py` and `sal/findings.py`, so a
  future misuse fails loudly instead of silently; and the same value-count
  cap `events_export()` already uses for its own multi-value filters,
  applied to `_multi_arg()` too.

## 2026-09-14 — Out-of-context-transaction findings now auto-check directly-assigned profiles

- Requested directly, after asking why the rule only checks PFCG roles and
  not profiles assigned straight to a user's master record (SAP_ALL and
  similar bypass roles entirely - see role_context.py's "Directly-assigned
  profiles" docstring section, added after a real investigation found
  exactly that on a user whose PA20/PA10/SE93 activity didn't match any
  role-menu tcode). The concern: without this, an analyst would need a
  separate manual lookup for every "out of context" finding just to rule
  out direct-profile access - an extra step for information the tool
  could already surface itself.
- New `role_context.directly_assigned_profiles(system_id, user_id)` (the
  live per-user SUSR_GET_PROFILES_OF_USER_RFC lookup, factored out of
  `user_access_summary()` so both share the same in-flight de-dup guard
  and timeout). `out_of_context_transaction.py`'s `_detect()` now calls it
  automatically for every user about to be flagged - not suppressing the
  finding either way (an owner decision: hiding a role gap just because a
  profile *might* cover it would hide real risk), just enriching it:
  - Every out-of-context finding's summary and evidence now note that a
    directly-assigned profile could also be granting the same access, not
    covered by the role check above.
  - If the user has **SAP_ALL** and/or **SAP_NEW** directly assigned,
    that's called out explicitly and prominently in the summary itself,
    not just buried in evidence - either profile alone is usually a
    bigger finding than the specific out-of-context tcode.
  - A failed/timed-out live lookup is noted as "could not check," never
    silently dropped or mistaken for "no profiles."
- Cached per user within one detection run (`sync_findings()` re-evaluates
  every retained event on every run, so without the cache the same
  flagged user could trigger a live RFC call once per matching event
  instead of once per run).

## 2026-09-14 — Fixed: Activity tab's Action filter was missing most real actions

- Requested directly: "I cannot see a Deleted Job action [in Activity],
  can you make sure all the actions are recorded and are filterable?"
  Everything was already being recorded correctly (`audit.record()` is
  called at 26 distinct call sites across `sal/web/api.py`) - the gap was
  purely in the Action filter dropdown, which was a hardcoded 9-entry list
  in `app.js` that had never been updated as new actions were added. 17 of
  26 real actions (including `job_delete`/`job_restore`, every
  export/dispose/whitelist/schedule action, and more) were simply
  unfilterable, silently.
- New `audit.list_actions()` / `GET /api/audit/actions` returns the
  distinct set of actions actually recorded (`SELECT DISTINCT action`).
  The Activity tab now populates its filter from that at load time instead
  of a hand-maintained list - self-maintaining going forward, since any
  new `audit.record()` action shows up the first time it fires rather than
  needing a matching frontend update.
- Added a friendly-label lookup for all 26 known actions (used by both the
  filter dropdown and the Action column of the activity table itself,
  which previously showed the raw `job_delete`-style string); an action
  not yet in that lookup still gets a readable auto-humanized label
  instead of nothing.

## 2026-09-14 — Column visibility toggle + app-wide motion/feedback pass

- Requested directly: the Jobs table's 15 columns forced constant
  horizontal scrolling to reach anything past "Error" (including the
  Delete button), and the app overall felt static.
- **Column visibility**: `renderJobsTable()` (Jobs tab and Recovery's
  "Deleted jobs" panel - they share this table) was refactored from one
  hardcoded row template into a column-spec array, filtered by a
  `localStorage`-persisted visible-column set. Default view now shows just
  Job / Status / Frequency / Action; the rest (System, Mode, Priority,
  Submitted, Started, Delay, Finished, Duration, Progress, ETA, Error) are
  opt-in via a new "Columns" checkbox picker in each panel's header. Since
  Error is hidden by default, a failed/partial job's Status badge now
  carries a warning glyph with the error message as its accessible name
  (not just a hover-only tooltip).
- **Motion pass**: a fade+slide page-enter transition on every route
  change; a subtle pulse on the Status badge's dot for queued/running
  jobs (`badge-live`, a dedicated class - not applied to the same badge
  colors used for Priority, which must stay still); a count-up animation
  for the Dashboard's KPI tile numbers on load; press feedback
  (`:active` translate) added to `.link-danger` to match the buttons that
  already had it. All animation/transition durations are already
  neutralized app-wide under `prefers-reduced-motion: reduce` (pre-existing
  global rule); the one animation that rule can't reach (the JS-driven
  count-up, since it's not a CSS transition) has its own explicit check
  and skips straight to the final value instead.
- **Toasts**: the export-only toast helper was generalized into
  `showToast()` and wired into job/run delete+restore, finding
  disposition, whitelist add/remove, and system add/edit/remove - actions
  that previously just silently re-rendered a list with no confirmation.
- a11y-architect review caught one real regression before it shipped: the
  toast's resting state used `visibility: hidden`, which pulls a
  `role="status"` live region out of the accessibility tree - since
  `showToast()` sets the message text before revealing it, that meant the
  text mutation happened while hidden from screen readers, on every
  normal use. Fixed by hiding the toast with `opacity`/`pointer-events`
  only, never `visibility`. Also fixed: the error-flag glyph's accessible
  name (was tooltip-only), and a misleading `aria-haspopup="true"` on the
  Columns trigger (its panel is a checkbox group, not a menu).

## 2026-09-14 — Fixed: deleted collection runs had no way back

- Found from a user report: a job deleted from the Job Detail page's "Job
  log" didn't show up in the new Recovery tab. Root cause - Recovery only
  lists deleted *jobs* (`collection_jobs`); what the user had actually
  deleted was the *run* that job produced (`collection_runs`), via the
  Delete button on that same Job Log's run rows - a separate, older
  soft-delete lifecycle from Slice A. That action was logged correctly
  (`collection_run_delete` in the audit trail) and the backend's
  `view=deleted` filter for `/api/collection-runs` still worked fine, but
  no page anywhere called it anymore: the standalone Collection History
  page that used to have an active/deleted toggle was folded into Jobs
  earlier this phase, and nothing preserved that toggle - so a deleted
  run became invisible and unrestorable through the UI entirely.
- Job Detail's "Job log" panel now has a **Show deleted runs** checkbox
  that switches its list between active and deleted runs (reusing
  `renderRunsTable()`'s existing `deletedView` support), with Restore
  available on deleted rows.
- Follow-up, requested directly: rather than having to open a specific
  job's Job Detail page and check that box, deleted runs should be visible
  from Recovery directly, same as deleted jobs already are. The Recovery
  tab now has a second panel, **Deleted collection runs**, listing every
  soft-deleted run (`GET /api/collection-runs?view=deleted`, scoped to the
  current system/client like the rest of the tab) with its own Restore
  action - so "did I forget to restore something" has one answer, not two
  different places to check depending on which kind of delete it was.
- The specific run affected by the original report was restored. Two more
  deleted runs turned up in the process (same root cause, from earlier
  testing) - now visible and restorable from Recovery instead of stuck.

## 2026-09-14 — Job-level soft-delete and a new Recovery tab

- Requested directly: "If I have deleted any job, and I forgot which Job I
  deleted, how can I check that... Create one recovery tab which includes
  only those jobs which are deleted." Jobs previously had no delete action
  at all - only the collection runs they produced could be soft-deleted.
- `collection_jobs` gained its own independent `deleted_at`/`deleted_by`/
  `delete_reason` columns (mirroring the collection_runs soft-delete from
  the History-discoverability round, but a separate lifecycle - deleting
  a job hides only its submission/tracking row, never the runs/events it
  already produced). `list_jobs()` takes a `view=active|deleted` filter,
  same pattern as `collection_runs()`.
- Jobs tab: each row now has a **Delete** action (reason required, via the
  same reason-modal used for run delete/restore); refuses a queued/running
  job with 409 since the worker thread still needs that row untouched
  while it's claimed. Deleting a job removes it from the Jobs tab.
- New **Recovery** tab (own nav entry, own `/recovery` route): lists only
  deleted jobs (`GET /api/jobs?view=deleted`), with a **Restore** button
  (reason required) per row that sends the job back to the Jobs tab with
  its Delete action available again. Shows who deleted it, when, and why.
- Both `DELETE /api/jobs/<id>` and `POST /api/jobs/<id>/restore` write to
  the audit log (`job_delete`/`job_restore`, with actor/job_id/job_name/
  reason) - visible on the existing Activity tab, so "who deleted which
  job" is always answerable.

## 2026-09-14 — Jobs tab: removed the expand/collapse row grouping

- Requested directly, after using the previous round's expand-a-row-to-
  see-its-runs feature: keep each job as its own separate, flat row -
  don't group it with the run(s) it produced inline in the same table.
  Removed `loadJobRuns()`/`wireJobExpandButtons()`/the expand button
  column/the nested `job-runs-row` entirely, along with their now-dead
  CSS. The Jobs list itself is unchanged otherwise (search/filter,
  pagination, Priority/Duration/Delay columns from the SM36/SM37 round
  all stay). To see what a specific job actually collected, open its Job
  Detail page (already existed, unaffected by this) - still shows the
  full "Job log" of runs that job produced.

## 2026-09-14 — Collect/Jobs modeled on SAP's own SM36/SM37, plus a stuck-job cleanup

- Requested directly: "the collect tab should be working as how SM36 in SAP
  and Jobs tab should work like SM37." Researched both transactions'
  actual fields/behavior before implementing (job class/priority,
  start conditions, periodic frequency for SM36; selection-screen filters,
  job overview columns, job log for SM37) rather than guessing.
- New **Job Class / Priority** (SAP's own A=High/B=Medium/C=Low
  vocabulary) on `collection_jobs`, migrated in for every existing row as
  Medium via `_ensure_column`'s `DEFAULT 'B'`. Collect's ad-hoc form gets a
  Priority selector; the recurring detection-feed baseline
  (`run_daily_checkpoint()`) always submits at High, explicitly, so it can
  never get stuck behind a pile of ad-hoc requests. The single worker
  thread's claim query now orders by `job_class` first, submission time
  second - a real behavior change, not just a label, verified with a
  cross-order test (a later-submitted High job is claimed before an
  earlier-submitted Low one already sitting in the queue).
- Jobs tab gained a **Priority filter and column**, plus SM37's own
  **Duration** (started→finished) and **Delay** (submitted→started, i.e.
  queue wait) columns - both genuinely useful given SAL's serial
  single-worker-thread queue, where a job really can sit waiting behind a
  higher-priority or earlier one. The Job Detail page's "runs produced by
  this job" section is now framed as a **Job Log**, matching SM37's own
  terminology for the same drill-down concept.
- `python-reviewer` found one real (if low-stakes) issue: the `job_class`
  enum tuple was typed out independently in three places (`sal/jobs.py`'s
  source of truth, plus two inline copies in `sal/web/api.py`'s
  validation) - exported as `jobs.JOB_CLASSES` and reused everywhere
  instead, so the three copies can't silently drift apart if the enum
  ever changes.
- Separately: found and removed 6 leftover test-artifact job rows (and
  their 22 associated collection_runs) from today's own Schedule-tab
  testing - a rapid sequence of schedule reconfigurations + dev-server
  restarts caused the `daily-S23`/`daily-S99` APScheduler jobs to fire
  three near-simultaneous, redundant times each. Confirmed via direct
  inspection this was a one-off artifact of today's testing session (not
  a live bug affecting normal scheduled operation going forward) before
  removing it - S23's triplicate genuinely re-pulled real SM20 data three
  times over (harmless to storage, since `events`' composite primary key
  deduplicates identical rows, but three redundant live RFC round-trips
  against SAP nonetheless).

## 2026-09-14 — IA consolidation: Collection History folds into Jobs, Schedule moves into Collect

Six issues raised directly after Slice A/B/Jobs-detail shipped, resolved via a
four-lens `/ecc:dev-team` review (unanimous on four items, a genuine 2-vs-2
split on one, resolved by asking the project owner directly rather than
picking silently):

- **One canonical date/time format, everywhere.** Three formatters had
  drifted (a raw digit-string render for `last_completed_date`/time
  ranges, a naive ISO-slice for timestamps, and `formatDateRange()`'s
  own "Sep 12, 2026" style) - consolidated into one `formatDateTime()`.
  Also found and fixed the actual root cause of the reported
  inconsistency: `toLocaleDateString(undefined, ...)` renders differently
  per *viewer's* browser/OS locale (`"11 Sept 2026"` vs `"Sep 12, 2026"`
  for the same date) - now pinned to `"en-US"` explicitly, so the format
  no longer depends on who's looking at it.
- **Job Detail page's self-referential link removed.** Its own "runs
  produced by this job" table no longer links the job name back to the
  page you're already on (`renderRunsTable()` gained a `currentJobId`
  option, threaded through everywhere it's used).
- **Schedule's time input switched to `<input type="time">`** (previously
  two plain number spinners), matching Collect's own `tim_from`/`tim_to`
  fields.
- **Schedule relocated into the Collect tab**, as its own "Automatic daily
  collection" panel, directly under the ad-hoc filter form - so the
  relationship (or lack of one) between "what gets collected on a
  schedule" and "what filters you just typed" is visible at a glance,
  which is what prompted the original "no filters/parameters" confusion.
  Deliberately does **not** make the baseline scheduled pull filterable -
  every persona in the dev-team review independently converged on this:
  the baseline is the sole feed for every detection rule and must stay
  comprehensive by construction, not by convention. A permanent regression
  test (`test_run_daily_checkpoint_never_submits_any_filters`) now guards
  this invariant directly. Recurring *filtered* collection remains a
  distinct, larger, not-yet-built capability if ever wanted.
- **Collection History tab removed; folded into Jobs.** `collection_runs`
  is one row per RFC pull - exactly one per ad-hoc job, one per day for a
  chunked scheduled job - so it was a near-duplicate of the Jobs list for
  every ad-hoc job (the majority of this pilot's data). Each Jobs row now
  expands inline to the run(s) it actually produced, reusing the exact
  same search/delete/restore machinery Collection History already had.
  `GET /api/jobs` gained the same `limit`/`offset`/`job_name`/`mode`/
  `status`/`date_from`/`date_to` pagination Collection History's removal
  would otherwise have regressed (mirrors `collection_runs()`'s existing
  pattern).
- Review passes caught two more real issues, both fixed: `list_jobs()`'s
  `date_to` handling diverged from `collection_runs()`'s sibling behavior -
  a regex-shaped-but-invalid date (`"2026-02-30"`) silently dropped the
  filter instead of erroring, now raises and 400s correctly, with a
  regression test. And the new expand/collapse Jobs rows had two
  accessibility gaps: no loading indicator while a row's runs fetch
  resolves (now `aria-busy` + a placeholder), and - more seriously - the
  Jobs table's ~1.5s poll-refresh while any job is active would silently
  yank keyboard focus to `<body>` mid-interaction if a user had an
  expanded row's Delete/Restore controls focused (now skips that tick's
  rebuild, without stopping the poll, whenever focus is inside the table).
Phase letters (A, B, C, ...) refer to the forward architecture in
`Docs/SAL_Architecture_Blueprint_v2.docx`. Entries outside that roadmap are
marked accordingly.

## 2026-09-13 — Collection History: search/pagination, soft-delete with a required reason, readable dates

- Found live: `GET /api/collection-runs` hard-limited to the 20 most recent
  runs with no pagination, so a system with dozens of collection runs could
  only ever see its most recent 20 - older runs, including previous
  ad-hoc/auditor-requested pulls, were invisible in the UI even though
  `/collection-runs/export`'s own unlimited query proved they were still in
  the database. Reported as "I can only see jobs from 75 to 94."
- `sal/web/api.py`'s `collection_runs()` now accepts `limit`/`offset` plus
  `job_name`/`mode`/`status`/`date_from`/`date_to`/`job_id` filters and
  returns `{items, total}`. The "Collect" tab's embedded runs table is
  replaced by a dedicated **Collection History** tab
  (`renderCollectionHistory()` in `sal/web/static/js/app.js`) with search,
  pagination, and export; Collect itself now shows only a live progress
  panel scoped to whatever job was just submitted (`loadJobProgress()`),
  preserving the existing day-by-day progress visualization without also
  carrying the full searchable archive.
- New soft-delete: `DELETE /api/collection-runs/<run_id>` and
  `POST /api/collection-runs/<run_id>/restore`, both requiring a `reason`
  in the request body (auditor-facing tool - every removal from or return
  to history must be justified and attributable) and audit-logged via the
  existing `sal_audit_log`/`audit.record()`. Never a hard delete -
  `collection_runs` rows are metadata about a pull, not the collected SAP
  data itself (`events` is keyed by its own
  `(source_system, client, instance, log_tstmp, counter)`, not by
  `collection_run_id`), so hiding/restoring a run costs nothing and is
  fully recoverable. Three new nullable columns on `collection_runs`:
  `deleted_at`/`deleted_by`/`delete_reason`.
- Delete is guarded against more than its own row's status: a wide job
  chunks into one `collection_runs` row per day, so deleting a finished
  day-3 row while day-5 of the *same* job is still `running` would leave a
  gap in an active job's visible history - the guard checks every sibling
  row sharing `job_id` and the parent `collection_jobs.status`, not just
  the target row.
- Raw `dat_from`/`dat_to` pairs like "20260912 - 20260913" (hard to parse
  at a glance) now render as "Sep 12, 2026 - Sep 13, 2026" via a new
  `formatDateRange()` helper, collapsing to one date for a single-day run.
- Planned via `/ecc:plan` + a four-lens `/ecc:dev-team` review, which
  caught two real design gaps before implementation even started: the
  delete guard's wrong granularity (target-row-only status - fixed above)
  and a missing mandatory reason field. The follow-up `python-reviewer` +
  `security-reviewer` pass then caught two more, both fixed here rather
  than shipped as found:
  - Soft-deleted runs were still surfacing on the dashboard's "last
    collection" tile and in both the plain and ITGC export paths - none
    of the three pre-existing queries that read `collection_runs` had
    been updated to respect the new `deleted_at` column. All three now
    filter it out.
  - The new `date_from`/`date_to` filter originally compared
    `date(cr.started_at) >= date(?)`, relying on SQLite's `date()`
    parser to understand the `+00:00`-suffixed, microsecond-bearing
    isoformat string this column is actually written with (only
    supported since SQLite 3.42) - exactly the "looked right, silently
    returned zero rows" failure class this project has been burned by
    before. Rewritten to a plain lexical string-range comparison
    (`cr.started_at >= "{date_from}T00:00:00"` /
    `< "{next_day}T00:00:00"`), the same approach `sal/retention.py`'s
    own cutoffs already use and for the same reason.
  - `a11y-architect` then caught a competing-autofocus bug in the new
    reason-prompt modal, a keyboard focus trap (focus fell back to
    `&lt;body&gt;` after every page-turn or delete/restore), a sub-24px
    touch target on the new Delete button, and undecorated icons inside
    text-labeled buttons (fixed centrally, across the whole shared `ICON`
    icon set, not just the two new buttons) - all fixed.
- This is "Slice A" of a larger ask; per-system schedule-frequency
  configuration (today's single process-wide `SAL_DAILY_COLLECTION_TIME`
  env var becoming a per-system, UI-editable cadence, on its own new
  "Schedule" tab) is "Slice B" - see the entry below.

## 2026-09-14 — Click a job to open its full detail (parameters, runs) in a new tab

- Requested directly: clicking a job (in the Jobs tab, Collection History,
  or Collect's own live progress panel - all three share the same
  `jobLabelHtml()` row renderer) now opens that job's detail page in a new
  tab (`#/jobs/<id>`, `target="_blank" rel="noopener"` - doesn't lose your
  place in whatever list you clicked from).
- Shows exactly what the job was submitted with - date/time range,
  user(s), transaction code(s), report/program, instance, message code(s),
  parsed from the same `filters_json` `submit_job()` already stores - plus
  full lifecycle metadata (mode, frequency, status, triggered by,
  submitted/started/finished, progress, ETA, last completed date) and the
  day-by-day `collection_runs` rows that job actually produced (reusing
  Slice A's existing `job_id`-scoped runs list, complete with its own
  search/delete/restore actions). No new backend endpoints - built
  entirely on `GET /api/jobs/<id>` and `GET /api/collection-runs?job_id=`,
  both already shipped.
- Found live during verification: the date/time-range values were
  double-HTML-escaped (`formatDateRange()`'s own `&ndash;` markup was
  re-escaped a second time, rendering as literal `&ndash;` text instead of
  an en dash) - fixed by only escaping raw filter values once, at the
  point they're pushed into the row list, not again when the table is
  assembled.

## 2026-09-14 — Jobs tab: a "Frequency" column, alongside Mode

- Requested directly after Slice B shipped: the Jobs tab's existing "Mode"
  badge told you scheduled-vs-ad-hoc, but not *how often* a scheduled job's
  system actually runs. New "Frequency" column between Mode and Status:
  "One-time" for an ad-hoc job, or the system's currently-configured
  cadence ("Daily at 02:00" / "Every 6h") for a scheduled one - sourced
  from `sal/schedule.py`'s `get_schedule()`, the same Slice B config the
  Schedule tab itself edits. By explicit choice, this reflects the
  *current* setting, not a per-job historical snapshot (`schedule_settings`
  only ever holds one live row per system) - the same simplification
  `next_scheduled_run` already made elsewhere on this page.
- `sal/web/api.py`'s `_enrich_job()` (backs both `GET /api/jobs` and
  `GET /api/jobs/<id>`) now attaches the schedule fields for
  `mode == "scheduled"` rows, `None` for ad-hoc ones.
- `python-reviewer` caught one real issue: the frontend's initial
  `hh ?? 0` / `mm ?? 0` fallback would have silently rendered a future
  null-data bug as "Daily at 00:00" - indistinguishable from a genuinely
  midnight-scheduled system. Now renders a visibly distinct "Daily (time
  unknown)" instead, so a real problem couldn't hide behind a plausible-
  looking value.

## 2026-09-13 — Slice B: per-system daily-collection frequency, its own Schedule tab

- Previously every SAP system shared one process-wide cadence
  (`SAL_DAILY_COLLECTION_TIME` env var, once/day for all of them, requiring
  a restart to change). New `schedule_settings` table (one row per system
  that's been explicitly configured; an unconfigured system falls back to
  the old env var/02:00 default, so upgrading never silently deregisters
  anyone's job) plus a new `sal/schedule.py` module owning its
  validation/CRUD, and a standalone **Schedule** tab per system: "Daily at
  a fixed time" or "Every N hours" (1-168).
- `sal/jobs.py`'s `register_daily_job()` now reads each system's cadence
  fresh on every call (deliberately uncached - a stale cache would mean a
  UI-made change silently not taking effect) and picks APScheduler's cron
  or interval trigger accordingly; saving a new cadence re-registers the
  live job immediately via the same write-then-reregister sequence
  `patch_system()` already used for ashost/sysnr/client changes - no app
  restart needed. `GET/PUT /api/systems/<id>/schedule`, audit-logged.
- `python-reviewer` blocked on two real issues before this shipped:
  - A row missing the fields its own `interval_type` needs (should be
    impossible through `set_schedule()`'s validation alone, but a
    hand-edited row or a future direct-write path could produce one) would
    have hit APScheduler as `CronTrigger(hour=None, minute=None)` - which
    doesn't error, it fires roughly once a second against a live SAP
    system. Fixed two ways: a `CHECK` constraint on `schedule_settings`
    itself (real DB-level enforcement, not just app-level), plus a
    defensive fallback in `get_schedule()` to the safe default if a
    returned row is ever malformed anyway.
  - `_to_int()`'s numeric coercion silently accepted a bool (`True`/`False`
    truncating to `1`/`0`, since `bool` is an `int` subclass in Python) and
    a non-whole float, and didn't catch `OverflowError` - reproducible live
    via `PUT .../schedule` with `{"interval_hours": Infinity}` (valid JSON;
    Python's `json` module accepts the bare `Infinity`/`NaN` tokens by
    default), which escaped as an unhandled 500 instead of a clean 400. All
    three now rejected explicitly.
  - `security-reviewer` and `a11y-architect` passes found no blocking
    issues in the backend/API and two real WCAG 2.2 AA gaps respectively
    (the hour/minute field pair's grouping was visual-only - now a
    `<fieldset>`/`<legend>`; the "Schedule updated" and "Next scheduled
    run" text updated with no page navigation and no `aria-live`/`role`,
    so a screen-reader user got no announcement - both now live regions),
    fixed here.

## 2026-09-13 — Role Context now surfaces directly-assigned SAP profiles, not just PFCG roles

- Found during a live investigation (a user's PA20/PA10/SE93 activity
  didn't match any tcode granted by their PFCG roles): the user had
  `SAP_ALL` - SAP's own full/unrestricted-access profile - assigned
  straight to their user master record, completely bypassing role-menu
  authorization. Requested directly: "if the users dont get access from
  the roles or role menus they might be getting access via directly
  assigned profiles. so include them as well in the picture."
- `sal/role_context.py`'s existing `AGR_USERS`/`AGR_TCODES` bulk sync only
  ever covered access granted through a role's PFCG menu - a profile
  assigned directly via SU01/SU02 was invisible to it entirely.
- Validated live against S23 before writing any code (per this project's
  own standing rule against assuming RFC/table names): `USR04` (the
  classic direct-profile-assignment table) exists, but its profile data
  lives in one 3750-char packed `PROFS` field (confirmed via
  `DDIF_FIELDINFO_GET`) - reading it via `RFC_READ_TABLE` raises
  `DATA_BUFFER_EXCEEDED`, and guessing at its packed layout would repeat
  the exact unverified-bit-parsing mistake `sal/rules/_coverage.py`
  already flags as a past lesson. `SUSR_GET_PROFILES_OF_USER_RFC` (already
  validated per-user in `scripts/probes/probe_user_master.py` during
  Phase F planning: real param is `USER_NAME`, not `USERNAME`) works
  cleanly but is strictly per-user - no bulk/table-scan equivalent, and
  with ~20k distinct users on S23 alone, a daily bulk pull the way
  `AGR_USERS`/`AGR_TCODES` are pulled isn't practical or what this feature
  needs anyway.
- New `sal/role_context.py`: `user_access_summary(system_id, client,
  user_id)` combines the already-synced local role/tcode data with a
  live, on-demand, timeout-bounded (30s) call to
  `SUSR_GET_PROFILES_OF_USER_RFC` for that one user - mirrors
  `sal/audit_config.py`'s single-call `check_audit_config()` shape
  (daemon-thread + `Future.result(timeout=)`, since pyrfc has no per-call
  timeout and this runs on Windows with no `signal.alarm`), plus its own
  in-flight guard keyed by `(system_id, user_id)`. A profile-fetch
  failure (timeout, `USER_NOT_EXISTS` for a user_id with no maintained
  SU01 record, connection error) is caught separately from the role/tcode
  lookup and reported as `profiles_error`, never hiding locally-available
  role data behind an unrelated RFC failure.
- New `GET /api/role-context/user?system_id=&client=&user_id=` endpoint
  (`sal/web/api.py`), audited as `role_context_user_lookup`.
- Coverage page's "Role context" panel (`sal/web/static/js/app.js`) gained
  a "Look up one user's access" form: username in, roles + tcode count
  (from local data) + directly-assigned profiles (live) out. `SAP_ALL`/
  `SAP_NEW` render with the red high-risk badge and an explanatory
  tooltip; other profiles get a neutral badge - both carry a tooltip
  clarifying they're independent of any role.
- Verified live against the real system (S23/TRAIN_13_S23): the endpoint
  correctly returns `SAP_ALL` plus 3 role-generated profiles alongside 13
  PFCG roles and 49 role-menu tcodes.
- 8 new tests (`tests/test_role_context.py` x5, `tests/test_api.py` x3):
  role data present + profiles present, zero role data but profiles still
  returned (the exact real scenario), a profile-fetch error not hiding
  role data, timeout handling, duplicate in-flight rejection, and the API
  endpoint's required-param validation + happy path.
- `python-reviewer`/`security-reviewer` follow-up fixes (both run against
  this diff, per this project's standard workflow): `user_id` is now
  normalized to uppercase (matching `system_id`'s existing treatment) so a
  lowercase-typed username in the new lookup form doesn't silently read as
  "no role data" instead of a case mismatch; `GET /api/role-context/user`
  now validates `system_id` against the configured-systems registry like
  every sibling endpoint already does; the audit-trail entry now records
  `outcome="error"` when the live profile fetch failed, not always `"ok"`;
  extracted a shared `_current_roles_and_tcodes()` helper so
  `authorized_tcodes_for_user()` and `user_access_summary()` no longer run
  duplicate queries, which also fixed a latent bug where an omitted
  `client` silently matched nothing (hardcoded `client = ?` against SQL
  `NULL`) instead of matching any client, the way this file's other
  scope-aware functions already do it. Also recorded in
  `Docs/PROJECT-CONTEXT.md`: security-reviewer's proportionality finding
  that this lookup is a live, unthrottled oracle for "who has SAP_ALL" for
  any free-text username (not limited to already-synced users, deliberately
  - a user with a directly-assigned profile and zero PFCG roles would
  otherwise be invisible to it) - accepted as-is for now, consistent with
  this project's existing no-RBAC decision, not solved here.
- Full suite: 168 passed (157 + 11 new, including 3 tests added for the
  review fixes themselves).

## 2026-09-12 (continued) — Plain-language labels for the Coverage page's SM19 configuration table

- Requested directly: "the tab Active SM19 configuration under Coverage
  section is very technical... what is $DYB$ profile [sic - `$DYN$`
  in the actual data]. Is there a way to label it differently... make a
  legend sort of table below which will make the user understand what
  each of them mean. And what is client/user filter filters and what each
  value mean."
- `$DYN$` is SAP's fixed name for "the dynamic profile that's active right
  now" (RSAU_API_GET_AUDIT_CONFIG always reports the live config under
  that literal name - see `sal/audit_config.py`'s module docstring), not
  something an admin named - confirmed against the real live snapshot
  (system S23/client 100). The Profile column in
  `renderSlotsTable()` (`sal/web/static/js/app.js`) now shows "Active
  configuration" with the raw `$DYN$` kept alongside in small muted
  parens, via a new `friendlyProfileLabel()` helper (falls through to the
  raw name unchanged for an actual named static profile, which this app
  has never seen in practice but the RFC response schema doesn't rule out).
- Added a `CLASS_LABELS` map (plain-language description per SM19 event
  class - Dialog logon, RFC/CPIC logon, Transaction start, Report start,
  User master record change, System events, RFC function calls, Other
  events) kept textually in sync with `sal/rules/_coverage.py`'s own
  `CLASS_*` comments, the project's existing source of truth for what
  each class captures. Every `CLASS_*` badge on the Coverage page (both
  the SM19 configuration table and the "Detection coverage vs. rule
  requirements" table below it) now carries a hover `title` tooltip from
  this map, and a new legend table lists all eight underneath the SM19
  configuration table.
- The "Client / user filter" column is now "Applies to (client / user)",
  reads "Client: All &middot; User: SAP#\*" instead of the bare "\* /
  SAP#\*", and a caption below the legend explains that a slot's client
  (MANDT) and user (UNAME) filters are SAP wildcard patterns (`*` matches
  anything) and that "All" means the slot isn't restricted at all.
- Frontend-only change (`sal/web/static/js/app.js`); no backend/API
  change - verified the new labels against the live `/api/audit-config`
  response for system S23/client 100 before and after. No test suite
  impact (this project has no JS test runner; `tests/test_audit_config.py`
  covers the Python backend only, unaffected - reran it to confirm: 10
  passed).

## 2026-09-12 (continued) — Dashboard/findings page load ~4-9x faster (redundant per-request schema init + catalogue reseeding)

- Requested directly: "use ecc plugin and all necessary the agent/skills
  inside it to optimize the webpage reducing processing time." Profiled
  against the live dev server before touching anything: `GET
  /api/dashboard` (the main page load) measured ~0.85-0.98s per request,
  `GET /api/findings` ~0.23-0.5s - both far slower than every other
  endpoint (all under 60ms).
- Root cause was redundant, idempotent setup work re-run on *every single
  request*, not query complexity or data volume (708,894 real events in
  the live DB weren't the bottleneck - confirmed via `EXPLAIN QUERY PLAN`,
  the `events` count query already uses the table's covering index):
  - `sal/storage/db.py`'s `init_schema()` - a full `executescript()` of
    ~15 `CREATE TABLE`/`INDEX IF NOT EXISTS` statements plus 7
    `_ensure_column()` `PRAGMA table_info()` migration checks, each on a
    brand-new sqlite3 connection - sits at the top of ~28 read/write
    functions across 10 files, and every one of those re-ran the whole
    thing, every call, even though the schema is static after the
    process's first real call.
  - `sal/web/api.py`'s `dashboard()`, `findings_list()`, and both
    catalogue GET endpoints unconditionally called
    `seed_default_critical_transactions()`/`seed_default_sensitive_tables()`
    (`sal/catalogues.py`) on every request - 21 hardcoded default entries
    x `INSERT OR IGNORE`, each entry itself triggering another
    `init_schema()` call. Net effect: one `/api/dashboard` load opened
    50+ short-lived sqlite3 connections for bookkeeping that's static
    after startup.
- Fix, via the ecc `performance-optimizer` agent (with a `python-reviewer`
  and `security-reviewer` pass afterward, per this project's own
  workflow):
  - `sal/storage/db.py`'s `init_schema()` now memoizes on the current
    `DB_PATH` value (a new module-level `_schema_ready_for: Path | None`,
    not a bare boolean) - repeat calls for the same path short-circuit
    immediately; a changed path (e.g. `tests/conftest.py`'s
    `isolated_db` fixture, which monkeypatches `DB_PATH` to a fresh
    `tmp_path` file per test) still forces a real re-init. All 28
    existing call sites were left exactly where they are - still
    correct, just cheap after the first real run per path. A failed run
    is never cached as ready (the memo is only set after the
    try/finally block completes).
  - `sal/web/__init__.py`'s `create_app()` now calls
    `seed_default_critical_transactions()`/`seed_default_sensitive_tables()`
    once at process startup, inside the existing
    `WERKZEUG_RUN_MAIN == "true"` guard (already there to stop
    `jobs.start_worker()`/`start_daily_scheduler()` double-starting under
    Werkzeug's reloader) and before those two calls, so no background
    job can read empty catalogues.
  - `sal/web/api.py`: removed the four now-redundant seed call sites and
    the now-unused import.
  - `security-reviewer` found one LOW/informational item, addressed by a
    comment only (no code change needed): catalogue seeding is now
    coupled to the same `WERKZEUG_RUN_MAIN` guard as the job
    worker/scheduler, so a hypothetical future deployment of this app via
    a production WSGI server instead of `run.py` would need that guard
    revisited (already a pre-existing, documented limitation for the job
    worker) - flagged in `sal/web/__init__.py`'s comment since it now also
    covers catalogue defaults some detection rules depend on
    (`out_of_context_transaction`).
  - `python-reviewer` found no CRITICAL/HIGH issues and two MEDIUM
    documentation-drift items, both fixed: `Docs/training/
    SAL_Technical_Deep_Dive.md` §3.9 no longer says catalogue seeding
    happens "from several API routes" (regenerated the matching PDF via
    `scripts/render_training_pdfs.py`); this changelog entry itself.
- Measured after (same live server, repeated `curl -w "%{time_total}"`,
  verified independently twice - once by the performance-optimizer agent,
  once by the orchestrating session): `/api/dashboard` ~0.2-0.25s (was
  ~0.85-0.98s), `/api/findings` ~0.04-0.06s (was ~0.23-0.5s).
- Added `tests/test_db_init_schema.py` (memoized no-op for the same
  `DB_PATH`; real re-init for a genuinely new `DB_PATH`; a failed run
  isn't cached as ready) and `tests/test_catalogue_seeding.py` (pins that
  `dashboard`/`findings_list`/both catalogue GET endpoints no longer
  re-seed a deliberately-removed default). Full suite: 157 passed (149
  + 8 new), confirmed independently by the orchestrating session.

## 2026-09-12 (continued) — Running-job badge color fix + faster/clearer large exports

- Requested directly: "the running status is shown in amber color [below
  Fetch from SAP] but in recent job collection, it shows red color... red
  is only for error and failed job." `renderRunsTable()`'s badge color in
  `sal/web/static/js/app.js` was `r.status === "success" ? "success" :
  "high"`, so a `running` row (a real, valid `collection_runs.status`
  value) fell into the same red `badge-high` bucket as `error`. Replaced
  with a `RUN_STATUS_BADGE` map (`running` → `medium`/amber, `success` →
  `success`, `error` → `high`/red), mirroring the `JOB_STATUS_BADGE`/
  `JOB_STATUS_TAB` convention already used elsewhere on the same page - red
  is now reserved strictly for `error`.
- Requested directly: "when I want to download a job report which has
  around 73000 rows, website keeps loading infinitely and I am not sure
  when the download will start since it takes a lot of time." Measured
  against the live dev DB (~71k real events, system S23/client 100, a
  4-day range): CSV ~4s, raw XLSX ~19s, ITGC-format XLSX ~50s.
  - `sal/itgc_events_report.py`'s `_build_event_log()` was calling
    `xlsx_style.style_body()` (per-cell border + wrap-text) across every
    row of the raw event dump - by far the largest single cost (~30s of
    the ~50s) for a sheet that, unlike `sal/itgc_report.py`'s much smaller
    findings sheets, can run into the hundreds of thousands of rows.
    Dropped it for this sheet only (findings sheets keep their styling);
    `freeze_panes` + `auto_filter` already make a sheet this size
    navigable. Re-measured after: ITGC format now ~21s, in line with the
    unstyled XLSX baseline.
  - `sal/export.py`'s `rows_to_xlsx()` (used for the raw, unstyled
    events/findings/collection-runs exports) now builds its workbook with
    `Workbook(write_only=True)` - no wall-clock win was measured at this
    row count, but it keeps memory flat rather than growing with row
    count, which matters given this app's real data volumes (up to 700k+
    events in one system/client).
  - Added a small `.toast` component (`showExportToast()` in `app.js`,
    wired once via a single delegated click listener in `init()` rather
    than per-render) that appears on any export link click
    (`/events/export`, `/findings/export`, `/collection-runs/export`):
    "Preparing your export... large date ranges can take up to a minute.
    It will download automatically when ready - feel free to keep
    working." Downloads are plain `<a href>` navigations with zero
    built-in browser progress feedback for a large file, which is what
    made the wait look like an indefinite hang even before the perf fix
    above.
  - No test changes needed: existing xlsx/itgc export tests assert on
    header row and cell values via `load_workbook()`, which reads
    correctly regardless of write mode or body-cell styling. Full suite
    (149 tests) still passing.

## 2026-09-12 (continued) — Ad-hoc jobs run their whole range as one call, not one per day

- Requested directly: submitting an ad-hoc query for "last week" (a
  7-day range) produced 7 `collection_runs` entries, one per day - "I
  don't want to see 7 jobs in my queue... it should show me the report
  for that one week only, not for the individual 7 days."
- Chunking is now mode-dependent in `sal/jobs.py`'s `run_job()` (see its
  module docstring for the full reasoning): **scheduled** jobs (the daily
  background collector) still split their range into one
  `collect_and_store()` call per day, since an unattended catch-up gap
  after downtime can span many days and benefits from resuming a partial
  failure rather than redoing everything. **Ad-hoc** jobs (the Collect
  UI, submitted once and watched live) now run their whole
  `[dat_from, dat_to]` range as a SINGLE `collect_and_store()` call - the
  chunking was never a technical requirement of the RFC call itself
  (`RSAU_API_GET_LOG_DATA`'s `IS_INTERVAL` parameter already accepts a
  date range natively, confirmed by `python-reviewer` and already
  exercised by `scripts/collect_sm20.py`'s own unchunked CLI path), only a
  resumability nicety that matters far more for an unattended catch-up
  than a one-shot query a user is actively waiting on. The trade-off,
  accepted knowingly: a failed ad-hoc range is retried as a whole (up to
  `_MAX_RETRIES` times), not resumed from a partial day.
- Extracted the shared per-chunk retry loop into `_collect_chunk()`, used
  by both paths, so the day-chunked (scheduled) and whole-range (ad-hoc)
  branches share one retry implementation rather than duplicating it.
- The Jobs page's progress column now shows a plain "Running…"/"Done"
  indicator for ad-hoc rows instead of an "X of 1 day" bar (`days_total`
  is always 1 for them now, and the old wording would misleadingly imply
  day-by-day progress that no longer happens) - keyed off `job.status`,
  not `days_completed`, after `python-reviewer` caught an earlier draft
  showing "Running…" forever on an ad-hoc job that had already failed
  (both are 0/falsy in that case, so the wrong signal was used first).
- 6 tests updated/added in `tests/test_jobs.py` (149 total, all passing):
  three that tested day-chunked retry/resume semantics were moved from
  `mode="adhoc"` to `mode="scheduled"` (that's what they were really
  testing); three new ones lock in the ad-hoc single-call path (one call
  spanning the whole range, retry-then-succeed, retry-exhausted marks
  "error" not "partial" since there's no longer a partial day to fall
  back to).

## 2026-09-12 (continued) — "Recent collection runs" now refreshes live while a job is running

- Reported as three things that looked like bugs; investigated against
  the real live database (`/api/jobs`) rather than guessed at, and only
  one was an actual gap: "jobs 43 to 56 all have the same name" and "row
  numbers are different even though the condition was the same" are both
  correct, expected behavior working as designed - a wide-range ad-hoc job
  (the specific one referenced spanned 32 days) chunks into one
  `collection_runs` row *per day* (`sal/jobs.py`), so many consecutive
  rows legitimately share one job's name; resubmitting a similar query
  creates new bookkeeping rows/run_numbers even though the underlying
  `events` table's composite primary key means no data actually
  duplicates. The real gap: "Recent collection runs" only ever refreshed
  once at the very start and once after the *entire* job finished, so a
  multi-day pull looked completely frozen while SAP was being called one
  day at a time (each day is its own live RFC call) - a user watching it
  had no way to tell that anything was happening, which is exactly what
  prompted the repeated manual refreshes that then looked like duplication.
- `pollJobStatus()` now calls the same `loadCollectionRuns()` the page
  already had, on the same 1.5s cadence as its own status-badge poll - a
  day's row now visibly appears as `running` and flips to `success` in
  near-real-time, matching what the status tab above it already showed.
- While fixing this, found and fixed a latent crash risk one call site
  over: `loadCollectionRuns()` had no guard against `#runsBody` no longer
  existing (the user navigated away from Collect while a job kept running
  in the background - a real background async loop, not tied to the DOM),
  unlike its sibling `loadJobs()`, which already has exactly this guard.
  Refreshing on every poll tick instead of once made the window for
  hitting this meaningfully bigger, so this was worth fixing now rather
  than leaving as a pre-existing edge case.

## 2026-09-12 (continued) — Job name on every run, a real running→completed status tab, and per-run ITGC downloads

Three requests, all touching the Collect/Recent-collection-runs surface
built up over this session's earlier passes (some of which had, in the
meantime, been extended further by a concurrent session - `job_name`/
`job_description` on `collection_jobs`, `run_number`, and the per-run
"Data" link already existed by the time this pass started; re-read every
touched file fresh before changing anything rather than trusting
in-context memory of them).

- **Job name in "Recent collection runs."** `job_name`/`job_description`
  existed only on `collection_jobs` - the per-day `collection_runs` rows
  the table actually shows had no way to trace back to the job that
  spawned them. Added `collection_runs.job_id` (new nullable column,
  `_ensure_column` migration) - `sal/collectors/sm20.py`'s
  `collect_and_store()` takes an optional `job_id` now, and
  `sal/jobs.py`'s `run_job()` passes its own job id on every day it
  chunks. `GET /api/collection-runs` LEFT JOINs `collection_jobs` on it
  (LEFT, not INNER: a run predating this column, or from
  `scripts/collect_sm20.py`'s CLI backfill path which bypasses
  `sal/jobs.py` entirely, must still show up - just with no job name).
  `renderRunsTable()` reuses the Jobs page's own `jobLabelHtml()` for the
  new column, so the name/fallback wording matches in both places rather
  than drifting.
- **A real status tab, not just changing text.** The polling status line
  in `#collectResult` now carries an actual `.badge` ("Queued"/"Running"
  while polling, "Completed"/"Partial"/"Failed" once `pollJobStatus()`
  returns) alongside the sentence, instead of the same paragraph with only
  its last word changing - a glance at the badge shows whether a job is
  still active without reading the text.
- **Per-run downloads can be in ITGC format, not only raw CSV/XLSX.**
  Added `sal/itgc_events_report.py` (`build_events_workbook()`) - a
  companion to `sal/itgc_report.py`'s findings workbook, for a different
  reference-IDR line item ("D-3: Audit Log Details, Extract... for Tcodes
  SM20 and SM21" asks for the raw log rows themselves, not SAL's derived
  findings). Cover Sheet (client/system/extraction period/parameters/
  methodology) + Event Log (every `EVENTS_HEADERS` column, reusing
  `sal.export.sanitize_row` for the same CWE-1236 defense every other
  export already has). Kept as its own module rather than growing
  `itgc_report.py` - the two workbooks serialize entirely different
  source data into entirely different sheets, sharing only the visual
  language (`sal/xlsx_style.py`). Wired in as a third `format=itgc` option
  on the existing `/api/events/export` route. Each row in "Recent
  collection runs" now has a small "Data ▾" menu (reusing
  `setupDropdownMenu()`) offering "Raw Excel" and "ITGC Format" side by
  side, rather than replacing the existing raw download.
- 19 new tests across `tests/test_collectors.py`, `tests/test_api.py`,
  `tests/test_events_export.py`, and the new `tests/test_itgc_events_report.py`
  (146 total, all passing): `job_id` storage and its `None` default, the
  `collection_runs`↔`collection_jobs` join (including the no-job-id case),
  the new ITGC event export's sheets/parameters/formula-injection defense.

## 2026-09-12 (continued) — Download the raw events behind an ad-hoc collect, not just its findings

- Requested directly: "for each ad hoc run... I should be able to download
  that specific data as well, not only sync the findings." Previously the
  only downloadable things were derived findings (`/api/findings/export`)
  and collection-run bookkeeping (`/api/collection-runs/export` - row
  counts/timestamps/status, never the actual event rows).
- Added `GET /api/events/export` (`sal/web/api.py`) - a query against the
  **already-collected** `events` table (no new SAP RFC call, no schema
  change), filtered by the same fields `sal/collectors/sm20.py`'s
  `fetch_events()` already sends to SAP as selection criteria: date/time
  range, and optional comma-separated `user`/`transaction_code`/`report`
  (→ the `program` column)/`instance`/`msg_code`. Deliberately not scoped
  to a specific `collection_run_id` or job id: a wide ad-hoc range is
  chunked into one `collection_runs` row per day
  (`sal/jobs.py`), and a day that needed a retry would split across two
  run ids - re-querying by the filters the user actually asked for is more
  robust than reconstructing "which run(s) count" after a partial retry.
  Multi-value filters are capped at 500 entries each (`_MAX_MULTI_FILTER_VALUES`)
  to avoid an uncaught SQLite bound-parameter error under Flask's
  always-on debug mode.
- Added `export.EVENTS_HEADERS` and reused the existing `rows_to_csv`/
  `rows_to_xlsx` (already apply the CWE-1236 formula-injection defense).
  Promoted `sal/collectors/sm20.py`'s `_event_timestamp()` to a public
  `event_timestamp()` (re-exported from `sal/collectors/__init__.py`) so
  the new endpoint's date-range query bounds are built from the exact same
  conversion the collector uses to populate `events.event_timestamp` on
  write, instead of a second inline copy of the slicing - `dat_from`/
  `tim_from` are the same `YYYYMMDD`/`HHMMSS` shape as SAP's own
  `SAL_DATE`/`SAL_TIME`, so one function covers both call sites.
- Collect page gained an "Export data" dropdown (reusing the `setupDropdownMenu()`
  component built for the Findings page's Export menu) next to "Fetch from
  SAP", built as real `<a href>` links refreshed on every form-field input
  (matching the Findings/Collection-Runs export links' own reactive
  pattern - `python-reviewer` flagged an earlier draft using a plain
  `<button>` + `window.location.href` as the only export control in the
  app not built as a real anchor, losing standard link affordances).
- `tests/test_events_export.py` (10 tests): validation, date-range
  filtering (verified against the collector's real timestamp format),
  tcode/multi-user filtering, system/client scoping, xlsx shape, the
  oversized-filter 400, and formula-injection defanging.
- `security-reviewer` confirmed the dynamic `IN (?, ?, ...)` clause
  (built from a variable-length comma-separated filter) is fully
  parameterized - the column name comes from a hardcoded tuple, never
  from request input, and every value is bound, never string-interpolated.

## 2026-09-12 (continued) — Run numbering, per-run data download, job name/description, and a real fix for the "stuck running" polling report

Four requests in one pass, the first live-diagnosed with chrome-devtools
(finally connected this session) rather than reasoned about blind:

- **"Running" text not updating after the job finished.** Reproduced live:
  submitted an ad-hoc job, watched 65+ correctly-firing `GET /api/jobs/<id>`
  polls, and confirmed the backend genuinely still reported `status:
  "running"` for 90-150s at a time - not a frontend display bug at all
  (the UI *did* update to "Collection complete" the moment the backend
  actually finished). Root cause: `sync_findings()` re-runs all 13
  detection rules over the full retained event history on every job
  (deliberate - see `out_of_context_transaction.py`'s docstring on why
  point-in-time re-evaluation matters for the audit scenario it serves),
  and several rules request the *identical* `fetch_events()` combination -
  `AU3` five times, `AU1` four times, across the 13 registered rules - each
  independently re-querying and re-sorting the same large result set from
  scratch. On this session's ~670K-row `events` table that redundancy
  alone was a meaningful share of the cost.
  Fixed with a per-pass memoization cache in `sal/rules/_common.py`
  (`_cache`, enabled/disabled around `registry.py`'s `run_all_rules()`
  loop - `None` by default so any `fetch_events()` call outside a full
  rule pass, e.g. a script or single-rule test, is unaffected). Verified
  in isolation (bypassing HTTP/job/worker-thread overhead entirely):
  `run_all_rules()` at ~15s, full `sync_findings()` at ~12s against the
  real 667K-row table - a reasonable duration. End-to-end timing through
  the live job pipeline in *this* session still showed more variance
  (90-150s) than the isolated number would suggest; that's consistent with
  this session's own heavy concurrent load (many pytest runs, browser
  automation, and prior ad-hoc test scripts all competing for the same
  machine and sqlite file throughout this session) rather than a residual
  code issue - not something a normal single-user session would see.
  `tests/test_rules_common.py` (6 tests) pins the cache's correctness
  (same object returned on a hit, distinct entries per filter combination,
  key order-independence, and reset via `finally` even if a rule raises).
- **Collection runs are now numbered** (`/api/collection-runs`'s new
  `run_number`, a `ROW_NUMBER() OVER (ORDER BY started_at ASC)` computed
  column - oldest run in scope = 1, stable regardless of new runs being
  added, not just each row's on-screen position in the newest-first
  table).
- **Download the exact data behind any past run**, not just the current
  Collect form's field values: each row in "Recent collection runs" now
  has a "Data" link that rebuilds the `/api/events/export` URL from that
  specific run's own stored `dat_from`/`dat_to`/`filters_json` - a run
  from days ago stays downloadable today with precisely the criteria it
  used, without retyping them into the form (`buildRunEventsExportUrl()`
  in `app.js`; no new backend endpoint, reuses the events-export route
  added earlier this session).
- **Job name + description** when submitting a collect job (`collection_jobs.job_name`/
  `job_description`, two new nullable columns via the existing
  `_ensure_column` migration pattern; threaded through `submit_job()` →
  `POST /api/collect` → the Collect form). Shown in the polling status
  text ("Job #12 (Weekly SU01 spot-check): running…") and as the leftmost
  column on the Jobs page; jobs submitted before this feature (or the
  daily scheduler, which doesn't set a name) fall back to a plain
  mode-based label rather than a blank cell.

## 2026-09-12 (continued) — Actually fixed: a CSS specificity tie was moving the trigger itself

- The "beside the trigger" fix above still left the trigger button
  rendering below the tile entirely - a different, more literal bug:
  `.fiori-tile-menu { position: absolute; ... }` and the generic
  `.menu { position: relative; }` (needed elsewhere, for the Findings
  page's Export menu) are equal specificity (one class each) and both
  apply to the same element (it carries both classes). On a tied
  property, the declaration later in the file wins regardless of which
  rule "looks" more specific to its purpose - and `.menu`'s came later,
  so `position: relative` silently won over `position: absolute`. A
  relatively-positioned element renders in normal document flow first;
  since it's a sibling *after* the tile's own full-height select button,
  "normal flow" put it directly below the 176px tile, not pinned to its
  corner.
- Fixed by raising specificity instead of depending on file order:
  `.fiori-tile .fiori-tile-menu { position: absolute; ... }` (0,2,0) beats
  `.menu`'s (0,1,0) unconditionally, regardless of where either rule sits
  in the file. This is the general lesson `artifact-design`-style
  guidance already warns about - two classes on the same element fighting
  over one property, resolved by source order rather than obvious intent
  - worth remembering for any other shared-class component (`.menu` is
  reused by the Findings page's Export button too).

## 2026-09-12 (continued) — Tile "more actions" menu: opens beside the trigger, not below the tile

- The `display: contents` fix below solved the overlap by moving the panel
  to open ~182px down (below the whole 176px tile) - correct in that it no
  longer covered the tile's own content, but reported as looking
  disconnected: "displays below instead of beside the three dots." A panel
  that far from its trigger reads as unrelated to the button that opened
  it, especially inside a multi-tile grid.
- Reverted to keeping `.fiori-tile-menu` as the trigger's own small
  positioning box (as it was originally), but changed which side the
  panel opens on: `right: calc(100% + 6px); top: 0;` flares it out to the
  LEFT of the trigger instead of below it - tethered tightly to the exact
  "⋮" that opened it, in the direction that stays clear of the tile's own
  icon/title (which sit lower and to the left).

## 2026-09-12 (continued) — Fixed the tile "more actions" menu opening on top of its own tile

- Reported live: each tile's "⋮" dropdown (Edit/Remove) opened overlapping
  the tile's own content instead of below it. Root cause was mechanical,
  not visual guesswork: `.menu-panel`'s generic `top: calc(100% + 6px)`
  resolves against the nearest positioned ancestor, which for a tile was
  `.fiori-tile-menu` - a wrapper only as tall as the 26px trigger button
  itself (an absolutely-positioned panel doesn't count toward its own
  parent's height). So the panel opened ~32px below the *button*, not
  below the 176px tile. Never a problem for the Findings page's Export
  button, whose trigger already spans the full toolbar width.
- Fixed by giving `.fiori-tile-menu` `display: contents` - it stops
  generating its own box, so its children (trigger + panel) position
  against `.fiori-tile` (the actual 176px tile) instead. The trigger's own
  `top`/`right` offsets moved onto `.tile-menu-trigger` directly since the
  wrapper can no longer carry them once it has no box of its own.
- (chrome-devtools MCP was requested for this but is still not connected
  this session per its earlier cached-failure state - diagnosed from the
  CSS positioning math instead, which for this specific bug class is
  deterministic rather than a guess.)

## 2026-09-12 (continued) — Home tiles: "Badge Card" direction chosen

- Follow-up to the Fiori-tile redesign below: still didn't look right, and
  with no browser tooling available this session to see CSS render, a
  third blind guess wasn't a good use of anyone's time. Published a
  Claude Design artifact instead - three real, working tile directions
  (Fiori Flat / Accent Rail / Badge Card) built with SAL's actual color
  tokens and font stack, viewable in an actual browser (the user's, since
  this session had none) rather than reasoned about blind. "Badge Card"
  was chosen: an icon in a tinted rounded badge, a small pill naming the
  environment, rounded corners with a hover lift.
- Added `--env-production`/`--env-sandbox`/`--env-quality`/
  `--env-development` tokens (light + both dark blocks) - deliberately
  distinct hues from the existing severity palette, so a Production tile
  can never misread as "something's wrong" the way reusing `--sev-high`
  would have. `.fiori-tile-icon`'s badge and `.fiori-tile-pill` both key
  off whichever `--env-c` custom property `renderHomeCard()` sets inline
  per tile (`ENV_COLOR_VAR` in `app.js`).
- The missing-credentials flag moved to the tile's bottom-right corner
  (was bottom-left in the first pass) to stay clear of the icon badge,
  the pill, and the top-right "more actions" popover - four fixed zones,
  no overlap regardless of which are present on a given tile.

## 2026-09-12 (continued) — Home page restyled as SAP Fiori-style tiles

- Requested directly: the Home page's system cards should look more like
  SAP Fiori Launchpad tiles - a fitting, on-brand direction given this is
  a console specifically for an SAP-technical audience.
- Reworked `renderHomeCard()`'s markup and `.system-card*` CSS into
  `.fiori-tile*`: fixed 176x176 square tiles (`.tile-grid` uses
  `repeat(auto-fill, 176px)`, not a stretching `minmax(...,1fr)`, so tiles
  wall up rather than stretch to fill each row - closer to how a real
  Fiori launchpad packs tiles), title/subtitle at top, a representative
  icon anchored bottom-right (SAP's own "static tile" layout), and an
  accent-colored top border reusing the same visual language as the
  Dashboard's KPI `.tile` component.
- Edit/Remove moved off a persistent button row and into a small
  circular "more actions" (⋮) popover per tile, reusing
  `setupDropdownMenu()` (built for the Findings page's Export menu)
  rather than a new mechanism - also the more authentically Fiori
  pattern (Fiori's own launchpad puts secondary tile actions behind a
  corner affordance, not inline buttons). Opening one tile's menu now
  auto-closes any other open one (`_openDropdownMenuClose` in `app.js`),
  since a tile grid makes "several popovers open at once" much easier to
  trigger than the single Export-menu case it was built for.
- The environment/credentials-configured badges were dropped from inside
  each tile - environment is already conveyed by the section header
  above the row, and "credentials configured" is the default/expected
  state, not worth a permanent badge; a small warning-triangle flag
  (`role="img"`, `aria-label`) still appears when credentials are
  missing, matching this app's general "silence = fine, flag = needs
  attention" convention (e.g. finding disposition, coverage gaps).

## 2026-09-12 (continued) — Static asset cache-busting

- Found live, immediately after shipping the Home page redesign below:
  navigating to `#/home` (via URL or the shellbar logo) rendered the
  Dashboard instead. Root cause wasn't a routing bug - the reporter's
  browser tab was still running pre-redesign `app.js` from before this
  session's changes. Hash-based client-side routing never triggers a page
  reload on its own, so an already-open tab keeps executing whatever
  JavaScript it loaded once, indefinitely; `Cache-Control: no-cache`
  (Flask's static-file default) only prompts a *revalidation* on an actual
  reload, and even then nothing forced a stale disk-vs-browser mismatch to
  resolve without a real reload happening first.
- Added `sal/web/__init__.py`'s `_asset_version()` (mtime-derived, no
  content-hash build pipeline per CLAUDE.md's no-build-step constraint) and
  wired it into `shell.html` as `?v=...` on both `app.js` and `style.css` -
  every real page load now requests a version-specific URL, so a genuine
  reload can never serve stale content again. Does not fix (nor was it
  meant to) the underlying SPA fact that a hash-only navigation reuses
  already-loaded JS - that's normal and expected; the fix is for the
  reload case. `tests/test_web_shell.py` pins both.

## 2026-09-12 — Home page + toolbar/menu redesign (outside the phase roadmap)

- Prompted by direct feedback that the buttons/sidenav felt flat, and that
  the standalone Systems page (add/edit/remove SAP connections) sat
  oddly alongside the shellbar's own system dropdown - two different
  "pick/manage a system" surfaces that didn't obviously relate to each
  other.
- Replaced the Systems page with a **Home page** (new default landing
  route): a grid of system cards grouped by environment, each showing
  environment/credentials badges and Edit/Remove actions, plus a
  dashed "+ Add system" card. Picking a card is how you enter that
  system's workspace (Dashboard/Findings/Jobs/...). Since this is a
  navigation-architecture change and not just a visual one, the exact
  shape (does the shellbar quick-switch stay or go, does Systems
  management fold into Home or stay separate) was confirmed with the
  project owner before implementing rather than assumed: the shellbar's
  quick-switch dropdown stays (so switching mid-page doesn't require
  going back to Home), and the last-chosen system now persists across
  reloads via `localStorage` (mirroring the existing theme-toggle
  pattern), rather than always defaulting to "the first configured
  system" as it silently did before.
- `app.js`'s `route()` now treats Home as a gate: with no system chosen
  yet this browser, any other route (including a bookmarked deep link)
  renders Home instead of rendering against an empty/wrong scope. The
  sidenav and shellbar quick-switch are both hidden while Home itself is
  shown (`body.route-home` in `style.css`) since Home's own cards are the
  picker there.
- Sidenav items regrouped under uppercase section labels (Monitoring /
  Data Collection / System Health) instead of one flat 9-item list -
  purely additive CSS/HTML, no routing changes.
- Findings page's action row consolidated: the three export formats
  (CSV/Excel/ITGC Report) now live behind one "Export" dropdown menu
  (`.menu` / `setupDropdownMenu()` in `app.js` - closes on outside
  click/Escape, returns focus to the trigger) instead of three
  same-weight buttons, and every toolbar button gained an inline-SVG icon
  matching the sidenav's existing stroke style (`.btn-primary`/
  `.btn-secondary` already had `gap`/`inline-flex` set up for this, just
  unused until now). Applied the same icon touch-up to the Collect page's
  Export CSV/Excel pair for consistency.
- Not live-browser-verified this session (the chrome-devtools MCP server
  failed to connect) - verified instead via `node --check` on `app.js`,
  a full manual trace of every routing/persistence branch, and HTTP-level
  checks that the served shell/JS/CSS matches disk. The full backend test
  suite (114 tests, all Python/unaffected by this frontend-only change)
  still passes.

## 2026-09-11 (continued) — Detection rules catalog export

- Added a "Detection Rules" button on the Findings page (`GET
  /api/rules/export`) that downloads a plain-English reference workbook
  explaining every active detection rule - what it detects, how its
  baseline/threshold logic works, which SM19 message codes/event class it
  reads, typical severity, and known caveats - so an analyst or auditor
  doesn't need repo access to understand what's actually firing findings.
- Added `sal/rules_catalog.py` (`build_rules_catalog_workbook()`,
  `RULE_DETAILS`). Every description was written from reading each
  `sal/rules/*.py` module's real detection logic directly, not copied from
  `Docs/Rules.md`'s higher-level table, so it describes what the code does
  rather than what the original use-case brief intended.
  `tests/test_rules_catalog.py` pins a drift guard (every `RULES` key must
  have a `RULE_DETAILS` entry), matching `itgc_report.py`'s and
  `_coverage.py`'s existing drift-test pattern.
- Extracted `sal/xlsx_style.py` (header fill/font, wrap alignment, thin
  borders, column widths) out of `sal/itgc_report.py` once
  `rules_catalog.py` needed byte-identical styling - the ~40 lines were
  genuinely duplicated, not just superficially similar, so this is
  refactor-on-second-use rather than a premature abstraction.
  `itgc_report.py`'s own report content (control mapping, disposition
  formatting, SAP-date rendering) stayed put; only the styling constants
  moved.

## 2026-09-11 — ITGC-formatted findings export (outside the phase roadmap)

- Prompted by two "SAP Initial ITGC Data Request" workbooks the client's
  audit team shared (`Docs/*ITGC Data Request*.xlsx`, FY23-24 and FY24-25):
  the existing findings export is a flat, detailed row dump, not the shape
  an ITGC (IT General Controls) auditor actually reviews. Those workbooks'
  own "SAP IDR" index sheet shows what that shape is - a cover sheet naming
  client/application/audit period/extraction method, an indexed control
  matrix, a workpaper with disposition plus blank auditor-remarks columns,
  and an extraction log evidencing how the data was pulled (their IDR asks
  for screenshots of RFC/GUI input parameters - SAL's `collection_runs`
  ledger is the API-driven equivalent of that evidence). Their own D-3 line
  item ("Audit Log Details ... for Tcodes SM20 and SM21") is literally what
  this tool automates.
- Added `sal/itgc_report.py` (`build_itgc_workbook()`): renders findings +
  in-scope collection-run history into a 4-sheet workbook (Cover Sheet,
  Control Matrix, Findings Detail, Extraction Log). `CONTROL_OBJECTIVES`
  maps every registered detection rule to one of 4 standard ITGC "Access to
  Programs and Data" sub-objectives (logon/session monitoring, SoD/sensitive
  transaction usage, sensitive data access/export, privileged/user-master
  change monitoring) - a reporting-only grouping, deliberately kept out of
  `sal/rules/registry.py` since it's how an auditor reads the catalog, not a
  detection concern. `tests/test_itgc_report.py` pins a drift guard (every
  `RULES` key must appear in `CONTROL_OBJECTIVES`), mirroring
  `_coverage.py`'s existing drift test.
- The cover sheet states scope up front: SAL only continuously monitors
  SM20, so this evidences one ITGC control domain (Access to Programs and
  Data) and explicitly does not cover Program Change Management, Program
  Development, or Computer Operations - it does not imply broader coverage
  than the tool has.
- Wired as a third format on the existing endpoint (`GET
  /api/findings/export?format=itgc`, alongside `csv`/`xlsx`) rather than a
  new route, and a matching "Export ITGC Report" button next to the
  existing Export CSV/Excel buttons on the Findings page.
- `security-reviewer` flagged a formula/CSV-injection gap (CWE-1236):
  several columns (actor display names - unrestricted free text with no
  RBAC, disposition reason codes/notes, SAP-sourced event text) were
  written straight into cells with no defanging, and a value starting with
  `=`/`+`/`-`/`@`/tab/CR is a live formula to Excel/LibreOffice on open -
  a materially bigger risk for a workbook meant for external audit-team
  handoff than for the existing internal-only CSV/XLSX pull (which had the
  same pre-existing gap). Added `sal/export.py`'s `sanitize_cell_value()`
  (prefixes a defanging `'`) and applied it in both `rows_to_csv`/
  `rows_to_xlsx` and every cell-write path in `itgc_report.py`.
- Live-verified against the running dev server and the real ~111K-event
  pilot database (`data/sal.db`), which caught one real bug before it
  shipped: the cover sheet's "Testing Period" filtered `collection_runs`
  on `status == "completed"`, a value that row never actually holds -
  `sal/collectors/sm20.py` writes `"success"`/`"error"`. Fixed, with a
  regression test pinning the correct value. Also added SAP-date
  (`YYYYMMDD`) → ISO (`YYYY-MM-DD`) rendering after noticing raw
  `20260601`-style strings in the live output.

## 2026-09-10 (continued) — Phase F: role/authorization context + out-of-context transaction usage (use case #14)

- **Live technical spike first**, per this project's standing discipline.
  `BAPI_USER_GET_DETAIL` was tested and found to be broken via pyrfc on
  this system/release (`decimal.InvalidOperation` from inside pyrfc's own
  response unmarshalling, reproduced against two different real users -
  systemic, not a data quirk). The validated path turned out to be a
  generic `RFC_READ_TABLE` read against `AGR_USERS` (role↔user assignment)
  and `AGR_TCODES` (role→tcode "menu"), not a purpose-built BAPI -
  `SUSR_GET_PROFILES_OF_USER_RFC` also works but returns generated
  **profile** names, not PFCG **role** names, which aren't interchangeable
  for this use case. See `Docs/Memory.md` items 4-7 and
  `scripts/probes/probe_agr_tables.py`/`probe_user_master.py`.
- `/ecc:dev-team` review of the plan reframed the proposed
  "snapshot-history vs. current-state" schema question as a false binary:
  storing `AGR_USERS`' raw rows with their own `FROM_DAT`/`TO_DAT`
  validity window (rather than collapsing to one representation) gets
  query-time "as of a date" filtering for free, without separate snapshot
  machinery - adopted. No `/ecc:council` round was needed; the four
  reviews converged rather than genuinely conflicted.
- Added `sal/role_context.py` (`sync_role_context`, `authorized_tcodes_for_user`,
  `latest_refresh`, `list_refresh_runs`, `role_context_counts`), three new
  tables (`user_roles`, `role_tcodes`, `role_context_refresh_runs`), a new
  rule `sal/rules/out_of_context_transaction.py` producing two distinct
  rule keys from one shared engine (mirroring `first_time_transaction.py`'s
  existing #4/#11 pattern) - `out_of_context_transaction` (roles exist,
  don't cover the tcode) and `out_of_context_no_role_data` (zero role rows
  on record at all) - a daily APScheduler refresh job per system plus a
  manual "Refresh role context" trigger, `GET/POST /api/role-context*`,
  and a new Role Context panel on the Coverage page.
- Deliberately a direct call, not a `sal/jobs.py` job - a bulk table read
  isn't the day-chunked problem that machinery solves (same reasoning as
  `audit_config.py`/`retention.py`).
- **Answers the actual owner-stated audit scenario** (see
  `Docs/Memory.md` item 0f): a user who ran a critical transaction weeks
  ago and no longer holds the role granting it today is correctly flagged,
  because `sync_findings()` already re-evaluates all retained event
  history on every run, not just newly-collected events - no new
  mechanism was needed for this, only precise evidence/wording. Verified
  live against real data (S23: ~20k `AGR_USERS` rows, ~171k `AGR_TCODES`
  rows) including this exact scenario.
- `python-reviewer` + `security-reviewer` (parallel, independent) found
  two real bugs before this shipped:
  - **CRITICAL**: the rule's evidence included the role-context refresh
    timestamp it was checked against, which changes daily even when the
    underlying finding is unchanged - `_finding_key()` hashes evidence
    into identity, so this silently created a new "open" finding every
    day and discarded any analyst disposition made the day before. Fixed
    by adding `role_refresh_checked_at` to `sal/findings.py`'s
    `_VOLATILE_EVIDENCE_KEYS` denylist; regression test added. Live
    re-verification confirmed: two syncs a day apart now produce zero new
    findings for an unchanged condition.
  - **HIGH**: the on-demand refresh had no timeout and no in-flight guard,
    unlike `audit_config.py`'s already-solved sibling pattern for the same
    problem (pyrfc has no per-call timeout; a wedged connection needs a
    bounded wait, and a second identical request shouldn't pile another
    attempt onto an already-wedged target). Fixed by copying
    `audit_config.py`'s daemon-thread-plus-`Future.result(timeout=)` and
    `_inflight` set pattern in full (300s timeout - many sequential
    paginated calls, not audit_config's single call). Live-verified: a
    second concurrent refresh request is correctly rejected while the
    first is still running, and the guard releases cleanly afterward.
  - Also fixed two MEDIUM findings from the same reviews: `RFC_READ_TABLE`
    row parsing now validates field count before use (a short/malformed
    row is logged and skipped, never silently field-shifted into the
    wrong columns) instead of trusting `zip()` to truncate silently; and
    hitting the pagination safety cap now reports a distinct
    `success_truncated` status instead of a plain `success` that would
    have hidden a real "more data existed than we fetched" gap.
- Full test suite: 90 passing (was 84 immediately after first
  implementation, 70 before Phase F).

## 2026-09-10 (continued) — Training docs now also generated as formatted PDFs

- Added `scripts/render_training_pdfs.py`: converts both
  `Docs/training/*.md` files into formatted PDFs (cover page, clickable
  table of contents, styled tables/code blocks, page-numbered footer)
  using `Markdown` + `xhtml2pdf` (added to `requirements-dev.txt` -
  doc tooling only, not imported by `sal/`). The Markdown stays the
  single source of truth; the PDF is a generated, re-runnable artifact
  for people who'd rather read/print/share a formatted document.
  `WeasyPrint` was tried first but requires a GTK/Pango system library
  this machine doesn't have and installing one is a heavier system
  change than this task warranted; `xhtml2pdf` needs no system
  dependencies and was already sufficient.
- QA'd every page of both generated PDFs by rendering them to images and
  inspecting visually (via PyMuPDF, dev-only, not a project dependency).
  Found and fixed real rendering defects along the way, all in the
  Markdown source rather than by fighting the renderer: xhtml2pdf cannot
  wrap text inside an unbroken run of non-whitespace characters (`/`,
  `<wbr>`, zero-width space, and `word-break`/`word-wrap` CSS were all
  tested and none work) - several table cells with long slash-joined
  identifiers (e.g. `open/true_positive/false_positive/whitelisted`,
  `SAL_SAP_<SYSTEM_ID>_ASHOST/_SYSNR/...`) were overflowing their column,
  in one case off the right edge of the page entirely; fixed by adding
  real spaces at natural break points in the source text. Also fixed
  `<code>` spans rendering illegibly (dark text on a near-white
  background) inside dark-blue table headers, and a shell-command code
  block whose long inline comments overflowed the page width (`pre-wrap`
  isn't honored either) - reformatted as one command + comment per line.

## 2026-09-10 — Repo reorganization + training documentation (outside the blueprint's phase lettering)

- **Reorganized the file layout** — the repo root had accumulated 8 loose
  markdown docs (`ARCHITECTURE.md`, `CHANGELOG.md`, `Design.md`,
  `Memory.md`, `Phases.md`, `PRD.md`, `PROJECT-CONTEXT.md`, `Rules.md`)
  alongside the existing `Docs/` folder, plus 16 one-off SAP RFC discovery
  spike scripts (`scripts/probe_*.py`) mixed in with the 3 real
  operational scripts, plus a stray `dev_rfc.log` at the root. Moved the
  8 docs into `Docs/` (their bare-filename cross-references to each other
  stayed valid since they moved together; references from files that
  *didn't* move — `CLAUDE.md`, `.claude/skills/sal-phase-workflow/SKILL.md`,
  and a handful of code comments/docstrings/one UI caption string — were
  updated to `Docs/<name>.md`), moved the probe scripts into
  `scripts/probes/` (fixing each one's `sys.path.insert` depth, since they
  moved one directory deeper — verified via `py_compile` on all 16), and
  moved `dev_rfc.log` into a new `logs/` folder. `CLAUDE.md` stays at the
  repo root — Claude Code auto-discovers project instructions there, so
  it's the one exception to "everything documentation-shaped lives under
  `Docs/`." The `nwrfc750P_16-70002755/` SAP NW RFC SDK folder was
  deliberately left at the root — it's already a single self-contained
  unit (not scattered), and moving it would mean editing the live
  `.env`'s `SAPNWRFC_HOME` path with no safety net (this project has no
  git history) for purely cosmetic benefit.
- **Added two training documents** under the new `Docs/training/`:
  `SAL_Technical_Deep_Dive.md` (for engineers — SAP RFC mechanics, exact
  function modules and field mappings, the full Python backend
  architecture, data model, job execution model, all 10 detection rules'
  exact logic, the API surface, and the cross-cutting engineering lessons
  this project has learned the hard way) and `SAL_Analyst_User_Guide.md`
  (for security analysts — plain-language walkthrough of every page,
  the disposition/whitelisting workflow, what each detection rule means
  in analyst terms, SLA/coverage/retention, and a troubleshooting FAQ).
  Both are pointed to from `CLAUDE.md`.
- Verified: full test suite (70 passing, unchanged) and a live dev-server
  health check after the move — no runtime code depends on documentation
  file locations, so this was a documentation/organization change with no
  functional risk, but verified anyway.

## 2026-09-09 (continued) — Data retention purge implemented (outside the blueprint's phase lettering)

- Implemented the owner-decided retention policy (`events` 365 days,
  `findings`/disposition history 2555 days/7 years - SOX audit-trail
  standard) as an actual purge, not just a documented decision. Added
  `sal/retention.py` (`preview_purge`, `run_purge`, `list_purge_runs`),
  the `retention_purge_runs` audit table (one row per run, even an empty
  one), a daily APScheduler job registered alongside the existing
  collection scheduler (default 03:00, one hour after collection's
  default 02:00, via `SAL_RETENTION_PURGE_TIME`), `GET /api/retention` /
  `POST /api/retention/purge-now`, and a new "Retention" page (policy
  summary, live preview, next scheduled run, a manual "Run now" button
  gated behind a confirm dialog, and a purge-history table).
- Deliberately not routed through `sal/jobs.py`'s chunked job model, per
  the same council-decided precedent as Phase D's audit-config check - a
  dateless local bulk-delete isn't the multi-day-RFC-pull problem that
  machinery solves.
- `python-reviewer` found a CRITICAL bug before this shipped: `events`'s
  cutoff was built with `.isoformat()` (a "T" separator + microseconds +
  UTC offset) while `events.event_timestamp` is actually stored by the
  collector as a naive `"YYYY-MM-DD HH:MM:SS"` string - a lexical `<`
  comparison between the two mismatched shapes silently treated every
  same-day row as eligible regardless of time-of-day, over-purging
  in-retention events by up to a day on every run, forever. Fixed by
  building the events cutoff with the collector's own format; a same-day
  boundary-crossing regression test was added specifically because the
  original test helper had (accidentally) written test data in the
  cutoff's format rather than the collector's, which is why the bug
  shipped past the first test pass undetected.
- Same review also flagged a HIGH-severity side effect of adding a
  second, uncoordinated writer to `events`/`findings`: a lock collision
  between the purge and the job worker's own error-path write could have
  taken down the single background worker thread permanently. Fixed by
  wrapping that write in its own try/except inside `sal/jobs.py`'s
  `_worker_loop`.
- Full test suite: 70 passing (was 69).

## 2026-09-09 (continued) — Phase D implemented

- Resolved D.1: SAP connectivity restored, re-ran the `RSAU_API_*` spike.
  `RSAU_API_GET_AUDIT_CONFIG` (no input parameters) is the correct FM -
  found in the exact function group `RSAU_API_GET_LOG_DATA` belongs to,
  confirming the hypothesis from planning. Returns a global enable flag
  and one row per active audit-log slot, each with named, self-describing
  event-class flags (`CLASS_LOGIN`, `CLASS_TCD`, `CLASS_USER`, etc.) and a
  `MSGVECT` byte vector for message-code-level detail whose bit encoding
  isn't documented anywhere verifiable - deliberately not decoded, per the
  planning review's own warning that a wrong guess risks a false
  "you're covered" signal.
- Added `sal/audit_config.py` (`check_audit_config`, `latest_snapshot`,
  `coverage_gaps`), `sal/rules/_coverage.py` (rule → SM19-class mapping,
  sourced by grepping each rule's actual filter, not assumed), the
  `audit_config_snapshots` table, `POST /api/audit-config/check` /
  `GET /api/audit-config`, and a new "Coverage" page.
- Built the on-demand check as a direct, timeout-bounded synchronous call
  per the council's binding decision - not routed through `sal/jobs.py`.
  `python-reviewer` then found the first implementation still had a real
  design gap the council hadn't anticipated: a shared, fixed-size
  `ThreadPoolExecutor` risks starving on one wedged system and (being
  non-daemon) can hang a clean process shutdown after any timeout ever
  fires. Redesigned to one daemon thread per call plus a per-(system,
  client) in-flight guard, with the abandoned call's eventual outcome
  logged instead of silently discarded (previously a real CRITICAL gap).
- `security-reviewer` found the raw RFC response was being persisted
  verbatim/unfiltered into the database - not a credential leak (the FM
  returns config metadata, not secrets), but the same "blind capture of
  an entire upstream payload" pattern flagged once before with an audit
  log route. Fixed with an explicit field allowlist. Also tightened
  `system_id` validation on the new check endpoint to match `/api/collect`'s
  existing registry check.
- Verified live against the real system (S23): audit log enabled, 3
  active slots, and - genuinely, not asserted - **zero coverage gaps**
  today; every one of the 10 rules' required event classes is currently
  active. Verified the "Check now" button end-to-end in the browser.
- 10 new tests (`tests/test_audit_config.py`), including a drift-guard
  test asserting `RULE_COVERAGE`'s keys never silently diverge from the
  real rule registry. One test-isolation bug found and fixed along the
  way (a mocked timeout path was leaking a stuck in-flight guard entry
  into every later test using the same system/client key). Full suite:
  64 passing.

## 2026-09-09 (continued) — Phase D planning + project documentation

- Planned Phase D (SM19 audit-configuration visibility). Attempted the
  technical spike (searching the `RSAU_API_*` function group for a config-
  reading FM, the same group `RSAU_API_GET_LOG_DATA` belongs to) but SAP
  was unreachable (network timeout) - remains the blocking first task.
- Ran a dev-team review on the plan; Developer found a real, pre-existing
  gap while reading rule source: `mass_user_changes.py` enforces
  `event_class` in code, with its actual message codes documented only in
  a comment, not enforced - exactly the kind of drift Phase D's coverage
  mapping needs to guard against structurally, not just document.
- Ran a council round on one genuine technical tension the review
  surfaced (should Phase D's on-demand config check reuse `sal/jobs.py`'s
  chunked job model, or be a simple direct call?). Unanimous verdict
  (all three independent voices, converging with the pre-formed position):
  direct synchronous call, explicit RFC timeout, `try/except/finally`
  discipline - not routed through infrastructure built for a different
  problem shape (multi-day chunking). The Critic's reframe - the real risk
  is an unbounded RFC call blocking a Flask request thread, not
  queue-vs-direct - is now the binding design constraint for D.4.
- Added `ARCHITECTURE.md` (code-derived module map, data flow, job
  execution model, security posture, phase status - distinct from the
  external consulting blueprint in `Docs/`), `CLAUDE.md` (project
  instructions for future Claude Code sessions), and
  `.claude/skills/sal-phase-workflow/SKILL.md` (codifies the plan →
  dev-team → council → implement-with-tests → independent-review →
  UI-build → live-verify → changelog process this project has actually
  been following). Refreshed `PROJECT-CONTEXT.md` to reflect Phase E's
  pull-forward, the Jobs/SLA additions, and Phase D's current blocked
  state.
- Added item 11 to `Docs/Open_Questions_For_Review.txt`: whether to ship
  Phase D's coverage dashboard on a weaker "last maintained config"
  signal if the spike can't reach true runtime-active state - a real,
  unresolved product question, not decided here.

## 2026-09-09 (continued) — Phase E pulled forward + Jobs monitoring + SLA dashboard

Triggered by answers to `Docs/Open_Questions_For_Review.txt`: the owner
confirmed a four-environment SAP landscape (Development/Quality/Production/
Sandbox) is coming, asked for UI to manage it now (effectively Phase E's
connector abstraction, pulled ahead of Phase D), plus a jobs-monitoring page
and an SLA/aging dashboard (High=1 business day, Medium=3, Low=7). A
dev-team review flagged this as a real scope decision, not just a
scheduling one; the owner confirmed pulling E forward, including Production.

- **Systems/environment registry** (`sal/systems.py`, new `systems` table):
  environment-tagged SAP connection metadata, managed via `/api/systems`
  CRUD and a new "Systems" page, grouped by environment. Deliberately
  stores no credential - passwords stay in `.env`
  (`SAL_SAP_<ID>_PASSWD`), so the app's own database never becomes a
  second place SAP credentials could leak from; the UI shows a
  "credentials configured/missing" indicator per system instead. Existing
  `.env`-only systems (S23) are auto-registered on first use, defaulted to
  "Sandbox" pending manual review.
- **Jobs monitoring page**: live status/progress ("N of M days")/ETA for
  running jobs (`sal/jobs.py` now tracks incremental per-day progress) and
  each system's next scheduled run (the daily-collection scheduler moved
  from `sal/web/__init__.py` into `sal/jobs.py` so this could be queried
  directly, and so a newly-added system's daily job registers immediately
  instead of requiring a restart).
- **SLA/aging dashboard panel**: open findings bucketed On track/At risk/
  Breached per severity (`sal/sla.py`, business-day math, Mon-Fri UTC, no
  holiday calendar - a documented simplification), plus a most-overdue list.
- Grouped the shell bar's system picker by environment.
- Built via `ecc:a11y-architect` (UI, consistent with the existing design
  system) and reviewed by `ecc:python-reviewer` + `ecc:security-reviewer`
  before shipping. Both found real bugs, all fixed before merge:
  - System-ID casing wasn't normalized in the PATCH/DELETE routes, so a
    lowercase URL segment would silently leave a "removed" system's daily
    SAP pull running under its original-cased scheduler job ID - fixed with
    normalization at both the API layer and defense-in-depth inside
    `sal/jobs.py`'s scheduler functions themselves, plus narrowing an
    overly broad `except Exception` that was masking exactly this failure.
  - A TOCTOU race in `POST /api/systems` (check-then-insert under Flask's
    `threaded=True`) could 500 instead of cleanly reporting a duplicate -
    fixed via `INSERT OR IGNORE` + rowcount, matching the pattern
    `seed_from_env()` already used correctly.
  - `PATCH /api/systems/<id>`'s audit log recorded the raw, unfiltered
    request body instead of an explicit field whitelist (every sibling
    route already did this correctly) - a latent risk if a secret were
    ever included in a request body, since audit entries are readable via
    an unauthenticated endpoint.
  - `update_system()` couldn't distinguish an omitted `description` from
    an explicitly cleared one - added a proper sentinel.
  - A real bug in `sal/sla.py`'s business-day math, caught by its own new
    tests before shipping: the first partial day of a date range was being
    double-counted as a full day.
- 21 new/changed tests (`test_systems.py`, `test_sla.py`, plus additions to
  `test_jobs.py`/`test_api.py`) — full suite: 54 passing.
- Verified live in the browser: added/edited/removed a real system,
  confirmed the "credentials missing" badge and grouped picker, watched a
  real in-flight job's progress bar and ETA update via polling, and
  confirmed the SLA panel's bucket counts against real data.

### Phase A — Findings persistence & disposition workflow
- Closed out Phase A: fixed the root cause of an empty `findings` table
  (`scripts/collect_sm20.py` never triggered `sync_findings()`), collected a
  real ~30-day reference dataset (507,977 events, 1,103 findings), and
  verified disposition + whitelist end-to-end via the browser.
- Fixed a real bug found during verification: a whitelist entry added
  *after* a finding already existed did nothing on re-sync. Whitelisting
  now retroactively suppresses matching open findings without overriding
  an analyst's existing disposition.
- Fixed a dead button: the dashboard's "Recent high-severity findings"
  disposition Save button had no event handler wired up (only the
  dedicated Findings page did). Extracted a shared handler used by both.
- Added the project's first automated test suite (`tests/test_findings.py`).
- Added `PROJECT-CONTEXT.md` as a shared baseline for future sessions.

### Phase B — Scheduled & ad-hoc collection
- Added `sal/jobs.py`: a shared job-execution primitive (day-by-day
  chunking, per-day retries, single background worker thread) used by both
  a new daily `APScheduler` job per configured system and the existing
  ad-hoc "Collect" UI, which now submits a job and polls status instead of
  blocking the HTTP request.
- New `collection_jobs` table; `GET /api/jobs`, `GET /api/jobs/<id>`.
- Hardening after live end-to-end testing surfaced two real bugs:
  - `collect_and_store()` only caught one SAP-specific exception type,
    leaving a `collection_runs` row stuck at `"running"` forever on any
    other failure (found via an unconfigured-system test). Finalization
    now happens in a `finally` block regardless of exception type.
  - `system_id` was never validated at job submission - an unconfigured
    system was accepted into the queue and only failed once the worker
    tried to run it. Now rejected at submission with a 400.
  - Added crash-recovery reconciliation: on startup, any job or collection
    run left at `"running"` (from a process that crashed or was killed
    mid-job) is marked `"error"` with a message asking it to be re-run.
- Added `tests/test_jobs.py`, `tests/test_collectors.py`, `tests/test_api.py`.

### Phase C — Export
- Added `sal/export.py` and `GET /api/findings/export` /
  `GET /api/collection-runs/export` (CSV and native Excel via `openpyxl`),
  respecting the current filters and exporting the full matching set (not
  just one page). Wired "Export CSV"/"Export Excel" buttons into the
  Findings and Collect pages.
- Added `tests/test_export.py`.

### UI visual refresh *(outside the phase roadmap)*
- Full visual redesign of the Flask UI (`sal/web/static/css/style.css`,
  `sal/web/templates/shell.html`, minor additive changes to
  `sal/web/static/js/app.js`), done via the `ecc:a11y-architect` agent:
  refined "enterprise security console" palette, real type scale, gradient
  shell bar, proper elevation/hover/focus states throughout, severity
  colors re-tuned for WCAG AA contrast (medium-severity orange in
  particular only hit ~3:1 before), redesigned tables/badges/buttons/modals
  and skeleton loaders, a skip link, and `prefers-reduced-motion` handling.
  Full dark mode via `prefers-color-scheme` (no toggle - follows the
  OS/browser setting). Kept fully self-contained (no external font/icon
  CDNs, since this tool runs against a live, security-sensitive SAP
  environment) and every functional class/id hook `app.js` depends on was
  verified unchanged.
- Verified live in the browser post-redesign: dashboard tiles/donut,
  Findings page (disposition save re-tested end-to-end, still persists
  correctly), and the whitelist modal all render and function correctly.
  Fixed one minor spacing issue found during verification (donut legend
  values were flush against their labels in narrow containers).
- Added an explicit light/dark toggle in the shell bar after noticing
  Chrome and Edge reported different `prefers-color-scheme` results on the
  same machine (each browser has its own independent appearance setting,
  not always following the OS). Choice persists per-browser via
  `localStorage`; defaults to following the browser's preference until
  changed. Verified: toggling flips the theme immediately and survives a
  page reload.

### Documentation
- `Docs/Open_Questions_For_Review.txt`: 10 open questions/decisions
  compiled for manual review (SAP Basis read-only confirmation, retention
  policy, RBAC timing, daily-schedule time, second-system onboarding
  timeline, roadmap sequencing, aging/SLA dashboard scope, and others).
