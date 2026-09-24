"""Flask application factory for SAL.

Serves one shell page; all views (dashboard, findings, connection test) are
rendered client-side against the JSON API in api.py, so switching views or
filters updates in place instead of a full-page reload.
"""
import os
from pathlib import Path

from flask import Flask, render_template

from .. import config  # noqa: F401  loads .env / SDK path before any pyrfc use
from .. import jobs
from ..catalogues import seed_default_critical_transactions, seed_default_sensitive_tables
from .api import api_bp

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _asset_version(*rel_parts: str) -> str:
    """A cache-busting query value for a static asset, derived from its own
    mtime - no build step (per CLAUDE.md's constraint) means no content-hash
    pipeline, so this is the lightest thing that actually invalidates a
    browser's cached app.js/style.css whenever the file on disk changes.
    Without it, an already-open SPA tab happily keeps running old
    JavaScript forever - hash-based client-side routing never reloads the
    page on its own, so a plain `no-cache` response header doesn't help;
    only a real full-page navigation re-fetches the script at all, and even
    then a stale disk-vs-browser mismatch was possible without a version
    bump forcing a genuinely different URL. Falls back to "0" if the file
    is missing rather than raising, since a missing static asset is a
    deployment problem the browser will surface as its own 404, not
    something this helper should crash the page over.
    """
    try:
        return str(int(_STATIC_DIR.joinpath(*rel_parts).stat().st_mtime))
    except OSError:
        return "0"


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(api_bp)

    # run.py always runs via app.run(debug=True), so Werkzeug's reloader is
    # active and spawns a parent watcher process plus one child that actually
    # serves requests - WERKZEUG_RUN_MAIN is set only in that child. This
    # guard keeps the job worker and scheduler from starting twice. It
    # assumes the reloader is present; running this app without it (e.g. a
    # production WSGI server) would need this revisited - that now also
    # applies to the catalogue seeding below (security-reviewer flagged
    # this: a future non-run.py deployment would silently never seed the
    # default critical-transaction/sensitive-table catalogues that some
    # detection rules, e.g. out_of_context_transaction, depend on).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        # Critical-transaction/sensitive-table catalogue defaults are static
        # after first insert (INSERT OR IGNORE against a hardcoded dict) -
        # seed them once here rather than on every /api/dashboard,
        # /api/findings, or /api/catalogues/* request, which used to re-run
        # this idempotent insert loop (and the schema init it triggers) on
        # every single page view. Must run before start_worker()/
        # start_daily_scheduler() below, since a background job could start
        # executing detection rules (e.g. out_of_context_transaction) that
        # read these catalogues almost immediately.
        seed_default_critical_transactions()
        seed_default_sensitive_tables()
        jobs.start_worker()
        jobs.start_daily_scheduler()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    @app.get("/<path:_client_route>")
    def shell(_client_route=None):
        return render_template(
            "shell.html",
            app_js_version=_asset_version("js", "app.js"),
            style_css_version=_asset_version("css", "style.css"),
        )

    return app
