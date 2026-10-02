"""Static check of the single-page UI's JavaScript: undeclared identifiers fail the build.

Needs Node/npx (present on GitHub runners and dev machines); skipped otherwise.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
INDEX = ROOT.parent / "src" / "filefold" / "web" / "index.html"


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx not installed")
def test_ui_javascript_has_no_undeclared_identifiers(tmp_path):
    html = INDEX.read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.S)
    assert scripts, "no inline script found"
    (tmp_path / "ui.js").write_text("\n".join(scripts), encoding="utf-8")
    result = subprocess.run(
        ["npx", "--yes", "eslint@9", "--no-config-lookup", "-c", str(ROOT / "js" / "eslint.config.mjs"), "ui.js"],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
