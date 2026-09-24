# Presenter Script — SSAT, SAL & Transport Advisor

Talk track for the SSAT, SAL, and Transport Advisor slides in
`ABB_ModernizationAI_23Sept2026.pptx` (slides 3, 5, and 4). Read it as a
conversation, not a script to recite word for word — the point is to hit
these beats in your own voice, in whatever order feels natural once you're
actually standing in front of the slide.

---

## 1. SSAT — Automated SAP Security & Compliance Assessment

So this one is SSAT — the Security Assessment Tool. Think about how a
SAP security assessment normally happens today: a consultant shows up,
spends a few days walking through a checklist by hand in SAP GUI, cross-
referencing tables and transactions one at a time, and then compiles
whatever they found into a spreadsheet. It works, but it's slow, and it's
only as consistent as whoever happens to be running it that week. Two
consultants doing the same assessment can come back with two different
answers, and there's no real way to prove what "good" is supposed to look
like across ECC, S/4HANA, GRC, and Fiori landscapes.

SSAT takes that same checklist and automates it. It connects to a
customer's SAP landscape over RFC and runs upwards of twenty standardized
checks around various functions.
Every single check logs the RFC calls it made along the way, so if a
consultant needs to go back and explain why something was flagged — or
troubleshoot why it wasn't — that trail already exists. And instead of
someone writing up "413 users have SAP_ALL" as a raw finding, SSAT turns
that into a plain-English key finding a business lead can read without
needing to know what SAP_ALL even is.

What used to take days now takes minutes, and it never touches the system. Read-only,
by design, running over the same standard SAP RFC layer that's already
there. No new software, nothing to install, nothing that needs its own
security review before you can even start using it.


We are also planning on layering risk and remediation guidance on top of
what's already being extracted — so it's not just "here's what we found,"
it's "here's what to do about it". In longer term, the plan is
executive dashboards, risk heat maps, and eventually S/4HANA
transformation-readiness scoring — and that's the roadmap.
---

## 2. SAL — Automated SAP Security Monitoring

Where SSAT is a point-in-time assessment, SAL is what watches
continuously afterward — SAL is the Security Audit Log tool. SAP's
Security Audit Log, SM20, technically has everything you'd need to
catch a problem, but almost nobody reviews it consistently. Someone has
to remember to check manually, on some cadence, and there's no record
afterward of what they actually looked at or whether anything slipped
through. Whatever they do find usually lives in their own memory or a
personal spreadsheet — it doesn't survive them going on leave, let alone
a client audit.

SAL connects to SAP over RFC, strictly read-only, and pulls Security
Audit Log activity daily, automatically, or on demand for any date
range, user, or transaction. It runs the same fourteen detection rules
against every event, every time, across multiple categories. A critical
transaction — a payment run, say — gets flagged regardless of who ran it
or what role they hold, because that shouldn't depend on trusting
everyone's judgment in the moment.

What actually changes how a security team works day to day is what
happens after a finding shows up. Someone makes a real call on it — true
positive, false positive, or accepted risk — with a reason, and that
reason is permanent. It's what makes the whole thing defensible later,
whether that's an internal review or an auditor asking how you know
this got looked at. Disposition history sits for seven years, in line
with SOX, and raw event data for one year, which is what auditors
actually ask for — not kept forever "just in case."

Next up: peer comparison, so the system flags when someone's access
pattern looks unusual next to people doing the same job, plus a
dedicated look at emergency "Firefighter" access sessions. And down the
line, letting someone just ask the system a question in plain English
and get a summary back, instead of having to know which report to run.

---

## 3. Transport Advisor — for SAP Transport Queues

This one's a bit more in-the-weeds than the last two, but if you've ever
managed SAP transports, you'll recognize the pain immediately. A
transport queue is just the line of change packages waiting to go into a
system — and here's the part nobody warns you about: SAP will happily
import an older transport after a newer one, silently undo real work in
the process, and hand back a clean return code zero — success — even
though something you fixed weeks ago just quietly came back. No error,
no warning. You find out when someone asks why a bug you already closed
is suddenly open again.

Transport Advisor reads five standard exports — SE16 and STMS data,
nothing exotic, nothing new to set up — and turns that blind queue into
an actual risk-scored release plan. It catches the overtakes I just
described, flags stale transport copies before they revert later work,
and catches customizing key overlaps — two transports quietly fighting
over the same config entry — before either one goes in.

Under the hood it's four detectors working together, plus a couple of
things I'd actually call out specifically: the key-overlap check is
honest about its own confidence — it separates an exact match it's sure
about from a wildcard match it's only fairly confident about — and the
sequencer doesn't just reorder the queue silently, it'll hold a
transport back and tell you exactly why. There's a transparent severity
score behind all of it too, so nobody has to just take the tool's word
for it.

What I'd actually want people to remember: this needed zero new SAP
access to build — no new users, no OData, nothing. It's built entirely
from exports that already exist. It ships as both a CLI report and a
small web app with three views — the pending queue, a retrospective
replay of real import history, and a summary — and it's backed by
thirty-five automated tests, one file per detector, deliberately kept
independent of each other so a change in one can't quietly break
another. And it's done — seven out of seven steps for this first
release, tested end to end against real data.

Four numbers here too: four detectors, thirty-five passing tests, three
web views, and seven of seven steps complete.
