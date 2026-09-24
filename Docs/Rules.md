# SAL Detection Rules

Catalog of the 11 implemented detection use cases (12 distinct rule keys
- #14 produces two, see below). Numbering matches the
original `Docs/Security_AI_UseCases_v1.xlsx` / v1 blueprint's Detection Use
Case Catalog, so the two documents can be read side by side. For how rules
fit into the overall data flow (events → rules → findings), see
`ARCHITECTURE.md`. For the exact SM19 event-class each rule depends on and
how that's checked against live configuration, see `sal/rules/_coverage.py`
and the Coverage page (Phase D, `Phases.md`).

All rules are deterministic — no ML/LLM. Every finding's "why flagged" text
is a plain Python string template, not a model output.

| # | Use case | Rule key | Source file | SM19 class needed | Mapping confidence |
|---|---|---|---|---|---|
| 1 | Unusual login time | `login_time` | `sal/rules/login_time.py` | Login | high |
| 2 | Unusual login frequency | `login_frequency` | `sal/rules/daily_count_baseline.py` | Login | high |
| 3 | Unusual source terminal/IP | `new_source` | `sal/rules/new_source.py` | Login | high |
| 4 | Unusual transaction execution | `unusual_transaction` | `sal/rules/first_time_transaction.py` | Transaction start | high |
| 5 | Unusual activity volume | `activity_volume` | `sal/rules/daily_count_baseline.py` | Transaction start | high |
| 7 | Multiple users, same source | `shared_ip` | `sal/rules/shared_ip_multi_user.py` | Login | high |
| 8 | Unusual export of data | `sensitive_table_access`, `data_export` | `sal/rules/export.py` | Other events | **moderate** — class assignment for these two rules not independently verified against a live system, see `_coverage.py` |
| 9 | Potential login attack | `login_attack` | `sal/rules/login_attack.py` | Login | high |
| 11 | First-time sensitive transaction | `first_time_sensitive_transaction` | `sal/rules/first_time_transaction.py` | Transaction start | high |
| 12 | Mass user updates | `mass_user_changes` | `sal/rules/mass_user_changes.py` | User master change | high |
| 14 | Suspicious/out-of-context transaction usage | `out_of_context_transaction`, `out_of_context_no_role_data` | `sal/rules/out_of_context_transaction.py` | Transaction start | high (SM19 coverage only - also depends on `sal/role_context.py`'s AGR_USERS/AGR_TCODES refresh being current, which SM19 coverage can't express) |

Use case #14 (Phase F) cross-references a critical-transaction `AU3` event
against the user's **currently** assigned SAP roles
(`sal/role_context.py`, fed by a live `RFC_READ_TABLE` read of
`AGR_USERS`/`AGR_TCODES`, refreshed daily) - not their access at the time
the transaction actually ran, which SAP's own data doesn't let this tool
reconstruct once a role has been fully revoked (see
`sal/role_context.py`'s docstring). Two distinct rule keys, not one: a
user whose roles simply don't cover the tcode
(`out_of_context_transaction`) is a different, more common finding than a
user with zero role assignments on record at all
(`out_of_context_no_role_data`) - conflating them would hide the more
unusual case. Because `sync_findings()` re-evaluates all retained
history on every run, an event that was fine when it happened surfaces
as a new finding the moment the user's current access no longer covers
it - this is the deliberate mechanism behind the audit scenario Phase F
was built to answer: "show me everyone who ran transaction X in the
audit window, including anyone whose access has since changed."

## Not yet implemented (from the original 14)

- **#6** Deviation from peer users — needs a peer-group baseline built on
  top of the role data #14 already ingests. Sequenced as a Phase F
  fast-follow, deliberately not bundled with #14 (a harder, separate
  statistical design problem: what counts as a "peer group" and
  meaningful deviation from it).
- **#10** Firefighter/GRC session analysis — needs GRC EAM tables, not
  ingested. Explicitly deferred pending separate approval (Phase F,
  eventually).
- **#13** Natural-language "ask the tool" query — an LLM-layer feature,
  deliberately last (Phase H) since every current finding is already
  explainable via deterministic templates without one.

## A note on message-code vs. event-class precision

`sal/rules/_coverage.py`'s mapping is deliberately at the SM19 **event
class** level (Login, Transaction start, User master change, etc.), not
individual message codes (AU1, AU2, AU3, DU9, ...), even though most rules
actually filter on specific message codes internally (see each rule's own
`fetch_events(msg_codes=...)` call). The reason: `RSAU_API_GET_AUDIT_CONFIG`
returns message-code-level detail as an undocumented byte-vector
(`MSGVECT`) with no verifiable bit encoding — guessing at it risks a false
"you're covered" signal, which the Phase D planning review flagged as
worse than the coverage blind spot the phase exists to close. Event-class
flags are named, self-describing booleans and safe to trust. Message-code
precision is a deliberate future increment, not an oversight.

## Known drift risk

`mass_user_changes.py` enforces `event_class="User master changes"` in its
actual query, with the specific message codes it's really about
(AUD/AU7/AUB/AUA/BU2) documented only in a code comment, not enforced.
`sal/rules/_coverage.py` was cross-checked against every rule's real
filter logic when written (see `tests/test_audit_config.py`'s
`test_rule_coverage_has_no_drift_from_the_real_rule_registry`, which fails
loudly if a rule is ever added/removed without updating this mapping) —
but a rule's *internal* filter changing without the coverage mapping being
revisited is exactly the failure mode that test cannot catch. Re-verify
`_coverage.py` by hand whenever a rule's `fetch_events()` call changes.
