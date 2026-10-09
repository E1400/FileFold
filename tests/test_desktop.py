"""Desktop app helpers (no window needed). Skipped where PySide6 is not installed."""
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from filefold.desktop import app as desktop  # noqa: E402
from filefold.desktop import icon  # noqa: E402


def test_choose_port_prefers_the_stable_port_so_browser_storage_survives_restarts():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert desktop.choose_port(free) == free


def test_choose_port_falls_back_when_the_stable_port_is_taken():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        taken = s.getsockname()[1]
        port = desktop.choose_port(taken)
    assert port != taken and 0 < port < 65536


def test_choose_port_reuses_the_stable_port_right_after_a_quit():
    """Quitting leaves recently used connections in TIME_WAIT; the next launch must still get the
    same port (the server can bind it), or the window's saved settings are lost."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # as uvicorn does
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    conn, _ = listener.accept()
    conn.close()                    # the server side closes first -> its end sits in TIME_WAIT
    client.close()
    listener.close()
    assert desktop.choose_port(port) == port


def test_only_the_local_server_stays_inside_the_window():
    port = 47321
    assert not desktop.is_external(f"http://127.0.0.1:{port}/?desktop=1", port)
    assert not desktop.is_external(f"http://127.0.0.1:{port}/static/samples/Job-1.inp", port)
    assert not desktop.is_external("blob:http://127.0.0.1:47321/abc", port)
    assert desktop.is_external("https://github.com/E1400/FileFold/releases", port)
    assert desktop.is_external(f"http://127.0.0.1:{port + 1}/", port)


def test_downloads_never_overwrite_an_existing_file(tmp_path):
    first = desktop.unique_download_path(tmp_path, "Job-1.zip")
    assert first == tmp_path / "Job-1.zip"
    first.write_text("x")
    second = desktop.unique_download_path(tmp_path, "Job-1.zip")
    assert second == tmp_path / "Job-1 (1).zip"
    second.write_text("y")
    assert desktop.unique_download_path(tmp_path, "Job-1.zip") == tmp_path / "Job-1 (2).zip"
    assert desktop.unique_download_path(tmp_path, "../../evil.zip").parent == tmp_path   # leaf name only


def test_icon_draws_the_filefold_mark(qapp_offscreen):
    px = icon.make_pixmap(128)
    assert px.width() == 128 and px.height() == 128
    img = px.toImage()
    centre = img.pixelColor(64, 64)
    assert centre.alpha() == 255, "the mark sits in the middle of the icon"


def test_ico_file_is_valid_with_several_sizes(tmp_path, qapp_offscreen):
    out = tmp_path / "icon.ico"
    icon.write_ico(out, sizes=(16, 32, 48, 256))
    data = out.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind, count) == (0, 1, 4)
    for i in range(count):
        w, h, _, _, _, _, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i: 22 + 16 * i])
        assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n" and size > 0
        assert (w or 256) in (16, 32, 48, 256)


@pytest.fixture(scope="module")
def qapp_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_smoke_test_mode_starts_the_server_and_renders_the_ui(tmp_path):
    """`filefold-desktop --smoke-test` is what CI runs against every built bundle."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "FILEFOLD_WORKSPACE_DIR": str(tmp_path / "ws"),
           "FILEFOLD_DESKTOP_DATA": str(tmp_path / "data"), "FILEFOLD_DESKTOP_PORT": "0"}
    out = subprocess.run([sys.executable, "-m", "filefold.desktop.app", "--smoke-test"],
                         env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "SMOKE OK" in out.stdout
