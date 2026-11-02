"""Rutas y preferencias de Nimbo."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .i18n import _

APP_ID = "nimbo"
REMOTE_NAME = "icloud"
SERVICE_NAME = "nimbo-mount.service"
PHOTOS_SERVICE_NAME = "nimbo-photos.service"


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / APP_ID


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / APP_ID


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(base) / APP_ID


def rclone_config_path() -> Path:
    return config_dir() / "rclone.conf"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def mount_rc_socket(kind: str = "drive") -> Path:
    """Socket de control de un montaje ("drive" o "photos"); su carpeta la crea systemd."""
    return runtime_dir() / kind / "rc.sock"


def setup_rc_socket() -> Path:
    """Socket temporal usado durante el inicio de sesión."""
    return runtime_dir() / "setup.sock"


def systemd_unit_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "systemd" / "user"


def autostart_path() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / "nimbo.desktop"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


@dataclass
class Settings:
    mount_point: str = field(default_factory=lambda: str(Path.home() / "iCloud"))
    cache_max_size_gb: int = 10
    # True cuando rclone.conf está cifrado con una clave guardada en el llavero.
    config_encrypted: bool = False
    apple_id: str = ""
    autostart: bool = True
    # "auto" (según el sistema), "es" o "en".
    language: str = "auto"
    # iCloud Fotos (solo lectura), opcional.
    photos_enabled: bool = False
    photos_mount_point: str = field(default_factory=lambda: str(Path.home() / _("Fotos de iCloud")))
    photos_cache_max_size_gb: int = 5
    # "Editar una copia": subcarpeta de iCloud Drive para las copias y programa
    # con el que abrirlas (vacío = el predeterminado del sistema).
    edited_subfolder: str = field(default_factory=lambda: _("Fotos editadas"))
    photo_editor: str = ""

    @classmethod
    def load(cls) -> Settings:
        try:
            data = json.loads(settings_path().read_text())
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        ensure_private_dir(config_dir())
        path = settings_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.chmod(0o600)
        tmp.replace(path)

    @property
    def is_configured(self) -> bool:
        return bool(self.apple_id) and rclone_config_path().exists()
