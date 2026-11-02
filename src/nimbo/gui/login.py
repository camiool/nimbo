"""Asistente de inicio de sesión (primera vez) y renovación del 2FA."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import integration, keyring, rclone, service
from .. import settings as st
from ..i18n import _
from .icons import app_icon
from .worker import run_async

_STEP_TEXT = {
    "config_2fa": "Revisa tu iPhone, iPad o Mac: Apple te mostrará un código de 6 dígitos.",
    "config_2fa_sms": "Introduce el código que recibiste por SMS.",
    "config_2fa_phone": "Elige el teléfono al que enviar el SMS.",
}


def folder_problem(
    path: Path, other: Path | None = None, allow_nonempty: bool = False
) -> str | None:
    """Motivo por el que no se puede montar en ``path`` (o None si vale).

    ``other`` es la carpeta del otro montaje: no pueden coincidir ni ir una
    dentro de la otra.
    """
    path = path.expanduser().resolve()
    if other is not None:
        other = other.expanduser().resolve()
        if path == other or path.is_relative_to(other) or other.is_relative_to(path):
            return _("Las carpetas de iCloud Drive y de Fotos deben ser distintas "
                     "y no estar una dentro de la otra.")
    if not allow_nonempty and path.exists() and path.is_dir() and any(path.iterdir()):
        return _("La carpeta elegida no está vacía. Elige una carpeta vacía o nueva.")
    return None


def check_rclone(parent: QWidget | None) -> bool:
    version = rclone.installed_version()
    if version and version >= rclone.MIN_VERSION:
        return True
    QMessageBox.warning(
        parent,
        _("Falta rclone"),
        _("Nimbo necesita rclone {min} o más nuevo. Instálalo con:",
          min=".".join(map(str, rclone.MIN_VERSION)))
        + "\n\n    sudo pacman -S rclone fuse3",
    )
    return False


class LoginDialog(QDialog):
    """`reauth=False`: alta inicial. `reauth=True`: solo repetir el 2FA."""

    finished_ok = Signal()

    def __init__(self, cfg: st.Settings, reauth: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.reauth = reauth
        self.session: rclone.SetupSession | None = None
        self.step: rclone.ConfigStep | None = None

        self.setWindowTitle(_("Iniciar sesión en iCloud"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(460)

        self.pages = QStackedWidget()
        self.page_intro = self._build_intro()
        self.page_creds = self._build_creds()
        self.page_busy = self._build_busy()
        self.page_step = self._build_step()
        self.page_done = self._build_done()
        for page in (self.page_intro, self.page_creds, self.page_busy, self.page_step,
                     self.page_done):
            self.pages.addWidget(page)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.hide()

        self.btn_cancel = QPushButton(_("Cancelar"))
        self.btn_extra = QPushButton(_("Enviar código por SMS"))
        self.btn_next = QPushButton(_("Siguiente"))
        self.btn_next.setDefault(True)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_extra.clicked.connect(lambda: self._submit("sms"))

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_extra)
        buttons.addStretch()
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_next)

        layout = QVBoxLayout(self)
        layout.addWidget(self.pages)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)

        self._show(self.page_creds if reauth else self.page_intro)

    # ------------------------------------------------------------------ páginas

    def _build_intro(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel(f"<h2>{_('Antes de empezar')}</h2>")
        body = QLabel(
            "<p>{}</p><ul><li>{}</li><li>{}</li></ul><p><small>{}</small></p>".format(
                _("Para que Nimbo pueda acceder a tu iCloud Drive, comprueba esto en tu "
                  "iPhone, iPad o Mac:"),
                _("<b>Acceder a datos de iCloud en la web</b> debe estar <b>activado</b> "
                  "(Ajustes → tu nombre → iCloud)."),
                _("Si usas <b>Protección de datos avanzada</b>, Apple te pedirá aprobar "
                  "el acceso en uno de tus dispositivos."),
                _("Tu contraseña viaja solo entre este equipo y Apple. Se guarda en este "
                  "equipo cifrada con una clave que vive en el llavero del sistema."),
            )
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(title)
        lay.addWidget(body)
        lay.addStretch()
        return w

    def _build_creds(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.apple_id = QLineEdit(self.cfg.apple_id)
        self.apple_id.setPlaceholderText("nombre@icloud.com")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        if self.reauth:
            self.apple_id.setReadOnly(True)
            self.password.setPlaceholderText(
                _("Contraseña (déjala vacía si no la has cambiado)"))
        form.addRow(QLabel(f"<h2>{_('Iniciar sesión en iCloud')}</h2>"))
        form.addRow(_("Apple ID (correo)"), self.apple_id)
        form.addRow(_("Contraseña"), self.password)
        return w

    def _build_busy(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.busy_label = QLabel(_("Hablando con Apple…"))
        self.busy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar = QProgressBar()
        bar.setRange(0, 0)
        lay.addStretch()
        lay.addWidget(self.busy_label)
        lay.addWidget(bar)
        lay.addStretch()
        return w

    def _build_step(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.step_title = QLabel(f"<h2>{_('Código de verificación')}</h2>")
        self.step_help = QLabel()
        self.step_help.setWordWrap(True)
        self.step_input = QLineEdit()
        self.step_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.step_input.font()
        font.setPointSize(font.pointSize() + 6)
        font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 4)
        self.step_input.setFont(font)
        self.step_choice = QComboBox()
        lay.addWidget(self.step_title)
        lay.addWidget(self.step_help)
        lay.addWidget(self.step_input)
        lay.addWidget(self.step_choice)
        lay.addStretch()
        return w

    def _build_done(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(QLabel(f"<h2>{_('¡Listo!')}</h2>"))
        form.addRow(QLabel(_("Tus archivos de iCloud Drive aparecerán en:")))
        self.mount_edit = QLineEdit(self.cfg.mount_point)
        pick = QPushButton(_("Elegir…"))
        pick.clicked.connect(self._pick_folder)
        row = QHBoxLayout()
        row.addWidget(self.mount_edit)
        row.addWidget(pick)
        form.addRow(_("Carpeta de iCloud"), row)
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(1, 2000)
        self.cache_spin.setSuffix(" GB")
        self.cache_spin.setValue(self.cfg.cache_max_size_gb)
        form.addRow(_("Espacio máximo para la caché local"), self.cache_spin)
        self.photos_check = QCheckBox(_("Mostrar también mis fotos de iCloud (solo lectura)"))
        self.photos_check.setChecked(self.cfg.photos_enabled)
        form.addRow(self.photos_check)
        self.autostart_check = QCheckBox(_("Iniciar Nimbo al iniciar sesión"))
        self.autostart_check.setChecked(self.cfg.autostart)
        form.addRow(self.autostart_check)
        return w

    def _pick_folder(self) -> None:
        start = str(Path(self.mount_edit.text()).expanduser().parent)
        chosen = QFileDialog.getExistingDirectory(self, _("Carpeta de iCloud"), start)
        if chosen:
            self.mount_edit.setText(chosen)

    # ------------------------------------------------------------- navegación

    def _show(self, page: QWidget) -> None:
        self.pages.setCurrentWidget(page)
        busy = page is self.page_busy
        self.btn_next.setEnabled(not busy)
        self.btn_next.setVisible(not busy)
        self.btn_extra.setVisible(
            page is self.page_step and self.step is not None and self.step.name == "config_2fa"
        )
        self.btn_next.setText(
            _("Terminar") if page is self.page_done
            else _("Enviar") if page is self.page_step
            else _("Siguiente")
        )

    def _busy(self, text: str) -> None:
        self.error_label.hide()
        self.busy_label.setText(text)
        self._show(self.page_busy)

    def _fail(self, exc: Exception, back_to: QWidget) -> None:
        self.error_label.setText(str(exc))
        self.error_label.show()
        self._show(back_to)

    def _on_next(self) -> None:
        page = self.pages.currentWidget()
        if page is self.page_intro:
            if check_rclone(self):
                self._show(self.page_creds)
        elif page is self.page_creds:
            self._start_login()
        elif page is self.page_step:
            if self.step and self.step.choices:
                self._submit(self.step_choice.currentData())
            else:
                self._submit(self.step_input.text().strip())
        elif page is self.page_done:
            self._finish_setup()

    # ---------------------------------------------------------------- flujo

    def _start_login(self) -> None:
        apple_id = self.apple_id.text().strip()
        password = self.password.text()
        if not apple_id or (not self.reauth and not password):
            return
        if not self.reauth and not self.cfg.config_encrypted and not keyring.available():
            answer = QMessageBox.question(
                self,
                _("No hay llavero disponible"),
                _("No se encontró secret-tool (paquete libsecret). La configuración se "
                  "guardará sin cifrar (solo legible por tu usuario). ¿Continuar?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        cfg = self.cfg
        reauth = self.reauth

        def work() -> rclone.ConfigStep | None:
            if reauth:
                service.stop()  # el montaje no debe escribir rclone.conf a la vez
            elif not cfg.config_encrypted and keyring.available():
                st.rclone_config_path().unlink(missing_ok=True)
                rclone.encrypt_config(cfg)
                cfg.save()
            if self.session is None:
                self.session = rclone.SetupSession(cfg)
                self.session.start()
            if reauth:
                return self.session.reconnect(password or None)
            return self.session.create(apple_id, password)

        self._busy(_("Hablando con Apple…"))
        run_async(work, self._on_step, lambda e: self._fail(e, self.page_creds))

    def _submit(self, value: str) -> None:
        if not value or self.step is None or self.session is None:
            return
        step, session = self.step, self.session
        self._busy(_("Hablando con Apple…"))
        run_async(lambda: session.answer(step, value), self._on_step,
                  lambda e: self._fail(e, self.page_step))

    def _on_step(self, step: rclone.ConfigStep | None) -> None:
        self.step = step
        if step is None:
            self._verify()
            return
        self.step_help.setText(_(_STEP_TEXT.get(step.name, step.help)))
        self.step_input.clear()
        self.step_choice.clear()
        for value, text in step.choices:
            self.step_choice.addItem(text or value, value)
        self.step_input.setVisible(not step.choices)
        self.step_choice.setVisible(bool(step.choices))
        self.step_input.setEchoMode(
            QLineEdit.EchoMode.Password if step.is_password else QLineEdit.EchoMode.Normal
        )
        if step.error:
            self.error_label.setText(step.error)
            self.error_label.show()
        self._show(self.page_step)
        self.step_input.setFocus()

    def _verify(self) -> None:
        session = self.session
        assert session is not None
        self._busy(_("Comprobando el acceso a iCloud Drive…"))
        run_async(session.check_drive, lambda _r: self._verified(),
                  lambda e: self._fail(e, self.page_creds))

    def _verified(self) -> None:
        self._close_session()
        self.cfg.apple_id = self.apple_id.text().strip()
        self.cfg.save()
        if self.reauth:
            run_async(service.restart, lambda _r: self._success(),
                      lambda e: self._fail(e, self.page_creds))
        else:
            self._show(self.page_done)

    def _finish_setup(self) -> None:
        mount = Path(self.mount_edit.text().strip()).expanduser()
        photos = self.photos_check.isChecked()
        problem = folder_problem(mount)
        if not problem and photos:
            problem = folder_problem(Path(self.cfg.photos_mount_point), mount)
        if problem:
            self.error_label.setText(problem)
            self.error_label.show()
            return
        self.cfg.mount_point = str(mount)
        self.cfg.cache_max_size_gb = self.cache_spin.value()
        self.cfg.autostart = self.autostart_check.isChecked()
        self.cfg.photos_enabled = photos
        self.cfg.save()
        cfg = self.cfg

        def work() -> None:
            service.write_autostart(cfg.autostart)
            integration.sync(cfg)
            service.install(cfg)
            service.start()

        self._busy(_("Conectando…"))
        run_async(work, lambda _r: self._success(), lambda e: self._fail(e, self.page_done))

    def _success(self) -> None:
        self.finished_ok.emit()
        self.accept()

    def _close_session(self) -> None:
        if self.session:
            self.session.stop()
            self.session = None

    def done(self, result: int) -> None:  # noqa: D401 - API de Qt
        session = self.session
        self.session = None
        if session:
            run_async(session.stop)
        if self.reauth and result != QDialog.DialogCode.Accepted:
            # Si se cancela la renovación, volver a intentar montar con lo que hay.
            run_async(service.start)
        super().done(result)
