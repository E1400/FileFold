"""The FileFold app icon, drawn from the same mark as the web UI's logo.

Used at runtime (window and tray icon) and by build/make_icons.py to write the bundle icons
(.icns for macOS, a multi-size .ico for Windows) without extra dependencies.
"""
from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QPolygonF

GROUND = QColor("#E8E9E5")   # the app's surface colour
RULE = QColor("#212523")     # ink
DOC = QColor("#1A2438")      # the logo's document
FOLD = QColor("#58A6FF")     # the logo's folded corner


def make_pixmap(size: int) -> QPixmap:
    """A square icon: the logo's document mark on the app's light ground."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    inset = size * 0.06 if size >= 64 else 0.0          # room for the system's shadow on big icons
    tile = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = tile.width() * 0.22
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(GROUND)
    p.drawRoundedRect(tile, radius, radius)
    if size >= 32:                                       # a hairline edge, like the app's rules
        p.setPen(RULE)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tile.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.setPen(Qt.PenStyle.NoPen)

    # the mark: a 20 x 24 document with its top-right corner folded, as in the web logo
    h = tile.height() * 0.62
    w = h * 20 / 24
    x0 = tile.center().x() - w / 2
    y0 = tile.center().y() - h / 2
    s = h / 24
    pt = lambda x, y: QPointF(x0 + x * s, y0 + y * s)
    doc = QPainterPath()
    doc.addPolygon(QPolygonF([pt(0, 0), pt(13, 0), pt(20, 7), pt(20, 24), pt(0, 24)]))
    p.fillPath(doc, DOC)
    fold = QPainterPath()
    fold.addPolygon(QPolygonF([pt(13, 0), pt(20, 7), pt(13, 7)]))
    p.fillPath(fold, FOLD)
    p.end()
    return px


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    make_pixmap(size).save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """A Windows .ico holding one PNG per size (supported since Windows Vista)."""
    images = [png_bytes(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(sizes, images):
        dim = 0 if size >= 256 else size                 # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    Path(path).write_bytes(header + entries + b"".join(images))


def write_icns(path: Path) -> None:
    """A macOS .icns, built with the system's iconutil."""
    iconset = Path(tempfile.mkdtemp()) / "FileFold.iconset"
    iconset.mkdir()
    for s in (16, 32, 128, 256, 512):
        make_pixmap(s).save(str(iconset / f"icon_{s}x{s}.png"), "PNG")
        make_pixmap(s * 2).save(str(iconset / f"icon_{s}x{s}@2x.png"), "PNG")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)
