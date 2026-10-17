"""The web UI's desktop mode (`?desktop=1`, set by the desktop app)."""
import os

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.skipif(os.environ.get("FILEFOLD_E2E_TARGET") == "static",
                                reason="the desktop app always uses the server build")


def test_desktop_mode_hides_the_desktop_download_button_and_says_where_files_live(app, base_url):
    expect(app.locator('[aria-label="Download desktop app"]')).to_be_visible()   # normal web build
    app.goto(base_url + "/?desktop=1")
    app.wait_for_load_state("networkidle")
    assert app.evaluate("document.documentElement.dataset.desktop") == "1"
    expect(app.locator('[aria-label="Download desktop app"]')).to_be_hidden()
    app.evaluate("showView('help')")
    text = app.locator("#view-help").inner_text()
    assert "on this computer" in text and "on the server" not in text


def test_a_reload_after_an_update_runs_the_new_scripts_not_cached_ones(app, base_url):
    """The desktop window kept an old build's splits.js for hours after an update (heuristic
    caching), so its Splits tab disagreed with the web app. Every script must be revalidated."""
    seen = {}
    app.on("response", lambda r: seen.__setitem__(r.url.split("?")[0], r))
    app.goto(base_url + "/?desktop=1")
    app.wait_for_load_state("networkidle")
    scripts = [u for u in seen if u.endswith(".js")]
    assert any(u.endswith("/static/splits.js") for u in scripts)
    for url in scripts + [base_url + "/"]:
        assert seen[url].headers.get("cache-control") == "no-cache", url
    status = app.evaluate("fetch('/api/workspaces').then(r => r.headers.get('cache-control'))")
    assert status == "no-store"
