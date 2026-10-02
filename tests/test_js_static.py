"""Static check of the UI's JavaScript (src/filefold/web/static/*.js): undeclared identifiers fail the build.

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
    # The page is a set of classic scripts sharing one global scope, so lint them as
    # one file, concatenated in the order index.html loads them.
    srcs = re.findall(r'<script src="/static/([^"]+)"', html)
    assert srcs, "no script files linked from index.html"
    code = "\n".join((INDEX.parent / "static" / s).read_text(encoding="utf-8") for s in srcs)
    (tmp_path / "ui.js").write_text(code, encoding="utf-8")
    try:
        result = _run_eslint(tmp_path)
    except subprocess.TimeoutExpired:
        pytest.skip("npm registry unreachable (ESLint could not be fetched); CI runs this check")
    assert result.returncode == 0, result.stdout + result.stderr


def _run_eslint(tmp_path):
    return subprocess.run(
        ["npx", "--yes", "--prefer-offline", "eslint@9", "--no-config-lookup", "-c", str(ROOT / "js" / "eslint.config.mjs"), "ui.js"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
    )
