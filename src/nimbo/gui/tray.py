"""Icono en la bandeja del sistema."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import HOMEPAGE, __version__, service
from .. import settings as st
from ..i18n import _
from ..status import Snapshot, Status, StatusProbe
from .icons import app_icon, status_icon
from .login import LoginDialog, check_rclone
from .prefs import LogDialog, PrefsDialog
from .worker import run_async

POLL_MS = 3000

_LABELS = {
    Status.UNCONFIGURED: "Sin configurar",
    Status.CONNECTING: "Conectando…",
    Status.OK: "Conectado",
    Status.PAUSED: "En pausa",
    Status.AUTH: "Hay que volver a iniciar sesión",
    Status.ERROR: "Error",
}


def human_speed(bps: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1024
    return ""


class Tray(QSystemTrayIcon):
    # Pide a app.py que rehaga la bandeja con el nuevo idioma.
    language_changed = Signal()

    def __init__(self, app: QApplication):
        super().__init__(status_icon(Status.CONNECTING), app)
        self.app = app
        self.cfg = st.Settings.load()
        self.probe = StatusProbe()
        self.status: Status | None = None
        self._polling = False
        self._dialog = None  # ventana abierta (evita duplicados)

        self.menu = QMenu()
        self.act_status = QAction("…")
        self.act_status.setEnabled(False)
        self.act_open = QAction(_("Abrir carpeta de iCloud"))
        self.act_open.triggered.connect(self.open_folder)
        self.act_pause = QAction(_("Pausar sincronización"))
        self.act_pause.triggered.connect(self.toggle_pause)
        self.act_login = QAction(_("Iniciar sesión en iCloud…"))
        self.act_login.triggered.connect(self.open_login)
        act_prefs = QAction(_("Preferencias…"), self)
        act_prefs.triggered.connect(self.open_prefs)
        act_log = QAction(_("Ver registro"), self)
        act_log.triggered.connect(self.open_log)
        act_about = QAction(_("Acerca de Nimbo"), self)
        act_about.triggered.connect(self.about)
        act_quit = QAction(_("Salir"), self)
        act_quit.triggered.connect(app.quit)

        for item in (self.act_status, None, self.act_open, self.act_pause, self.act_login,
                     None, act_prefs, act_log, act_about, None, act_quit):
            if item is None:
                self.menu.addSeparator()
            else:
                self.menu.addAction(item)
        self.setContextMenu(self.menu)
        self.setToolTip("Nimbo")

        self.activated.connect(self._on_activated)
        self.messageClicked.connect(self._on_message_clicked)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(POLL_MS)
        self.poll()

    # --------------------------------------------------------------- estado

    def poll(self) -> None:
        if self._polling:
            return
        self._polling = True
        cfg = self.cfg

        def done(snap: Snapshot) -> None:
            self._polling = False
            self._apply(snap)

        def failed(exc: Exception) -> None:
            self._polling = False
            self._apply(Snapshot(Status.ERROR, detail=str(exc)))

        run_async(lambda: self.probe.poll(cfg), done, failed)

    def _apply(self, snap: Snapshot) -> None:
        previous, self.status = self.status, snap.status
        if snap.status is Status.SYNCING and snap.transfers:
            n = snap.transfers.transferring + snap.transfers.queued_uploads
            label = _("Sincronizando {n} archivo(s) · {speed}", n=n,
                      speed=human_speed(snap.transfers.speed))
        else:
            label = _(_LABELS.get(snap.status, "…"))
        self.act_status.setText(label)
        self.setToolTip(f"Nimbo — {label}")
        self.setIcon(status_icon(snap.status))

        configured = snap.status is not Status.UNCONFIGURED
        self.act_open.setEnabled(snap.status in (Status.OK, Status.SYNCING))
        self.act_pause.setVisible(configured)
        self.act_pause.setText(
            _("Reanudar sincronización") if snap.status in (Status.PAUSED, Status.ERROR)
            else _("Pausar sincronización")
        )
        self.act_login.setText(
            _("Volver a iniciar sesión…") if configured else _("Iniciar sesión en iCloud…")
        )

        if previous is not snap.status:
            if snap.status is Status.AUTH:
                self.showMessage(
                    _("Tu sesión de iCloud caducó"),
                    _("Apple pide verificar tu identidad cada cierto tiempo. Haz clic para "
                      "introducir el código."),
                    QSystemTrayIcon.MessageIcon.Warning,
                )
            elif snap.status is Status.ERROR and previous is not None:
                self.showMessage(
                    _("No se pudo montar iCloud Drive"),
                    _("Revisa el registro para más detalles."),
                    QSystemTrayIcon.MessageIcon.Critical,
                )

    # ------------------------------------------------------------- acciones

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason is QSystemTrayIcon.ActivationReason.Trigger:
            if self.status is Status.AUTH:
                self.open_login()
            elif self.status is Status.UNCONFIGURED:
                self.open_login()
            else:
                self.open_folder()

    def _on_message_clicked(self) -> None:
        if self.status is Status.AUTH:
            self.open_login()
        else:
            self.open_log()

    def open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.cfg.mount_point))))

    def toggle_pause(self) -> None:
        if self.status in (Status.PAUSED, Status.ERROR):
            fn = service.start
        else:
            fn = service.stop
        run_async(fn, lambda _r: self.poll(),
                  lambda e: QMessageBox.warning(None, _("Error"), str(e)))

    def _single(self, factory):
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.raise_()
            self._dialog.activateWindow()
            return None
        dialog = factory()
        self._dialog = dialog
        dialog.finished.connect(lambda _r: self._dialog_closed())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _dialog_closed(self) -> None:
        self._dialog = None
        self.cfg = st.Settings.load()
        self.probe.force_health_check()
        self.poll()

    def open_login(self) -> None:
        reauth = self.cfg.is_configured
        if not reauth or check_rclone(None):
            self._single(lambda: LoginDialog(self.cfg, reauth=reauth))

    def open_prefs(self) -> None:
        dialog = self._single(lambda: PrefsDialog(self.cfg))
        if dialog is not None:
            dialog.language_changed.connect(self.language_changed.emit)

    def open_log(self) -> None:
        self._single(LogDialog)

    def about(self) -> None:
        box = QMessageBox()
        box.setWindowTitle(_("Acerca de Nimbo"))
        box.setIconPixmap(app_icon().pixmap(64, 64))
        box.setText(
            f"<h3>Nimbo {__version__}</h3>"
            f"<p>{_('Cliente libre de iCloud Drive para Linux.')}</p>"
            "<p>GPL-3.0-or-later · "
            f"<a href='{HOMEPAGE}'>GitHub</a> · "
            "<a href='https://rclone.org'>rclone</a></p>"
            f"<p><small>{_('Nimbo no está afiliado a Apple. iCloud es una marca de Apple Inc.')}"
            "</small></p>"
        )
        box.exec()

    def show_main(self) -> None:
        """Llamado al ejecutar `nimbo` cuando ya está abierto."""
        if self.cfg.is_configured:
            self.open_prefs()
        else:
            self.open_login()
