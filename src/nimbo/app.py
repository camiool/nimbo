"""Arranque de Nimbo (una sola instancia por usuario)."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="nimbo", description="iCloud Drive para Linux")
    parser.add_argument("--tray", action="store_true",
                        help="arrancar solo en la bandeja (sin abrir ventanas)")
    parser.add_argument("--version", action="version", version=f"nimbo {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)

    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

    from . import i18n
    from .gui.icons import app_icon
    from .gui.tray import Tray
    from .i18n import _
    from .settings import Settings

    i18n.set_language(Settings.load().language)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nimbo")
    app.setDesktopFileName("nimbo")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    # Si ya hay una instancia, pedirle que se muestre y salir.
    server_name = f"nimbo-{os.getuid()}"
    probe = QLocalSocket()
    probe.connectToServer(server_name)
    if probe.waitForConnected(500):
        if not args.tray:
            probe.write(b"show")
            probe.waitForBytesWritten(500)
        probe.disconnectFromServer()
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Nimbo", _("No hay bandeja del sistema disponible."))
        return 1

    holder: dict[str, Tray] = {}

    def make_tray() -> None:
        # Al cambiar de idioma se crea una bandeja nueva con los textos nuevos.
        old = holder.get("tray")
        tray = Tray(app)
        tray.language_changed.connect(make_tray)
        tray.show()
        holder["tray"] = tray
        if old is not None:
            old.timer.stop()
            old.hide()
            old.deleteLater()

    make_tray()

    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(server_name)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        def on_ready() -> None:
            if bytes(conn.readAll()).startswith(b"show"):
                holder["tray"].show_main()
        conn.readyRead.connect(on_ready)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)

    if not args.tray and not holder["tray"].cfg.is_configured:
        holder["tray"].open_login()

    code = app.exec()
    # Salida ordenada: esperar tareas en curso antes de que Python destruya Qt.
    from PySide6.QtCore import QThreadPool

    holder["tray"].hide()
    server.close()
    QThreadPool.globalInstance().waitForDone(5000)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
