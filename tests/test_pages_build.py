"""The Python shipped to the browser must work with the standard library alone."""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_zip(tmp_path: Path) -> Path:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_pages
    dest = tmp_path / "filefold-py.zip"
    build_pages.build_python_zip(dest)
    return dest


def test_zip_contains_no_server_or_gui_code(tmp_path):
    names = zipfile.ZipFile(_build_zip(tmp_path)).namelist()
    assert "filefold/browser.py" in names and "filefold/service.py" in names
    assert not any(n.startswith(("filefold/api/routes", "filefold/cli", "filefold/desktop")) for n in names)
    assert "filefold/api/main.py" not in names


def test_zip_runs_on_the_standard_library_only(tmp_path):
    """-I -S: no site-packages, so FastAPI/Typer/Qt cannot be imported even if installed."""
    z = _build_zip(tmp_path)
    code = (
        f"import sys; sys.path.insert(0, {str(z)!r}); import os; os.environ['FILEFOLD_WORKSPACE_DIR'] = {str(tmp_path / 'ws')!r};"
        "from filefold import browser; "
        "status, ctype, headers, body = browser.handle('GET', '/api/sub-options'); "
        "assert status == 200 and ctype == 'application/json', (status, body); "
        "assert not any(m in sys.modules for m in ('fastapi', 'starlette', 'pydantic', 'typer', 'PySide6')); "
        "print('ok')"
    )
    out = subprocess.run([sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stdout + out.stderr
