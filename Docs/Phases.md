# SAL Phase Tracker

Authoritative status for every phase. Letters A–H refer to the forward
architecture in `Docs/SAL_Architecture_Blueprint_v2.docx`; entries without
a letter were built outside that roadmap, at the owner's explicit request.
For *what was actually built and what bugs were found along the way*, see
`CHANGELOG.md` (chronological); this file is the current-status summary.

| Phase | What | Status |
|---|---|---|
| A | Findings persistence & disposition workflow | **Done** |
| B | Scheduled + ad-hoc collection | **Done** |
| C | Export (CSV/Excel) | **Done** |
| — | UI visual redesign + light/dark theme toggle | **Done** (outside roadmap) |
| E | Connector abstraction (multi-environment systems registry) | **Done** (pulled forward ahead of D) |
| — | Jobs monitoring page + SLA/aging dashboard | **Done** (outside roadmap, requested alongside E) |
| D | SM19 audit-configuration visibility (Coverage page) | **Done** |
| F | Role/authorization context + out-of-context transaction usage (use case #14) | **Done** |
| F | Peer-group deviation from role baseline (use case #6) | Not started — deliberate fast-follow, not bundled with #14 |
| F | GRC EAM / Firefighter session review (use case #10) | Not started — explicitly deferred pending separate approval |
| G | Postgres migration | Not started — not yet justified by volume |
| H | LLM layer (natural-language query, summaries) | Not started — deliberately last |

## Sequencing note: why E shipped before D

The blueprint's own stated order was D then E. The owner's answers to two
separate review questions were in direct tension: one asked for a
multi-environment systems UI *now* (which is, in substance, Phase E's
connector abstraction), while another said to keep blueprint order as-is.
A dev-team review refused to silently pick one interpretation and put it
back to the owner explicitly; the owner chose to pull E forward. This is
recorded here because it's a real precedent: two answers to two questions
can conflict, and the right move is to surface that, not average it away.

## Per-phase notes

**A — Findings persistence & disposition.** The code existed before it was
ever exercised against real data — the actual blocking issue was that the
CLI collection path never called the sync step. Closing this out also
surfaced a genuine whitelist bug (didn't retroactively suppress an
already-existing finding) and a dead UI button (dashboard disposition
control had no JS listener attached).

**B — Scheduled + ad-hoc collection.** Built a shared, chunked job runner
(`sal/jobs.py`) used by both the daily scheduler and ad-hoc submissions.
Hardening after live testing fixed a stuck-row bug (narrow exception
handling) and added missing `system_id` validation at submission.

**C — Export.** Straightforward; no new data model, per the blueprint's own
framing of this phase.

**E — Connector abstraction.** A `systems` table replacing `.env`-only
discovery, environment-tagged (Development/Quality/Production/Sandbox).
Deliberately stores no credential — passwords stay in `.env`. Existing
`.env`-only systems auto-register on first use.

**D — SM19 audit-configuration visibility.** The technical spike (which
RFC reads the *active* config) was genuinely unknown at planning time and
blocked once on a live-connectivity issue. Resolved: `RSAU_API_GET_AUDIT_CONFIG`,
found by searching the same function group as the already-validated SM20
FM. A dev-team + council review decided the on-demand check must be a
direct, timeout-bounded call, not routed through `sal/jobs.py`'s chunked
model — and that decision surfaced two further real bugs during
implementation review (a silently-discarded background result, and a
shared thread pool that could starve or hang shutdown), both fixed before
shipping. First live run against the real system: zero coverage gaps.

**F — Role/authorization context (use case #14).** Grounded in a live
technical spike, per this project's usual discipline: `BAPI_USER_GET_DETAIL`
was tested and found to be broken via pyrfc on this system/release
(a systemic `decimal.InvalidOperation`, not a data quirk — reproduced
against two different users); the validated path turned out to be a
generic `RFC_READ_TABLE` read against `AGR_USERS`/`AGR_TCODES` (the actual
PFCG role-assignment and role-menu tables), not a purpose-built BAPI. A
dev-team review reframed the planned "snapshot-history vs. current-state"
schema question as a false binary — storing `AGR_USERS`' raw rows with
their own validity dates, rather than collapsing to one representation,
gets query-time "as of a date" filtering without separate snapshot
machinery (though this still cannot reconstruct authorization *after* a
role has been fully revoked, since SAP deletes that row outright rather
than expiring it — a real, documented limitation, not solved here).
Independent review before shipping found a CRITICAL bug (a volatile
evidence field was destabilizing finding identity, silently discarding
analyst dispositions and re-flooding the findings table daily) and a HIGH
gap (no timeout/in-flight guard on the on-demand refresh, unlike the
established `audit_config.py` precedent it should have copied) — both
fixed, with regression tests, before this closed out. Verified live
against real data (S23: ~20k role assignments, ~171k role-tcode
mappings) including the specific audit scenario this phase was built to
answer: a user who ran a critical transaction weeks ago and no longer
holds the role granting it today is correctly flagged, because
`sync_findings()` re-evaluates all retained history on every run, not
just newly-collected events.

**F (remaining), G, H.** Peer-group deviation (#6) and GRC EAM (#10) not
started — see the phase table above for why each is sequenced separately
from #14. G/H unchanged from before.
