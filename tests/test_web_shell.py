"""Regression tests for sal/web/__init__.py's shell route and its
cache-busting query params on app.js/style.css.

Found live: an already-open SPA tab kept running pre-redesign JavaScript
indefinitely (hash-based client-side routing never reloads the page, so a
plain `no-cache` response header didn't help) - a real page reload could
still serve a stale disk-vs-browser mismatch without something forcing a
genuinely different URL per version. See sal/web/__init__.py's
_asset_version() docstring.
"""
from sal.web import _asset_version, create_app


def _client():
    app = create_app()
    app.testing = True
    return app.test_client()


def test_asset_version_reflects_real_file_mtime():
    from pathlib import Path

    app_js = Path(__file__).resolve().parent.parent / "sal" / "web" / "static" / "js" / "app.js"
    assert _asset_version("js", "app.js") == str(int(app_js.stat().st_mtime))


def test_asset_version_falls_back_for_missing_file():
    assert _asset_version("js", "does-not-exist.js") == "0"


def test_shell_response_includes_versioned_asset_urls():
    client = _client()
    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert "/static/js/app.js?v=" in body
    assert "/static/css/style.css?v=" in body


def test_shell_route_serves_same_page_for_any_client_path():
    """The catch-all route (/<path:_client_route>) must keep serving the
    shell for any hash-routed SPA path (e.g. a bookmark to /findings) -
    the version query params must be present there too, not just at "/".
    """
    client = _client()
    resp = client.get("/findings")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "/static/js/app.js?v=" in body
