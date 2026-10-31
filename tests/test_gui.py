"""Pruebas de humo de la interfaz (Qt en modo offscreen)."""

import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from nimbo import rclone, service  # noqa: E402
from nimbo import settings as st  # noqa: E402
from nimbo.gui import icons, login, prefs  # noqa: E402
from nimbo.status import Status  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from PySide6.QtCore import QCoreApplication, QThreadPool

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield qapp
    # Cerrar en orden: ventanas, tareas pendientes y por último Qt. Si no,
    # Python destruye los objetos de Qt en cualquier orden al salir.
    for widget in qapp.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QThreadPool.globalInstance().waitForDone(5000)
    QCoreApplication.sendPostedEvents(None, 0)
    QCoreApplication.processEvents()
    gc.collect()
    if hasattr(qapp, "shutdown"):
        qapp.shutdown()


@pytest.fixture(autouse=True)
def drain_background_tasks(monkeypatch):
    """Nunca llamar a systemctl de verdad y esperar a las tareas en segundo
    plano antes de deshacer los parches (si no, Qt puede cerrarse a medias)."""
    for name in ("start", "stop", "restart", "install", "uninstall"):
        monkeypatch.setattr(service, name, lambda *a, **k: None)
    yield
    from PySide6.QtCore import QCoreApplication, QThreadPool

    QThreadPool.globalInstance().waitForDone(5000)
    QCoreApplication.processEvents()


def test_status_icons(app):
    for s in Status:
        assert not icons.status_icon(s).isNull()


def test_login_dialog_steps(app):
    dlg = login.LoginDialog(st.Settings())
    assert dlg.pages.currentWidget() is dlg.page_intro
    dlg._on_step(rclone.ConfigStep(state="2fa_do", name="config_2fa", help="x"))
    assert dlg.pages.currentWidget() is dlg.page_step
    assert dlg.btn_extra.isVisibleTo(dlg)  # botón "SMS"
    assert "6" in dlg.step_help.text()  # texto propio, no el de rclone

    dlg._on_step(rclone.ConfigStep(state="s", name="config_2fa_phone", help="x",
                                   choices=[("1:sms", "+34 ••• 12")]))
    assert dlg.step_choice.count() == 1
    assert not dlg.btn_extra.isVisibleTo(dlg)
    dlg.session = None
    dlg.close()


def test_reauth_dialog_starts_on_credentials(app):
    dlg = login.LoginDialog(st.Settings(apple_id="yo@icloud.com"), reauth=True)
    assert dlg.pages.currentWidget() is dlg.page_creds
    assert dlg.apple_id.isReadOnly()
    dlg.reject()


def test_folder_problem(tmp_path):
    assert login.folder_problem(tmp_path / "nueva") is None
    (tmp_path / "llena").mkdir()
    (tmp_path / "llena" / "a.txt").write_text("x")
    assert login.folder_problem(tmp_path / "llena")


def test_prefs_dialog(app):
    dlg = prefs.PrefsDialog(st.Settings())
    dlg.cache_spin.setValue(25)
    dlg.autostart.setChecked(False)
    dlg._save()
    saved = st.Settings.load()
    assert saved.cache_max_size_gb == 25
    assert not saved.autostart


def test_sign_out_cleans_local_state(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "uninstall", lambda: calls.append("uninstall"))
    monkeypatch.setattr(prefs.keyring, "clear", lambda: calls.append("keyring"))
    st.ensure_private_dir(st.config_dir())
    st.rclone_config_path().write_text("secreto")
    st.ensure_private_dir(st.cache_dir())
    cfg = st.Settings(apple_id="yo@icloud.com", config_encrypted=True)
    prefs.sign_out(cfg)
    assert calls == ["uninstall", "keyring"]
    assert not st.rclone_config_path().exists()
    assert not st.cache_dir().exists()
    assert st.Settings.load().apple_id == ""
