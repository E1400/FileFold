"""Write the desktop bundle icons from the app's own logo mark (filefold/desktop/icon.py).

    uv run python build/make_icons.py

Outputs build/icon.png (1024 px source), build/icon.ico (Windows, multi-size) and, on macOS,
build/icon.icns. Needs PySide6 (the `desktop` extra); runs without a display.
"""
import os
import platform
import sys
from pathlib import Path

BUILD = Path(__file__).parent
sys.path.insert(0, str(BUILD.parent / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from filefold.desktop import icon  # noqa: E402


def main() -> None:
    _app = QApplication.instance() or QApplication([])
    icon.make_pixmap(1024).save(str(BUILD / "icon.png"), "PNG")
    icon.write_ico(BUILD / "icon.ico")
    print("wrote build/icon.png, build/icon.ico")
    if platform.system() == "Darwin":
        icon.write_icns(BUILD / "icon.icns")
        print("wrote build/icon.icns")


if __name__ == "__main__":
    main()
