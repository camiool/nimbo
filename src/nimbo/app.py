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

    from .gui.icons import app_icon
    from .gui.tray import Tray
    from .i18n import _

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

    tray = Tray(app)
    tray.show()

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
                tray.show_main()
        conn.readyRead.connect(on_ready)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)

    if not args.tray and not tray.cfg.is_configured:
        tray.open_login()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
