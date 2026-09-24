# SAL — 5-Minute Business Demo Script

**Audience:** business stakeholders / leadership (non-technical)
**Goal:** show what SAL does, why it matters, and what a reviewer's day-to-day looks like — in 5 minutes.
**Total run time:** ~5 minutes talk track + live clicks. Practice once; the click-throughs add ~30–60s beyond the words alone.

## Before you start (30 seconds of prep, not part of the timed script)

- Have the app open at the **Dashboard** for the pilot system (Development), already logged in with your display name.
- Make sure there's at least one finding in **Awaiting Review** status, and at least one already **resolved**, so both states are visible without extra clicking.
- Have the **Collect** tab and **Findings** tab open in background browser tabs so you can switch instantly instead of navigating live.
- Optional: keep `Docs/SAL_Overview.pptx` (or the numbers-first v2) open as a leave-behind, but don't present from slides — drive the live app.

---

## 0:00–0:30 — The problem, in one breath

> "Today, reviewing SAP's Security Audit Log is manual and reactive. Someone has to remember to look, there's no persisted record of what was actually reviewed or by whom, and there's no way to prove coverage is happening or improving. Findings live in someone's memory or a spreadsheet — nothing forces them to actually get resolved."

**[ON SCREEN: stay on a blank browser tab or the login screen — no app yet. This is the "before" picture.]**

---

## 0:30–1:00 — What SAL is, in one breath

> "SAL fixes that. It connects directly to SAP — read-only, it never writes anything back — and automatically pulls Security Audit Log activity every day, or on demand for any date range, user, or transaction. Then it runs the same 14 detection rules against every event, every time, across every system. Every finding gets tracked to resolution with a full audit trail: who reviewed it, when, and why."

**[ON SCREEN: open the app to the Dashboard.]**

---

## 1:00–2:00 — The Dashboard: what a reviewer sees first

> "This is what an analyst opens every morning. These tiles show open findings by severity, how many are aging past SLA, and how many systems are covered. Nothing here is guesswork — every number ties back to an actual detection run against actual SAP data."

**[ON SCREEN: point at the severity tiles, then the SLA/aging panel. Hover one bar to show the tooltip.]**

> "Notice the SLA tracking — severity-based, so nothing sits unreviewed indefinitely. A High finding has a tighter clock than a Low one, and this panel shows exactly what's overdue right now."

---

## 2:00–3:00 — Collect → Detect: where the data comes from

**[ON SCREEN: switch to the Collect tab.]**

> "Collection can run two ways. Automatically, every day, in the background — that's the default. Or, like right now, on demand: pick a date range, optionally narrow to a specific user or transaction, and pull it live."

**[ON SCREEN: point to the Date from / Date to fields, then click "Fetch from SAP" if you have a safe demo window, or explain without submitting if live SAP access isn't available in the room.]**

> "Once the data lands, all 14 rules run automatically — no one has to remember to trigger detection. They cover five areas: login and access anomalies, suspicious or first-time transaction usage, segregation-of-duties visibility, sensitive data protection, and administrative oversight like bulk account changes. A payment-run transaction, for example, is always flagged regardless of who ran it or what role they hold."

---

## 3:00–4:00 — Triage: turning a finding into a decision

**[ON SCREEN: switch to the Findings tab. Open one open finding.]**

> "This is where a finding actually gets closed out. An analyst marks it true positive, false positive, or accepted risk — and has to give a reason. That reason is permanent; it's what makes this defensible later, whether that's an internal review or an external audit."

**[ON SCREEN: point to disposition history / whitelist option if visible.]**

> "If something's a known, accepted pattern — a scheduled job that always looks unusual but isn't a problem — it can be whitelisted with a reason and an expiry date, so it stops generating noise without disappearing from the record."

---

## 4:00–4:30 — Reporting: what leadership and audit actually get

**[ON SCREEN: show the Export menu or Retention page briefly.]**

> "Everything here exports — findings, the raw event log, the full activity trail of who did what inside the tool itself. Disposition history is kept seven years, aligned with SOX audit-trail expectations. Raw event data is kept one year, which matches what auditors actually ask to see."

---

## 4:30–5:00 — Close: the numbers to remember

> "Four numbers to take away: **100%** read-only — it can never change anything in SAP. **Daily** automated collection, or on demand any time. **14** deterministic detection rules, the same criteria every time. And **7 years** of audit-ready disposition history."
>
> "We're piloting today on the Development environment. The architecture already supports the full landscape — Dev, QA, Production, and Sandbox — without any rework, so extending coverage from here is a scope decision, not a build."

**[END. Pause for questions — see cheat sheet below.]**

---

## Quick-answer cheat sheet (if asked)

| Question | Short answer |
|---|---|
| "Can it accidentally change something in SAP?" | No — it only reads. There is no code path that writes back to SAP, by design. |
| "Who can see this data?" | Currently attribution-only (a self-declared reviewer name), no role-based access control yet — deliberate at this pilot scale, revisited before wider rollout. |
| "What happens to old data?" | Raw events: 1 year, then purged. Finding/disposition history: 7 years, matching SOX retention expectations. |
| "How is this different from someone just watching SM20 in SAP?" | SM20 shows raw log lines with no memory of what's been reviewed. SAL persists every review decision, tracks SLA aging, and applies the same 14 rules consistently — SAP itself does none of that. |
| "What's next after the pilot?" | Rolling out to QA, Production, and Sandbox; the architecture already supports it. A scoped, least-privilege SAP service account is also planned as a follow-up hardening step. |
| "Does it use AI/ML to detect things?" | No — today's detection is deterministic, rule-based logic, not machine learning. Every flag traces back to an explicit, explainable rule. |
