"""Iconos: la nube de Nimbo con un punto de color según el estado."""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ..status import Status

_DOT = {
    Status.UNCONFIGURED: "#9e9e9e",
    Status.CONNECTING: "#9e9e9e",
    Status.OK: "#2ecc71",
    Status.SYNCING: "#3498db",
    Status.PAUSED: "#9e9e9e",
    Status.AUTH: "#f39c12",
    Status.ERROR: "#e74c3c",
}

_cache: dict[Status, QIcon] = {}


def app_icon() -> QIcon:
    themed = QIcon.fromTheme("nimbo")
    if not themed.isNull():
        return themed
    path = resources.files("nimbo") / "assets" / "nimbo.svg"
    return QIcon(str(path))


def status_icon(status: Status) -> QIcon:
    if status in _cache:
        return _cache[status]
    base = app_icon()
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64):
        pix = base.pixmap(size, size)
        if pix.isNull():
            pix = QPixmap(size, size)
            pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if status in (Status.PAUSED, Status.UNCONFIGURED, Status.CONNECTING):
            # Atenuar la nube cuando no está activa.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.fillRect(pix.rect(), QColor(0, 0, 0, 140))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        d = max(6, size * 0.42)
        painter.setPen(QColor("#ffffff"))
        painter.setBrush(QColor(_DOT[status]))
        painter.drawEllipse(int(size - d), int(size - d), int(d) - 1, int(d) - 1)
        painter.end()
        icon.addPixmap(pix)
    _cache[status] = icon
    return icon
