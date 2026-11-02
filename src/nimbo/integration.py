"""Opción "Editar una copia" en el menú del clic derecho de Dolphin y Nautilus."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from . import settings as st
from .i18n import _

DOLPHIN_FILE = "nimbo-edit-copy.desktop"
_MIMES = "image/*;video/*;"


def _data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value else Path.home() / ".local" / "share"


def dolphin_path() -> Path:
    return _data_home() / "kio" / "servicemenus" / DOLPHIN_FILE


def nautilus_dir() -> Path:
    return _data_home() / "nautilus" / "scripts"


def _command() -> list[str]:
    exe = shutil.which("nimbo-edit-copy")
    return [exe] if exe else [sys.executable, "-m", "nimbo.editcopy"]


def _desktop_exec(parts: list[str]) -> str:
    # Formato Exec de la especificación de archivos .desktop.
    def quote(p: str) -> str:
        if any(c in p for c in ' \t"\'\\$`'):
            return '"' + p.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")\
                .replace("`", "\\`") + '"'
        return p
    return " ".join(quote(p) for p in parts) + " %F"


def build_dolphin_menu() -> str:
    return f"""[Desktop Entry]
Type=Service
MimeType={_MIMES}
X-KDE-ServiceTypes=KonqPopupMenu/Plugin
Actions=nimboEditCopy
X-KDE-Priority=TopLevel

[Desktop Action nimboEditCopy]
Name=Editar una copia (Nimbo)
Name[es]=Editar una copia (Nimbo)
Name[en]=Edit a copy (Nimbo)
Icon=document-edit
Exec={_desktop_exec(_command())}
"""


def _nautilus_script_name() -> str:
    return _("Editar una copia (Nimbo)")


def build_nautilus_script() -> str:
    cmd = " ".join(shlex.quote(p) for p in _command())
    return f'#!/bin/sh\n# Generado por Nimbo.\nexec {cmd} "$@"\n'


def install() -> None:
    menu = dolphin_path()
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(build_dolphin_menu())
    menu.chmod(0o755)  # Plasma exige permiso de ejecución en los menús de usuario
    if shutil.which("nautilus"):
        remove_nautilus()
        script = nautilus_dir() / _nautilus_script_name()
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(build_nautilus_script())
        script.chmod(0o755)


def remove_nautilus() -> None:
    folder = nautilus_dir()
    if folder.is_dir():
        for script in folder.iterdir():
            if script.is_file() and "# Generado por Nimbo." in script.read_text(errors="ignore"):
                script.unlink()


def remove() -> None:
    dolphin_path().unlink(missing_ok=True)
    remove_nautilus()


def sync(cfg: st.Settings) -> None:
    """Instala el atajo si Fotos está activado; si no, lo quita."""
    if cfg.is_configured and cfg.photos_enabled:
        install()
    else:
        remove()
