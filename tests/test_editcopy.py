import os
import stat

import pytest

from nimbo import editcopy, integration
from nimbo import settings as st


def test_unique_path(tmp_path):
    assert editcopy.unique_path(tmp_path, "IMG_1.HEIC") == tmp_path / "IMG_1.HEIC"
    (tmp_path / "IMG_1.HEIC").write_text("x")
    assert editcopy.unique_path(tmp_path, "IMG_1.HEIC") == tmp_path / "IMG_1 (2).HEIC"
    (tmp_path / "IMG_1 (2).HEIC").write_text("x")
    assert editcopy.unique_path(tmp_path, "IMG_1.HEIC") == tmp_path / "IMG_1 (3).HEIC"


def _setup(tmp_path, monkeypatch, mounted=True):
    drive = tmp_path / "iCloud"
    drive.mkdir()
    photos = tmp_path / "Fotos" / "PrimarySync" / "Favorites"
    photos.mkdir(parents=True)
    src = photos / "IMG_0001.HEIC"
    src.write_bytes(b"foto original")
    monkeypatch.setattr(editcopy.os.path, "ismount", lambda p: mounted and str(p) == str(drive))
    cfg = st.Settings(mount_point=str(drive), edited_subfolder="Fotos editadas")
    cfg.save()
    return cfg, drive, src


def test_copy_for_editing(tmp_path, monkeypatch):
    cfg, drive, src = _setup(tmp_path, monkeypatch)
    copies = editcopy.copy_for_editing([src, src, tmp_path / "no-existe.jpg"], cfg)
    assert [c.name for c in copies] == ["IMG_0001.HEIC", "IMG_0001 (2).HEIC"]
    assert all(c.parent == drive / "Fotos editadas" for c in copies)
    assert copies[0].read_bytes() == b"foto original"
    assert src.read_bytes() == b"foto original"  # el original no se toca


def test_refuses_when_drive_not_mounted(tmp_path, monkeypatch):
    cfg, drive, src = _setup(tmp_path, monkeypatch, mounted=False)
    with pytest.raises(RuntimeError):
        editcopy.copy_for_editing([src], cfg)
    assert not (drive / "Fotos editadas").exists()  # no ensucia la carpeta de montaje


def test_main_opens_with_editor(tmp_path, monkeypatch):
    cfg, drive, src = _setup(tmp_path, monkeypatch)
    cfg.photo_editor = "gimp --new-instance"
    cfg.save()
    opened, notes = [], []
    monkeypatch.setattr(editcopy.subprocess, "Popen", lambda cmd, **kw: opened.append(cmd))
    monkeypatch.setattr(editcopy, "notify", lambda *a, **k: notes.append(a))
    assert editcopy.main([str(src)]) == 0
    assert opened == [["gimp", "--new-instance", str(drive / "Fotos editadas" / src.name)]]
    assert notes


def test_main_default_app_and_error(tmp_path, monkeypatch):
    cfg, drive, src = _setup(tmp_path, monkeypatch)
    opened, notes = [], []
    monkeypatch.setattr(editcopy.subprocess, "Popen", lambda cmd, **kw: opened.append(cmd))
    monkeypatch.setattr(editcopy, "notify", lambda *a, **k: notes.append((a, k)))
    assert editcopy.main([str(src)]) == 0
    assert opened[0][0] == "xdg-open"

    monkeypatch.setattr(editcopy.os.path, "ismount", lambda p: False)
    notes.clear()
    assert editcopy.main([str(src)]) == 1
    assert notes[0][1] == {"error": True}
    assert editcopy.main([]) == 2


def test_integration_install_and_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(integration.shutil, "which",
                        lambda n: {"nimbo-edit-copy": "/usr/bin/nimbo-edit-copy",
                                   "nautilus": "/usr/bin/nautilus"}.get(n))
    st.ensure_private_dir(st.config_dir())
    st.rclone_config_path().write_text("")
    cfg = st.Settings(apple_id="yo@icloud.com", photos_enabled=True)

    integration.sync(cfg)
    menu = integration.dolphin_path()
    text = menu.read_text()
    assert "Exec=/usr/bin/nimbo-edit-copy %F" in text
    assert "MimeType=image/*;video/*;" in text
    assert "Name[en]=Edit a copy (Nimbo)" in text
    assert os.stat(menu).st_mode & stat.S_IXUSR
    scripts = list(integration.nautilus_dir().iterdir())
    assert len(scripts) == 1
    assert "exec /usr/bin/nimbo-edit-copy \"$@\"" in scripts[0].read_text()

    # Un script del usuario que no es de Nimbo no se borra.
    (integration.nautilus_dir() / "mío").write_text("#!/bin/sh\necho hola\n")
    cfg.photos_enabled = False
    integration.sync(cfg)
    assert not menu.exists()
    assert [p.name for p in integration.nautilus_dir().iterdir()] == ["mío"]


def test_desktop_exec_quotes_spaces():
    assert integration._desktop_exec(["/opt/mi app/python", "-m", "x"]) == \
        '"/opt/mi app/python" -m x %F'
