"""Calcula el estado de Nimbo (sin interfaz gráfica, para poder probarlo)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from . import rclone, service
from . import settings as st


class Status(Enum):
    UNCONFIGURED = "unconfigured"
    CONNECTING = "connecting"
    OK = "ok"
    SYNCING = "syncing"
    PAUSED = "paused"
    AUTH = "auth"
    ERROR = "error"


@dataclass
class Snapshot:
    status: Status
    transfers: rclone.TransferStatus | None = None
    detail: str = ""


# Cada cuánto se comprueba de verdad que la sesión de Apple sigue viva.
HEALTH_INTERVAL = 15 * 60


class StatusProbe:
    def __init__(self) -> None:
        self.rc = rclone.RcClient(st.mount_rc_socket())
        self._last_health: float | None = None  # None = comprobar ya

    def poll(self, cfg: st.Settings) -> Snapshot:
        if not cfg.is_configured:
            return Snapshot(Status.UNCONFIGURED)

        state = service.state()
        if state in ("activating", "reloading"):
            return Snapshot(Status.CONNECTING)
        if state == "failed":
            if service.failed_because_of_auth():
                return Snapshot(Status.AUTH)
            return Snapshot(Status.ERROR, detail=service.recent_log(5).strip())
        if state != "active":
            return Snapshot(Status.PAUSED)

        try:
            transfers = rclone.mount_status(self.rc)
            if not transfers.busy and (
                self._last_health is None
                or time.monotonic() - self._last_health > HEALTH_INTERVAL
            ):
                self._last_health = time.monotonic()
                self.rc.call(
                    "operations/list",
                    {"fs": f"{st.REMOTE_NAME}:", "remote": ""},
                    timeout=60,
                )
        except rclone.AuthExpiredError as exc:
            return Snapshot(Status.AUTH, detail=str(exc))
        except rclone.RcloneError as exc:
            return Snapshot(Status.CONNECTING, detail=str(exc))

        if rclone.looks_like_auth_error(transfers.last_error):
            return Snapshot(Status.AUTH, transfers, transfers.last_error)
        return Snapshot(Status.SYNCING if transfers.busy else Status.OK, transfers)

    def force_health_check(self) -> None:
        self._last_health = None
