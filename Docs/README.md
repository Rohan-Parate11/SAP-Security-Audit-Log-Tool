# SAP Security Audit Log Tool (SAL)

An internal Bristlecone consulting tool that connects to live SAP systems over RFC,
collects SAP Security Audit Log (SM20) events, runs deterministic detection rules
against them, and gives security analysts a dashboard/findings workflow.

**Detection-only** -- nothing in this codebase writes back to SAP or takes
remediating action, ever.

## What it does

- **Collects SM20 audit log events** from one or more SAP systems over RFC, on a
  schedule (APScheduler) or via manual CLI backfill.
- **9 deterministic detection rules** run against collected events (see
  [Detection rules](#detection-rules) below) -- no AI/LLM involved in detection
  itself, every finding is explainable and reproducible.
- **Findings workflow**: a dashboard for analysts to triage findings, record a
  disposition, and track them through SLA/aging.
- **Coverage tracking**: visibility into which systems/date ranges have actually
  been collected, so a gap in monitoring is visible, not silent.
- **ITGC-style reporting & export**: findings/events export for audit evidence.
- **Retention policy**: normalized events retained 1 year (matches typical auditor
  requests); findings/disposition history retained 7 years (SOX audit-trail
  standard) via a daily purge job.
- **Credentials**: either per-system `.env` variables, or an optional central,
  encrypted credential store ("Password Manager") -- see
  [Configuration](#configuration) below. **A SAP credential is never stored in the
  database in plaintext, and the app never writes back to SAP.**

## Requirements

- **Windows** (the SAP NetWeaver RFC SDK's prebuilt Python wheel used here targets
  `win_amd64`; other platforms would need to build `pyrfc` from source).
- **Python 3.11** (64-bit).
- **SAP NetWeaver RFC SDK** -- licensed SAP software. You'll need SAP Support Portal
  / S-user access to download it (see [Step 3](#3-install-the-sap-netweaver-rfc-sdk)
  below). **This is never committed to this repo.**
- A SAP system and an RFC user with read-only authorization to the SM20-related
  function modules (`RSAU_API_GET_LOG_DATA` -- see `Docs/ARCHITECTURE.md`; do not
  assume a different function module name from documentation alone, this project
  has been burned by that before).

## Setup

### 1. Clone and create a virtual environment

```powershell
git clone https://github.com/Rohan-Parate11/SAP-Security-Audit-Log-Tool.git
cd SAP-Security-Audit-Log-Tool
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

`pyrfc` is listed in `requirements.txt`, but it is **not actually installable from
PyPI** -- every release there is yanked or Python-incompatible. Install the
matching prebuilt wheel instead (no compiler needed):

```powershell
pip install "https://github.com/SAP-archive/PyRFC/releases/download/v3.3.1/pyrfc-3.3.1-cp311-cp311-win_amd64.whl"
```

Browse [SAP-archive/PyRFC releases](https://github.com/SAP-archive/PyRFC/releases)
for a different Python version. For running tests / doc tooling, use
`requirements-dev.txt` instead (adds `pytest`, plus `Markdown`/`xhtml2pdf` used only
by `scripts/render_training_pdfs.py`).

### 3. Install the SAP NetWeaver RFC SDK

1. Go to [support.sap.com](https://support.sap.com/) -> **Software Downloads** ->
   search **"SAP NW RFC SDK"**, and download the **Windows on x64 64bit** package.
2. Extract it into this project's root as `nwrfc750P_xx\nwrfcsdk` (with
   `lib`/`include`/`bin` subfolders) -- this folder is gitignored; it's SAP-licensed
   software tied to your S-user, never commit or share it.

### 4. Configure credentials and connection details

Copy `.env.example` to `.env` and fill in your system(s):

```
SAPNWRFC_HOME=nwrfc750P_16-70002755\nwrfcsdk

SAL_SAP_S23_DESCRIPTION=S23
SAL_SAP_S23_ASHOST=
SAL_SAP_S23_SYSNR=
SAL_SAP_S23_CLIENT=
SAL_SAP_S23_USER=
SAL_SAP_S23_PASSWD=
```

Add one `SAL_SAP_<SYSTEM_ID>_*` block per system. `.env` is gitignored -- never
commit it.

*(Optional)* Instead of per-system `.env` passwords, the app has a central,
encrypted credential store ("Password Manager", `sal/credentials.py`) so a
password can be saved and viewed through the UI instead. It requires its own key:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the result as `SAL_CREDENTIAL_ENCRYPTION_KEY` in `.env` -- keep it secret and
back it up separately from `data/sal.db`; it's the only thing that can decrypt any
password saved in the central store.

### 5. Run it

```powershell
python run.py
```

Then open **http://127.0.0.1:5050**.

For a one-off manual backfill instead of (or in addition to) the scheduler:

```powershell
python scripts/collect_sm20.py <SYSTEM_ID> <CLIENT> <DAYS_BACK>
```

## Running tests

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Detection rules

| Rule | What it flags |
|---|---|
| `critical_transaction_usage` | Use of a defined set of sensitive/critical transactions |
| `daily_count_baseline` | A user/system's daily event volume deviating from its own baseline |
| `first_time_transaction` | A user executing a transaction they've never run before |
| `login_attack` | Patterns consistent with a brute-force / login-attack attempt |
| `login_time` | Logins outside expected/approved time windows |
| `mass_user_changes` | A burst of user-master changes in a short window |
| `new_source` | A login or activity from a source (host/terminal) not seen before for that user |
| `out_of_context_transaction` | A transaction run outside its expected role/context |
| `shared_ip_multi_user` | Multiple distinct users active from the same source IP |

Each rule is deterministic and independently testable (see `tests/`) -- no rule
result depends on an LLM or external service call.

## Project structure

```
sal/
  collectors/    Pulls SM20 events from SAP over RFC (sap_connector/) and
                   normalizes them into the events table.
  rules/         One module per detection rule (table above), plus shared
                   helpers (_common.py, _coverage.py, _stats.py) and the
                   registry that wires them into a collection run.
  storage/       Database layer (schema, queries).
  web/           Flask app: api.py (routes), static/ (app.js, style.css),
                   templates/.
  audit.py, findings.py, jobs.py, schedule.py, sla.py, retention.py,
    credentials.py, systems.py, itgc_report.py, itgc_events_report.py, export.py
                 Core domain logic: findings/disposition, scheduled collection
                   jobs, SLA/aging, the retention purge job, the central
                   credential store, saved systems, ITGC-style reporting/export.
scripts/         collect_sm20.py (manual CLI backfill), run_rules.py,
                   render_training_pdfs.py, test_connection.py, probes/ (ad hoc
                   RFC exploration scripts used while validating SAP function
                   modules -- not part of the running app).
tests/           pytest suite covering rules, collectors, findings, credentials,
                   retention, SLA, exports, and the web API.
Docs/            Architecture, PRD, design, durable decision memory, changelog,
                   phase roadmap, and analyst/engineer training guides.
data/            Generated at runtime (SQLite DB, collected events) -- gitignored.
```

Read `Docs/ARCHITECTURE.md` first for the full module map and data flow, and
`Docs/PROJECT-CONTEXT.md` for current phase status and key constraints.

## Security notes

- **A SAP credential is never stored in the database in plaintext.** Per-system
  passwords live only in `.env`; the optional central store encrypts with a key
  that itself is never stored in the database.
- **Never writes back to SAP.** Every SAP call this tool makes is read-only.
- **No external CDN dependencies in the frontend** -- no CDN fonts, icon
  libraries, or JS, since this runs against live, often network-locked-down SAP
  environments and must be self-contained.
- `.env`, `data/` (the runtime database and collected events), and the SAP
  NetWeaver RFC SDK folder are all gitignored.

## Internal / confidential

This is an internal Bristlecone tool. The checked-in `Docs/` folder includes
internal planning material; a small number of genuinely sensitive items (real
ITGC audit-engagement spreadsheets, error screenshots) were deliberately excluded
from version control rather than committed.

