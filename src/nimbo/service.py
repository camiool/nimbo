"""Servicio de usuario de systemd que mantiene montada la carpeta de iCloud."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import rclone
from . import settings as st
from .i18n import _


def systemd_quote(arg: str) -> str:
    """Cita un argumento para una línea Exec= de systemd."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def build_unit(cfg: st.Settings, rclone_path: str) -> str:
    mount_point = str(Path(cfg.mount_point).expanduser())
    args = [
        rclone_path,
        "mount",
        f"{st.REMOTE_NAME}:",
        mount_point,
        *rclone.common_args(cfg),
        "--cache-dir",
        str(st.cache_dir()),
        "--vfs-cache-mode",
        "full",
        "--vfs-cache-max-size",
        f"{cfg.cache_max_size_gb}G",
        "--vfs-cache-max-age",
        "720h",
        "--dir-cache-time",
        "1m",
        "--rc",
        "--rc-addr",
        f"unix://{st.mount_rc_socket()}",
        "--rc-no-auth",
        "--log-level",
        "INFO",
    ]
    exec_start = " ".join(systemd_quote(a) for a in args)
    quoted_mp = systemd_quote(mount_point)
    return f"""# Generado por Nimbo. Se reescribe al cambiar las preferencias.
[Unit]
Description=Nimbo: iCloud Drive en {mount_point.replace("%", "%%")}
After=network-online.target
Wants=network-online.target
# Si la sesión de Apple caducó, no insistir: Nimbo pedirá el código 2FA.
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=notify
RuntimeDirectory=nimbo
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


def install(cfg: st.Settings) -> None:
    binary = rclone.rclone_binary()
    if not binary:
        raise rclone.RcloneError(_("rclone no está instalado"))
    unit = st.systemd_unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    st.ensure_private_dir(st.cache_dir())
    unit.write_text(build_unit(cfg, binary))
    _systemctl("daemon-reload")
    _systemctl("enable", st.SERVICE_NAME)


def start() -> None:
    _systemctl("reset-failed", st.SERVICE_NAME, check=False)
    _systemctl("start", st.SERVICE_NAME)


def stop() -> None:
    _systemctl("stop", st.SERVICE_NAME, check=False)


def restart() -> None:
    _systemctl("reset-failed", st.SERVICE_NAME, check=False)
    _systemctl("restart", st.SERVICE_NAME)


def uninstall() -> None:
    _systemctl("disable", "--now", st.SERVICE_NAME, check=False)
    st.systemd_unit_path().unlink(missing_ok=True)
    _systemctl("daemon-reload", check=False)


def state() -> str:
    """'active', 'activating', 'inactive', 'failed', ..."""
    proc = _systemctl("is-active", st.SERVICE_NAME, check=False)
    return proc.stdout.strip() or "unknown"


def recent_log(lines: int = 80) -> str:
    proc = subprocess.run(
        [
            "journalctl",
            "--user",
            "-u",
            st.SERVICE_NAME,
            "-n",
            str(lines),
            "--no-pager",
            "-o",
            "cat",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return proc.stdout


def failed_because_of_auth() -> bool:
    errors = [
        line
        for line in recent_log(60).splitlines()
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
