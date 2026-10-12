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
