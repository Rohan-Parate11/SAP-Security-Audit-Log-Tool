# SAL Project Memory

Durable decisions and lessons, with the reasoning behind them — distinct
from `CHANGELOG.md` (chronological record of *what* changed). This file
is *why*, kept so a lesson already learned doesn't get silently relearned
or re-litigated. Update it when a decision or a hard-won fact would
otherwise only live in a chat transcript.

## Product/business decisions (owner-confirmed, 2026-09-09)

0a. **Data retention**: `events` (normalized SM20 rows) retained 1 year -
    matches what auditors actually request. `findings`/disposition
    history retained 7 years (SOX audit-trail standard) - kept longer
    than raw events since disposition history has ongoing audit value
    after the underlying events age out. Organization is SOX-only, no
    other framework in scope. **Implemented 2026-09-09** as an actual
    daily purge job (`sal/retention.py`, a "Retention" page) - see
    `CHANGELOG.md`'s same-day entry and lesson [[13]] below for a real
    bug this caught before shipping.
0b. **The future NL-query/LLM layer (Phase H) only needs normalized data.**
    Confirmed with a concrete example ("list users who ran FB01N in the
    last 10 days") - this is a direct query against the existing `events`
    table's columns. No raw/unparsed SAP payload is needed or stored.
0c. **Scheduling stays app-side**, not an SAP-side ABAP job. Confirmed
    after laying out the tradeoff (an SAP-side job would need to push into
    SAL, inverting the read-only-observer trust model, for no real gain).
0d. **SAL_RFC keeps SAP_ALL until the tool (including Phase F) is
    feature-complete, then gets scoped via SU53 trace analysis.** This is
    a deliberate, owner-approved methodology - not an oversight. Do not
    build the scoped role earlier than that, and do not flag SAP_ALL as a
    forgotten to-do in the meantime.
0e. **Phase F proceeds with SU01/PFCG/AGR_USERS ingestion now; GRC EAM
    (use case #10, Firefighter) is explicitly deferred**, pending separate
    approval to ingest that data. **Implemented 2026-09-09** —
    `sal/role_context.py` + use case #14 (out-of-context transaction
    usage). Use case #6 (peer-group deviation) is a deliberate fast-follow,
    not bundled with #14 — see `Phases.md`.
0f. **The specific audit scenario Phase F must answer, in the owner's own
    words**: an auditor asks "who has used transaction X in the past
    month," and a user who ran it weeks ago but no longer holds the role
    granting it today must still be surfaced, with the fact that they no
    longer have that access logged explicitly - not silently omitted just
    because they don't currently appear in the "who has access" list.
    This is answered by `sync_findings()`'s existing re-scan-all-history
    behavior interacting with `sal/role_context.py`'s current-state role
    data - no new mechanism was needed, only evidence/wording precise
    enough to state it as "not currently assigned" (see rule 14 below).

## Validated facts about the live SAP system (S23)

1. **`RSAU_READ_LOG` does not work over RFC.** It reliably returns zero
   rows/zero file-stats even for windows independently confirmed to
   contain data. `RSAU_API_GET_LOG_DATA` is the validated, working
   alternative for SM20 event extraction. Do not reintroduce
   `RSAU_READ_LOG` without re-validating against a live system.
2. **`RSAU_API_GET_AUDIT_CONFIG`** (no input parameters) reads the active
   SM19 configuration. Found by searching the same function group
   (`RSAU_API_*`) that fact #1's working FM belongs to — when one FM in a
   group is validated, searching that group first is a reasonable, fast
   way to find a sibling FM, before guessing at names from documentation.
3. **`RSAU_API_GET_AUDIT_CONFIG`'s `MSGVECT` field** (a byte vector,
   presumably a per-message-code bitmask) has no verifiable bit encoding.
   Do not attempt to decode it without independent SAP documentation — a
   wrong decode risks a false "you're covered" detection-coverage signal,
   which is worse than not having the data at all. Event-class-level
   fields (`CLASS_LOGIN`, `CLASS_TCD`, etc.) are named booleans and safe.
4. **`BAPI_USER_GET_DETAIL` is broken via pyrfc on this system/release** —
   it raises `decimal.InvalidOperation` from inside pyrfc's own response
   unmarshalling (not a SAP-side error), reproduced against two different
   real users (DDIC, BASIS001), so it's systemic, not a user-data quirk.
   Do not use it; do not re-attempt without re-validating first (same
   discipline as fact #1's `RSAU_READ_LOG`). `BAPI_USER_GETLIST` (a user
   roster: `USERNAME`/`FIRSTNAME`/`LASTNAME`/`FULLNAME`) works cleanly and
   is the validated alternative for basic SU01 user-list data.
5. **The validated path to Phase F's role/authorization data (use cases
   #6 peer-group deviation, #14 out-of-context tcode usage) is
   `RFC_READ_TABLE` against `AGR_USERS` (role↔user assignment: `UNAME`,
   `AGR_NAME`, `FROM_DAT`, `TO_DAT`) and `AGR_TCODES` (role→tcode
   authorization: `AGR_NAME`, `TCODE`), not a BAPI.** Both read cleanly
   against S23 in one bulk call each (not one call per user).
   `SUSR_GET_PROFILES_OF_USER_RFC` (real import param is `USER_NAME`, not
   `USERNAME` — found via `RFC_GET_FUNCTION_INTERFACE` rather than
   guessed) also works, but returns generated/assigned **profile** names
   (e.g. `SAP_ALL`), not PFCG **role** names — the two are not
   interchangeable, and profile names alone don't support role-based
   peer-grouping or role-menu tcode cross-referencing. See
   `scripts/probes/probe_agr_tables.py` and
   `scripts/probes/probe_user_master.py`.
6. **Not every value in `events.user_id` corresponds to a real, currently
   maintained SU01 user record.** `SUSR_GET_PROFILES_OF_USER_RFC` raised
   `USER_NOT_EXISTS` for `BASIS001`, a value that appears in collected
   SM20 events, while working fine for `DDIC`/`SAL_RFC`. Any Phase F
   ingestion that joins `events.user_id` against fresh SU01/role data
   must tolerate a user_id with no matching master-data row — treat it as
   "no role context available," not an error.
7. **`RFC_READ_TABLE` is a generic table read, not a purpose-built BAPI —
   it needs `S_TABU_DIS`/`S_TABU_NAM` authority.** Currently moot (SAL_RFC
   has `SAP_ALL`, item 0d), but when the SU53-based scoped role gets built
   after the tool is feature-complete, explicitly confirm these two
   authorization objects are included — don't assume a scoped role will
   "just work" for a generic table read without checking.

## Design decisions and why

4. **Don't force a dateless/single-RFC-call operation through `sal/jobs.py`'s
   chunked job model just for "consistency."** Decided by a council review
   (Phase D planning): that machinery solves day-range chunking and
   resumability, problems a single config-read doesn't have. "Consistency"
   should mean shared conventions and module boundaries, not literally
   reusing a mechanism built for a different problem shape.
5. **Credentials never enter the application's own database — REVERSED
   2026-09-16, a deliberate, informed decision, not an oversight.** This
   held from Phase A through most of the project's life: SAP passwords
   lived only in `.env`, and the `systems` registry table had no password
   column *structurally*. The project owner explicitly asked for a
   central credential store ("a similar page for password manager on the
   home screen... a central repository that will store passwords for all
   the systems") answering the open question raised in UAT
   (`Docs/Open_Questions_For_Review.txt`, now resolved and removed from
   that file). Before building it, the owner was told the concrete
   tradeoff — this app has no RBAC, so centralizing credentials means
   anyone who can reach the app can reach every system's live password —
   and explicitly chose to proceed, further specifying that a stored
   password stays **viewable** again through the UI (not write-only), with
   `.env` kept working unchanged for any system that hasn't had a password
   saved centrally yet (coexistence, not a forced migration). Implemented
   as `sal/credentials.py`: a new `system_credentials` table, Fernet
   (symmetric, authenticated) encryption at rest, with the encryption key
   itself (`SAL_CREDENTIAL_ENCRYPTION_KEY`) living in `.env` — outside the
   database — the same principle that kept credentials out of `sal.db` in
   the first place, just one layer down. Every reveal of an actual stored
   password is audit-logged (`credential_view`) as the one mitigation
   available given the "viewable" choice. `sal.config.sap_system_config()`
   checks the central store first, falling back to the original all-`.env`
   logic unchanged for any system not yet migrated.
6. **Never persist an unfiltered upstream payload.** Found twice: once as
   a near-miss (an audit-log route logging a raw, unfiltered request body
   instead of an explicit field whitelist), once as a real fix (Phase D's
   `audit_config.py` originally stored the entire RFC response verbatim;
   changed to an explicit allowlist). The pattern to avoid is "just
   `json.dumps()` the whole thing" — always name the fields you intend to
   keep.
7. **Business-day/date-range math must handle partial first/last periods
   by actual elapsed-time overlap, not by counting whole calendar units.**
   The first implementation of SLA business-day math double-counted a
   partial first day as a full day while also fractioning the last day -
   caught by its own tests before shipping, but only because tests were
   written with concrete expected values, not just "does it run."

## Operational lessons

8. **Every function that makes a live RFC call needs `try/except/finally`
   discipline around whatever state it finalizes.** A `collection_runs`
   row got stuck at `"running"` forever once, from an exception handler
   narrower than the actual failure that occurred. This has recurred in a
   related form since: a `ThreadPoolExecutor`-based timeout initially left
   an abandoned background call's eventual outcome silently discarded
   (no log, no state update) — same root lesson, different shape.
9. **A shared, fixed-size thread pool is dangerous for potentially-hanging
   native calls.** `concurrent.futures.ThreadPoolExecutor`'s worker threads
   are non-daemon and get joined by an `atexit` hook — one genuinely wedged
   call can hang a clean process shutdown, and a fixed pool can be starved
   by repeat checks against the same stuck target. Fix: one daemon thread
   per call, plus an explicit in-flight guard keyed by the actual target
   (not the pool itself) to cap duplicate concurrent attempts.
10. **`system_id` (and similar keys) must be normalized consistently at
    every point that keys off it** - scheduler job IDs, audit log entries,
    database lookups. A case mismatch between a URL path segment and an
    internally-normalized value once caused a "removed" system's daily
    SAP job to keep running silently, undetected because the failure was
    caught by an overly broad `except Exception`.
11. **Owner answers to two separate questions can genuinely conflict.**
    When a dev-team review finds this, the right move is to name the
    conflict explicitly and ask, not average the two answers into a
    compromise neither party actually chose. (See `Phases.md`'s
    sequencing note on why Phase E shipped before D.)
12. **The plan → dev-team review → council (only for genuine tensions) →
    implement-with-tests → independent review → live-verify → changelog
    process reliably finds real bugs before shipping.** Every independent
    review pass on this project so far has found at least one real issue.
    Treat that as the process working as intended, not as a sign
    something went wrong upstream — see
    `.claude/skills/sal-phase-workflow/SKILL.md` for the process itself.
13. **Two ISO-shaped-looking TEXT timestamp columns can still be
    incomparable with a plain SQL `<`.** `events.event_timestamp` is a
    naive `"YYYY-MM-DD HH:MM:SS"` string (`sal/collectors/sm20.py`'s
    `_event_timestamp()`), while `findings.first_seen_at` is
    `datetime.now(timezone.utc).isoformat()` (a `"T"` separator +
    microseconds + UTC offset) — two different shapes that both happen to
    look like "a timestamp." A lexical string comparison only agrees with
    chronological order when both sides share the exact same shape; the
    retention purge's first cutoff (built via `.isoformat()` for both
    columns) silently treated every event on the cutoff's own calendar
    date as eligible regardless of time-of-day, over-purging in-retention
    events by up to a day on every run — caught by `python-reviewer`
    before shipping, not by the test suite, because the test helper had
    (accidentally) written test data in the cutoff's shape rather than
    the real collector's. **Before comparing two TEXT timestamp columns
    with `<`/`>` in this codebase, check how each one is actually
    written, not just that both "look like" ISO 8601.**
14. **A finding's evidence must never include a value that changes on its
    own over time for an otherwise-unchanged finding.** Phase F's
    out-of-context-transaction rule included the role-context refresh
    timestamp it was checked against in its evidence dict - informational
    and reasonable to want, but `_finding_key()` hashes evidence into
    identity, and that timestamp changes every single day the (correctly
    working) daily refresh job runs. The result: the same substantive
    finding got a new `finding_key` daily, re-appearing as a brand-new
    "open" row and silently discarding whatever disposition an analyst
    had already made - a CRITICAL bug caught by `python-reviewer` before
    shipping, not by the test suite (existing tests didn't simulate two
    syncs a day apart with a real evidence-timestamp change). Fixed by
    adding the field to `sal/findings.py`'s `_VOLATILE_EVIDENCE_KEYS`
    denylist. **Before adding any new field to a rule's evidence dict,
    ask whether it could independently change while the finding's actual
    substance stays the same — if yes, it belongs in the volatile
    denylist, not just "seemed useful context."**
15. **A new on-demand RFC-triggering feature must copy an already-solved
    sibling pattern in full, not just its shape.** Phase F's role-context
    refresh (`sal/role_context.py`) is architecturally the same kind of
    thing as `audit_config.py`'s on-demand SM19 check - a direct call
    triggered from an API route - but its first version only copied the
    "direct call, not a job" decision and missed the *reason* audit_config.py
    also has a timeout-bounded daemon thread and an in-flight guard
    (pyrfc has no call timeout; a wedged connection can't otherwise be
    bounded; a second identical request shouldn't pile another attempt
    onto an already-wedged target). `security-reviewer` caught this as a
    HIGH finding before shipping. **When a new feature is "the same shape"
    as an existing one, re-read that existing module's own docstring for
    *why* it's built the way it is, not just copy its top-level structure.**
16. **A recurring capability that looks like "the same schedule feature,
    just filtered" must not reuse the baseline's own storage/mode.**
    Requested directly (2026-09-16, resolving the open "recurring filtered
    collection" question): a saved, filtered, recurring pull, separate
    from and additional to `sal/schedule.py`'s single comprehensive
    baseline schedule per system. Built as its own table
    (`filtered_schedules`, keyed by a surrogate id, since a system can
    have many) and its own job `mode` (`"filtered_scheduled"`, never
    `"scheduled"`) - reusing `mode="scheduled"` would have let a filtered
    job's `last_completed_date` be mistaken by
    `last_scheduled_checkpoint()` for baseline progress, silently causing
    the real unfiltered detection-feed collection to skip days it never
    actually pulled. Deliberately no catch-up/resume (unlike the
    baseline's day-by-day checkpoint) - each firing just pulls a fixed
    2-calendar-day rolling window, relying on `events`' natural-key dedup
    to make overlap harmless; a missed firing simply isn't backfilled,
    accepted because this is a supplementary/investigative feed, not the
    primary detection one.
