"""Ejecuta tareas lentas (red, systemctl) fuera del hilo de la interfaz."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - se informa a la interfaz
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


_live: set[_Task] = set()


def run_async(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    task = _Task(fn)
    task.setAutoDelete(False)
    _live.add(task)

    def finish() -> None:
        _live.discard(task)

    # Las señales se emiten desde otro hilo: se encolan para ejecutarse en el
    # hilo principal, que es el único que puede tocar la interfaz.
    queued = Qt.ConnectionType.QueuedConnection
    if on_done:
        task.signals.done.connect(on_done, queued)
    if on_error:
        task.signals.failed.connect(on_error, queued)
    task.signals.done.connect(finish, queued)
    task.signals.failed.connect(finish, queued)
    QThreadPool.globalInstance().start(task)
