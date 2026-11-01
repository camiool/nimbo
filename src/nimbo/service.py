"""Servicios de usuario de systemd que mantienen montadas las carpetas de iCloud.

Hay dos montajes, ambos con la misma sesión de Apple (el mismo remoto de
rclone), así que basta un solo inicio de sesión con 2FA:

- ``drive``: iCloud Drive, lectura y escritura.
- ``photos``: iCloud Fotos, solo lectura (rclone no permite subir ni borrar).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import rclone
from . import settings as st
from .i18n import _


@dataclass(frozen=True)
class Mount:
    kind: str  # "drive" o "photos"
    unit_name: str
    description: str

    def unit_path(self) -> Path:
        return st.systemd_unit_dir() / self.unit_name

    def installed(self) -> bool:
        return self.unit_path().exists()


DRIVE = Mount("drive", st.SERVICE_NAME, "iCloud Drive")
PHOTOS = Mount("photos", st.PHOTOS_SERVICE_NAME, "iCloud Fotos")
MOUNTS = (DRIVE, PHOTOS)


def systemd_quote(arg: str) -> str:
    """Cita un argumento para una línea Exec= de systemd."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def _mount_args(mount: Mount, cfg: st.Settings) -> tuple[str, list[str]]:
    """Carpeta de montaje y opciones específicas de cada servicio."""
    if mount is PHOTOS:
        # Opciones recomendadas por la documentación de rclone para Fotos.
        return str(Path(cfg.photos_mount_point).expanduser()), [
            "--iclouddrive-service",
            "photos",
            "--read-only",
            "--vfs-refresh",
            "--dir-cache-time",
            "1h",
            "--attr-timeout",
            "1m",
            "--vfs-cache-max-size",
            f"{cfg.photos_cache_max_size_gb}G",
        ]
    return str(Path(cfg.mount_point).expanduser()), [
        "--vfs-cache-max-size",
        f"{cfg.cache_max_size_gb}G",
        "--vfs-cache-max-age",
        "720h",
        "--dir-cache-time",
        "1m",
    ]


def build_unit(cfg: st.Settings, rclone_path: str, mount: Mount = DRIVE) -> str:
    mount_point, extra = _mount_args(mount, cfg)
    args = [
        rclone_path,
        "mount",
        f"{st.REMOTE_NAME}:",
        mount_point,
        *rclone.common_args(cfg),
        "--cache-dir",
        str(st.cache_dir() / mount.kind),
        "--vfs-cache-mode",
        "full",
        *extra,
        "--rc",
        "--rc-addr",
        f"unix://{st.mount_rc_socket(mount.kind)}",
        "--rc-no-auth",
        "--log-level",
        "INFO",
    ]
    exec_start = " ".join(systemd_quote(a) for a in args)
    quoted_mp = systemd_quote(mount_point)
    return f"""# Generado por Nimbo. Se reescribe al cambiar las preferencias.
[Unit]
Description=Nimbo: {mount.description} en {mount_point.replace("%", "%%")}
After=network-online.target
Wants=network-online.target
# Si la sesión de Apple caducó, no insistir: Nimbo pedirá el código 2FA.
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=notify
# Carpeta propia por servicio: al parar uno no se borra el socket del otro.
RuntimeDirectory=nimbo/{mount.kind}
RuntimeDirectoryMode=0700
ExecStartPre=/usr/bin/mkdir -p {quoted_mp}
ExecStartPre=-/usr/bin/fusermount3 -uz {quoted_mp}
ExecStart={exec_start}
ExecStop=/usr/bin/fusermount3 -uz {quoted_mp}
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, text=True, check=check, timeout=60
    )


def _installed_units() -> list[str]:
    return [m.unit_name for m in MOUNTS if m.installed()]


def install(cfg: st.Settings) -> None:
    """Escribe y activa los servicios según las preferencias (Fotos es opcional)."""
    binary = rclone.rclone_binary()
    if not binary:
        raise rclone.RcloneError(_("rclone no está instalado"))
    st.systemd_unit_dir().mkdir(parents=True, exist_ok=True)
    wanted = [DRIVE, PHOTOS] if cfg.photos_enabled else [DRIVE]
    for mount in MOUNTS:
        if mount in wanted:
            st.ensure_private_dir(st.cache_dir() / mount.kind)
            mount.unit_path().write_text(build_unit(cfg, binary, mount))
        elif mount.installed():
            _systemctl("disable", "--now", mount.unit_name, check=False)
            mount.unit_path().unlink(missing_ok=True)
    _systemctl("daemon-reload")
    _systemctl("enable", *[m.unit_name for m in wanted])


def upgrade_if_needed(cfg: st.Settings) -> bool:
    """Regenera los servicios escritos por una versión anterior de Nimbo."""
    if not DRIVE.installed():
        return False
    if f"RuntimeDirectory=nimbo/{DRIVE.kind}" in DRIVE.unit_path().read_text():
        return False
    install(cfg)
    restart()
    return True


def start() -> None:
    units = _installed_units()
    if units:
        _systemctl("reset-failed", *units, check=False)
        _systemctl("start", *units)


def stop() -> None:
    _systemctl("stop", *[m.unit_name for m in MOUNTS], check=False)


def restart() -> None:
    units = _installed_units()
    if units:
        _systemctl("reset-failed", *units, check=False)
        _systemctl("restart", *units)


def uninstall() -> None:
    _systemctl("disable", "--now", *[m.unit_name for m in MOUNTS], check=False)
    for mount in MOUNTS:
        mount.unit_path().unlink(missing_ok=True)
    _systemctl("daemon-reload", check=False)


def state(mount: Mount = DRIVE) -> str:
    """'active', 'activating', 'inactive', 'failed', ..."""
    proc = _systemctl("is-active", mount.unit_name, check=False)
    return proc.stdout.strip() or "unknown"


def recent_log(lines: int = 80, mount: Mount | None = None) -> str:
    """Registro de un servicio, o de todos si ``mount`` es None."""
    units = [mount] if mount else list(MOUNTS)
    cmd = ["journalctl", "--user"]
    for m in units:
        cmd += ["-u", m.unit_name]
    cmd += ["-n", str(lines), "--no-pager", "-o", "cat" if mount else "short"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    return proc.stdout


def failed_because_of_auth(mount: Mount = DRIVE) -> bool:
    errors = [
        line
        for line in recent_log(60, mount).splitlines()
        if any(tag in line for tag in ("ERROR", "CRITICAL", "Fatal", "Failed"))
    ]
    return rclone.looks_like_auth_error("\n".join(errors))


def write_autostart(enabled: bool) -> None:
    path = st.autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Nimbo\n"
        "Comment=iCloud Drive en la bandeja del sistema\n"
        "Exec=nimbo --tray\n"
        "Icon=nimbo\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )
