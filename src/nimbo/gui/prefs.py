"""Ventana de preferencias."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import i18n, keyring, service
from .. import settings as st
from ..i18n import _
from .icons import app_icon
from .login import folder_problem
from .worker import run_async


def sign_out(cfg: st.Settings) -> None:
    """Desmonta, borra credenciales locales y caché. No toca iCloud."""
    service.uninstall()
    service.write_autostart(False)
    st.rclone_config_path().unlink(missing_ok=True)
    keyring.clear()
    shutil.rmtree(st.cache_dir(), ignore_errors=True)
    cfg.apple_id = ""
    cfg.config_encrypted = False
    cfg.save()


class PrefsDialog(QDialog):
    signed_out = Signal()
    language_changed = Signal()

    def __init__(self, cfg: st.Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(_("Preferencias…").rstrip("…"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(480)

        form = QFormLayout()
        form.addRow(_("Apple ID (correo)"), QLabel(cfg.apple_id or "—"))

        self.mount_edit = QLineEdit(cfg.mount_point)
        pick = QPushButton(_("Elegir…"))
        pick.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.mount_edit)
        row.addWidget(pick)
        form.addRow(_("Carpeta de iCloud"), row)

        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(1, 2000)
        self.cache_spin.setSuffix(" GB")
        self.cache_spin.setValue(cfg.cache_max_size_gb)
        form.addRow(_("Espacio máximo para la caché local"), self.cache_spin)

        self.autostart = QCheckBox(_("Iniciar Nimbo al iniciar sesión"))
        self.autostart.setChecked(cfg.autostart)
        form.addRow(self.autostart)

        self.language = QComboBox()
        self.language.addItem(_("Automático (idioma del sistema)"), "auto")
        for code, name in i18n.LANGUAGES.items():
            self.language.addItem(name, code)
        index = self.language.findData(cfg.language)
        self.language.setCurrentIndex(max(index, 0))
        form.addRow(_("Idioma"), self.language)

        self.error = QLabel()
        self.error.setStyleSheet("color: #e74c3c;")
        self.error.setWordWrap(True)
        self.error.hide()

        sign_out_btn = QPushButton(_("Cerrar sesión en iCloud"))
        sign_out_btn.setEnabled(cfg.is_configured)
        sign_out_btn.clicked.connect(self._sign_out)

        buttons = QDialogButtonBox()
        buttons.addButton(_("Guardar"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(_("Cancelar"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(sign_out_btn)
        bottom.addStretch()
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addLayout(bottom)

    def _pick(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, _("Carpeta de iCloud"),
                                                  str(Path.home()))
        if chosen:
            self.mount_edit.setText(chosen)

    def _save(self) -> None:
        new_mount = str(Path(self.mount_edit.text().strip()).expanduser())
        mount_changed = new_mount != self.cfg.mount_point
        if mount_changed:
            problem = folder_problem(Path(new_mount))
            if problem:
                self.error.setText(problem)
                self.error.show()
                return
        changed = mount_changed or self.cache_spin.value() != self.cfg.cache_max_size_gb
        self.cfg.mount_point = new_mount
        self.cfg.cache_max_size_gb = self.cache_spin.value()
        self.cfg.autostart = self.autostart.isChecked()
        new_language = self.language.currentData()
        language_changed = new_language != self.cfg.language
        self.cfg.language = new_language
        self.cfg.save()
        cfg = self.cfg

        def work() -> None:
            service.write_autostart(cfg.autostart)
            if changed and cfg.is_configured:
                service.stop()
                service.install(cfg)
                service.start()

        run_async(work, on_error=lambda e: QMessageBox.warning(None, _("Error"), str(e)))
        if language_changed:
            i18n.set_language(new_language)
            self.language_changed.emit()
        self.accept()

    def _sign_out(self) -> None:
        answer = QMessageBox.question(
            self,
            _("Cerrar sesión en iCloud"),
            _("¿Cerrar sesión? La carpeta se desmontará y se borrarán las credenciales "
              "y la caché de este equipo. Tus archivos en iCloud no se tocan."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        sign_out(self.cfg)
        self.signed_out.emit()
        self.accept()


class LogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_("Registro de Nimbo"))
        self.setWindowIcon(app_icon())
        self.resize(760, 460)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText("…")
        close = QDialogButtonBox()
        close.addButton(_("Cerrar"), QDialogButtonBox.ButtonRole.RejectRole)
        close.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(view)
        lay.addWidget(close)

        def show(text: str) -> None:
            view.setPlainText(text or "—")
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

        run_async(lambda: service.recent_log(400), show,
                  lambda e: view.setPlainText(str(e)))

