"""Generate icon assets for PyInstaller bundles.

Run once before building:
    uv run python build/make_icons.py

Outputs:
    build/icon.icns   (macOS)
    build/icon.ico    (Windows)
    build/icon.png    (source, 1024x1024)
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

BUILD = Path(__file__).parent


def make_pixmap(size: int) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background rounded rect
    radius = size * 0.22
    p.setBrush(QColor("#0C0F14"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, radius, radius)

    # Accent band at top
    p.setBrush(QColor("#58A6FF"))
    p.drawRoundedRect(0, 0, size, int(size * 0.38), radius, radius)
    p.fillRect(0, int(size * 0.18), size, int(size * 0.2), QColor("#58A6FF"))

    # "FF" text
    font = QFont("Arial", int(size * 0.36), QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor("#000000"))
    p.drawText(0, 0, size, int(size * 0.48), Qt.AlignmentFlag.AlignCenter, "FF")

    # "FileFold" sub-label (only readable at larger sizes)
    if size >= 128:
        sub_font = QFont("Arial", int(size * 0.09), QFont.Weight.Medium)
        p.setFont(sub_font)
        p.setPen(QColor("#58A6FF"))
        p.drawText(0, int(size * 0.56), size, int(size * 0.2),
                   Qt.AlignmentFlag.AlignCenter, "FileFold")

    p.end()
    return px


def main() -> None:
    _app = QApplication.instance() or QApplication([])

    # PNG source (1024 for macOS retina)
    px1024 = make_pixmap(1024)
    png_path = BUILD / "icon.png"
    px1024.save(str(png_path), "PNG")
    print(f"Wrote {png_path}")

    # .icns via iconutil (macOS only)
    import platform
    if platform.system() == "Darwin":
        import subprocess, tempfile, os, shutil
        iconset = Path(tempfile.mkdtemp()) / "FileFold.iconset"
        iconset.mkdir()
        sizes = [16, 32, 64, 128, 256, 512, 1024]
        for s in sizes:
            make_pixmap(s).save(str(iconset / f"icon_{s}x{s}.png"), "PNG")
            if s <= 512:
                make_pixmap(s * 2).save(str(iconset / f"icon_{s}x{s}@2x.png"), "PNG")
        icns = BUILD / "icon.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
        shutil.rmtree(iconset.parent)
        print(f"Wrote {icns}")

    # .ico (Windows — embed multiple sizes)
    try:
        from PIL import Image
        import io
        frames = []
        for s in [16, 24, 32, 48, 64, 128, 256]:
            buf = io.BytesIO()
            make_pixmap(s).save(buf, "PNG")  # type: ignore[arg-type]  # Qt saves to BytesIO? No...
            buf.seek(0)
            frames.append(Image.open(buf))
        ico_path = BUILD / "icon.ico"
        frames[0].save(ico_path, format="ICO", sizes=[(f.width, f.height) for f in frames],
                       append_images=frames[1:])
        print(f"Wrote {ico_path}")
    except ImportError:
        # Pillow not installed; save a single PNG fallback as .ico
        make_pixmap(256).save(str(BUILD / "icon.ico"), "PNG")
        print("Pillow not found — wrote fallback icon.ico (single size PNG)")


if __name__ == "__main__":
    main()
