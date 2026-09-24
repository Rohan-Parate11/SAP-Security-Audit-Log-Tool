# SAL — Product Requirements Document

For system design see `ARCHITECTURE.md`. For phase-by-phase delivery status
see `Phases.md`. For the detection rule catalog see `Rules.md`. For open
decisions still needed from the product owner see
`Docs/Open_Questions_For_Review.txt`.

## Problem

SAP Security Audit Log (SM20) review is manual, reactive, and today
produces no measurable signal on whether it's actually working — no
persisted findings, no disposition history, no visibility into whether
the underlying audit log is even configured to capture what detection
logic assumes exists. `Docs/SAL_Architecture_Blueprint_v2.docx` (the
source consulting document for this rebuild) frames this precisely: the
original blueprint's "60-80% effort reduction" claim was explicitly a
forecast, unverifiable until a disposition workflow exists to measure
analyst time against.

## Goals

- Deterministic, evidence-first detection before any AI-assisted layer
  (both the original and reconciled blueprints agree on this ordering).
- Detection-only — never write back to SAP or take remediating action.
- Make "effort reduction" and "detection coverage" measurable claims, not
  assertions.
- Validate every technical assumption (RFC/function-module behavior)
  against a live system before it becomes a plan or a line of code.

## Non-goals (for now)

- Auto-remediation of any kind.
- Full RBAC (pilot-scale: attribution-only actor identification is
  accepted as a deliberate, tracked decision, not an oversight).
- ML/LLM-based detection (deterministic rules only; an LLM layer is
  sequenced last, for convenience/summarization, not detection itself).
- Peer-group baselining and Firefighter/GRC correlation (require data
  sources — SU01, PFCG, GRC EAM — not ingested at all yet).

## Users

Security analysts/consultants reviewing SAP audit activity across a
client's SAP landscape (Development/Quality/Production/Sandbox), typically
during a security assessment or ongoing monitoring engagement.

## Functional requirements

Sourced from the original `Docs/Security_AI_UseCases_v1.xlsx` catalog (14
use cases) as reconciled in the v2 blueprint. See `Rules.md` for exactly
which are implemented, how, and what SM19 configuration each depends on —
not repeated here to avoid two sources of truth for the same list.

At a system level, the product must let an analyst:
- Collect SAP Security Audit Log events, both on a recurring schedule and
  on demand with specific filters.
- See computed findings, disposition them (true/false positive, with a
  reason), and time-bound whitelist recurring noise.
- Track finding age against a per-severity SLA and see what's overdue.
- Manage the SAP systems/environments being monitored without editing
  server configuration by hand.
- See the health and history of every collection job.
- Export findings and collection history for reporting.
- See whether the SAP system's own audit configuration actually captures
  what the detection rules assume — before quoting coverage to a client.

## Non-functional requirements

- SAP credentials never enter the application's own database — `.env`
  only.
- No external network dependency in the UI (self-contained, since this
  runs against locked-down client networks).
- Every application action is attributable in an audit trail (attribution
  only today, not an access-control boundary — see `Docs/Open_Questions_For_Review.txt`).
- SQLite is the deliberate storage choice at pilot scale; not migrated
  until volume/system-count actually requires it.

## Success metrics

- Time from finding computed → disposed, per severity, against the SLA
  thresholds in `Rules.md`/the SLA dashboard (this is what makes "effort
  reduction" measurable instead of asserted).
- Detection coverage: percentage of implemented rules whose required SM19
  event classes are actively logged, per monitored system (the Coverage
  page — see `Phases.md`, Phase D).
- Zero writes back to SAP, ever (guardrail, not a metric to optimize —
  a violation is a defect, not a tradeoff).

## Roadmap

See `Phases.md` for current status of every phase (A–H) and what's next.
