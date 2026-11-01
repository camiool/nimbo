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
        pick.clicked.connect(lambda: self._pick(self.mount_edit))
        row = QHBoxLayout()
        row.addWidget(self.mount_edit)
        row.addWidget(pick)
        form.addRow(_("Carpeta de iCloud"), row)

        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(1, 2000)
        self.cache_spin.setSuffix(" GB")
        self.cache_spin.setValue(cfg.cache_max_size_gb)
        form.addRow(_("Espacio máximo para la caché local"), self.cache_spin)

        # --- iCloud Fotos (solo lectura)
        self.photos_check = QCheckBox(_("Mostrar mis fotos de iCloud (solo lectura)"))
        self.photos_check.setChecked(cfg.photos_enabled)
        form.addRow(QLabel(f"<b>{_('iCloud Fotos')}</b>"))
        form.addRow(self.photos_check)
        self.photos_edit = QLineEdit(cfg.photos_mount_point)
        photos_pick = QPushButton(_("Elegir…"))
        photos_pick.clicked.connect(lambda: self._pick(self.photos_edit))
        photos_row = QHBoxLayout()
        photos_row.addWidget(self.photos_edit)
        photos_row.addWidget(photos_pick)
        form.addRow(_("Carpeta de Fotos"), photos_row)
        self.photos_cache = QSpinBox()
        self.photos_cache.setRange(1, 2000)
        self.photos_cache.setSuffix(" GB")
        self.photos_cache.setValue(cfg.photos_cache_max_size_gb)
        form.addRow(_("Caché para fotos"), self.photos_cache)
        hint = QLabel(_("La primera vez puede tardar unos minutos en mostrar todos los "
                        "álbumes. Las fotos no se pueden subir ni borrar desde aquí."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)

        def toggle_photos(on: bool) -> None:
            for w in (self.photos_edit, photos_pick, self.photos_cache):
                w.setEnabled(on)

        self.photos_check.toggled.connect(toggle_photos)
        toggle_photos(cfg.photos_enabled)

        form.addRow(QLabel(f"<b>{_('General')}</b>"))
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

    def _pick(self, target: QLineEdit) -> None:
        chosen = QFileDialog.getExistingDirectory(self, _("Elegir…").rstrip("…"),
                                                  str(Path.home()))
        if chosen:
            target.setText(chosen)

    def _save(self) -> None:
        cfg = self.cfg
        new_mount = str(Path(self.mount_edit.text().strip()).expanduser())
        new_photos = str(Path(self.photos_edit.text().strip()).expanduser())
        photos_on = self.photos_check.isChecked()
        problem = None
        if new_mount != cfg.mount_point:
            problem = folder_problem(Path(new_mount))
        if not problem and photos_on:
            # Si Fotos ya está montado ahí, es normal que la carpeta tenga contenido.
            in_use = cfg.photos_enabled and new_photos == cfg.photos_mount_point
            problem = folder_problem(Path(new_photos), Path(new_mount), allow_nonempty=in_use)
        if problem:
            self.error.setText(problem)
            self.error.show()
            return
        changed = (
            new_mount != cfg.mount_point
            or self.cache_spin.value() != cfg.cache_max_size_gb
            or photos_on != cfg.photos_enabled
            or (photos_on and new_photos != cfg.photos_mount_point)
            or (photos_on and self.photos_cache.value() != cfg.photos_cache_max_size_gb)
        )
        cfg.mount_point = new_mount
        cfg.cache_max_size_gb = self.cache_spin.value()
        cfg.photos_enabled = photos_on
        cfg.photos_mount_point = new_photos
        cfg.photos_cache_max_size_gb = self.photos_cache.value()
        cfg.autostart = self.autostart.isChecked()
        new_language = self.language.currentData()
        language_changed = new_language != cfg.language
        cfg.language = new_language
        cfg.save()

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

