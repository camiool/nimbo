"""Comunicación con rclone.

Nimbo nunca pasa la contraseña de Apple por la línea de comandos (sería
visible con `ps`). En su lugar arranca `rclone rcd` escuchando en un socket
Unix privado (dentro de $XDG_RUNTIME_DIR, permisos 0700) y le envía las
credenciales en el cuerpo de una petición HTTP local.
"""

from __future__ import annotations

import http.client
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import settings as st
from .i18n import _

MIN_VERSION = (1, 70, 0)


class RcloneError(Exception):
    """Error devuelto por rclone o al hablar con él."""


class AuthExpiredError(RcloneError):
    """La sesión de iCloud caducó y hay que repetir el 2FA."""


_AUTH_PATTERNS = re.compile(
    r"trust token expired|missing icloud trust token|please reauth|"
    r"\b401\b|\b421\b|unauthori[sz]ed|-20101",
    re.IGNORECASE,
)


def looks_like_auth_error(message: str) -> bool:
    return bool(_AUTH_PATTERNS.search(message or ""))


# --------------------------------------------------------------------------
# Binarios y versión
# --------------------------------------------------------------------------


def rclone_binary() -> str | None:
    return shutil.which("rclone")


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"rclone v?(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in match.groups()) if match else None  # type: ignore[return-value]


def installed_version() -> tuple[int, int, int] | None:
    binary = rclone_binary()
    if not binary:
        return None
    try:
        out = subprocess.run(
            [binary, "version"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_version(out)


def keyring_command() -> list[str]:
    """Comando que rclone usará como --password-command."""
    exe = shutil.which("nimbo-keyring")
    if exe:
        return [exe]
    return [sys.executable, "-m", "nimbo.keyring"]


def _join_command(parts: list[str]) -> str:
    # rclone interpreta --password-command como una lista separada por
    # espacios con comillas al estilo CSV.
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def common_args(cfg: st.Settings) -> list[str]:
    args = ["--config", str(st.rclone_config_path())]
    if cfg.config_encrypted:
        args += ["--password-command", _join_command(keyring_command())]
    return args


def encrypt_config(cfg: st.Settings) -> None:
    """Cifra rclone.conf con una clave aleatoria guardada en el llavero."""
    binary = rclone_binary()
    if not binary:
        raise RcloneError(_("rclone no está instalado"))
    st.ensure_private_dir(st.config_dir())
    conf = st.rclone_config_path()
    if not conf.exists():
        conf.touch(mode=0o600)
    proc = subprocess.run(
        [
            binary,
            "--config",
            str(conf),
            "--password-command",
            _join_command(keyring_command()),
            "config",
            "encryption",
            "set",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RcloneError(proc.stderr.strip() or _("no se pudo cifrar la configuración"))
    conf.chmod(0o600)
    cfg.config_encrypted = True


# --------------------------------------------------------------------------
# Cliente HTTP sobre socket Unix
# --------------------------------------------------------------------------


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._path = str(path)

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


class RcClient:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    def available(self) -> bool:
        return self.socket_path.exists()

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30) -> dict:
        conn = _UnixHTTPConnection(self.socket_path, timeout)
        try:
            body = json.dumps(params or {})
            conn.request("POST", "/" + method, body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", "replace")
        except OSError as exc:
            raise RcloneError(_("no se pudo hablar con rclone: {exc}", exc=exc)) from exc
        finally:
            conn.close()
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {"error": raw}
        if resp.status != 200:
            message = str(data.get("error") or raw or resp.reason)
            if looks_like_auth_error(message):
                raise AuthExpiredError(message)
            raise RcloneError(message)
        return data


# --------------------------------------------------------------------------
# Asistente de configuración (estado de rclone config)
# --------------------------------------------------------------------------


@dataclass
class ConfigStep:
    """Una pregunta que rclone hace durante la configuración."""

    state: str
    name: str
    help: str
    is_password: bool = False
    choices: list[tuple[str, str]] = field(default_factory=list)  # (valor, texto)
    error: str = ""

    @classmethod
    def from_rc(cls, out: dict) -> ConfigStep | None:
        option = out.get("Option")
        if not option:
            if out.get("Error"):
                raise RcloneError(out["Error"])
            return None
        examples = option.get("Examples") or []
        return cls(
            state=out.get("State", ""),
            name=option.get("Name", ""),
            help=option.get("Help", ""),
            is_password=bool(option.get("IsPassword")),
            choices=[(str(e.get("Value", "")), str(e.get("Help", ""))) for e in examples],
            error=out.get("Error", ""),
        )


class SetupSession:
    """`rclone rcd` temporal para crear o renovar la sesión de iCloud."""

    def __init__(self, cfg: st.Settings):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.rc = RcClient(st.setup_rc_socket())

    def __enter__(self) -> SetupSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        binary = rclone_binary()
        if not binary:
            raise RcloneError(_("rclone no está instalado"))
        st.ensure_private_dir(st.runtime_dir())
        sock = st.setup_rc_socket()
        sock.unlink(missing_ok=True)
        self.proc = subprocess.Popen(
            [
                binary,
                "rcd",
                *common_args(self.cfg),
                "--rc-addr",
                f"unix://{sock}",
                "--rc-no-auth",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise RcloneError(err.strip() or _("rclone terminó inesperadamente"))
            if sock.exists():
                try:
                    self.rc.call("rc/noop", timeout=5)
                    return
                except RcloneError:
                    pass
            time.sleep(0.2)
        self.stop()
        raise RcloneError(_("rclone no respondió a tiempo"))

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.rc.call("core/quit", timeout=5)
            except RcloneError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        st.setup_rc_socket().unlink(missing_ok=True)

    # Las llamadas a iCloud pueden tardar (Apple espera a que aceptes en el iPhone).
    _TIMEOUT = 180

    def create(self, apple_id: str, password: str) -> ConfigStep | None:
        out = self.rc.call(
            "config/create",
            {
                "name": st.REMOTE_NAME,
                "type": "iclouddrive",
                "parameters": {"apple_id": apple_id, "password": password, "service": "drive"},
                "opt": {"nonInteractive": True, "obscure": True},
            },
            timeout=self._TIMEOUT,
        )
        return ConfigStep.from_rc(out)

    def reconnect(self, password: str | None = None) -> ConfigStep | None:
        params: dict[str, str] = {}
        if password:
            params["password"] = password
        out = self.rc.call(
            "config/update",
            {
                "name": st.REMOTE_NAME,
                "parameters": params,
                "opt": {"nonInteractive": True, "obscure": bool(password)},
            },
            timeout=self._TIMEOUT,
        )
        return ConfigStep.from_rc(out)

    def answer(self, step: ConfigStep, value: str) -> ConfigStep | None:
        out = self.rc.call(
            "config/update",
            {
                "name": st.REMOTE_NAME,
                "parameters": {},
                "opt": {"continue": True, "state": step.state, "result": value},
            },
            timeout=self._TIMEOUT,
        )
        return ConfigStep.from_rc(out)

    def check_drive(self) -> None:
        """Lista la raíz de iCloud Drive para confirmar que el acceso funciona."""
        self.rc.call(
            "operations/list",
            {"fs": f"{st.REMOTE_NAME}:", "remote": "", "opt": {"recurse": False}},
            timeout=120,
        )

    def delete_remote(self) -> None:
        self.rc.call("config/delete", {"name": st.REMOTE_NAME})


# --------------------------------------------------------------------------
# Estado del montaje en marcha
# --------------------------------------------------------------------------


@dataclass
class TransferStatus:
    transferring: int = 0
    queued_uploads: int = 0
    speed: float = 0.0  # bytes/s
    errors: int = 0
    last_error: str = ""

    @property
    def busy(self) -> bool:
        return self.transferring > 0 or self.queued_uploads > 0


def mount_status(rc: RcClient) -> TransferStatus:
    stats = rc.call("core/stats", timeout=5)
    status = TransferStatus(
        transferring=len(stats.get("transferring") or []),
        speed=float(stats.get("speed") or 0),
        errors=int(stats.get("errors") or 0),
        last_error=str(stats.get("lastError") or ""),
    )
    try:
        vfs = rc.call("vfs/stats", {"fs": f"{st.REMOTE_NAME}:"}, timeout=5)
        disk = vfs.get("diskCache") or {}
        status.queued_uploads = int(disk.get("uploadsInProgress") or 0) + int(
            disk.get("uploadsQueued") or 0
        )
    except RcloneError:
        pass
    return status
