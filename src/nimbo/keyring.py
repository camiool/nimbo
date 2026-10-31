"""Clave de cifrado de rclone.conf guardada en el llavero del sistema.

Se usa libsecret (`secret-tool`), que funciona con KWallet (Plasma 6) y con
GNOME Keyring. rclone llama a `nimbo-keyring` mediante `--password-command`
cada vez que necesita abrir su archivo de configuración, así que la clave
nunca se escribe en disco ni aparece en la línea de comandos.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys

_ATTRS = ["application", "nimbo", "purpose", "rclone-config"]
_LABEL = "Nimbo: clave de la configuración de iCloud"


def available() -> bool:
    return shutil.which("secret-tool") is not None


def lookup() -> str | None:
    if not available():
        return None
    proc = subprocess.run(
        ["secret-tool", "lookup", *_ATTRS],
        capture_output=True,
        text=True,
        check=False,
    )
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def store(value: str) -> None:
    subprocess.run(
        ["secret-tool", "store", f"--label={_LABEL}", *_ATTRS],
        input=value,
        text=True,
        check=True,
        capture_output=True,
    )


def clear() -> None:
    if available():
        subprocess.run(["secret-tool", "clear", *_ATTRS], check=False, capture_output=True)


def get_or_create() -> str:
    value = lookup()
    if value is None:
        value = secrets.token_urlsafe(32)
        store(value)
        if lookup() != value:
            raise RuntimeError("el llavero no guardó la clave")
    return value


def main() -> int:
    """Punto de entrada de `nimbo-keyring` (lo invoca rclone)."""
    try:
        # rclone define RCLONE_PASSWORD_CHANGE=1 cuando está cifrando por
        # primera vez o cambiando la clave: solo entonces la generamos.
        if os.environ.get("RCLONE_PASSWORD_CHANGE") == "1":
            value = get_or_create()
        else:
            value = lookup()
        if not value:
            print("nimbo-keyring: no hay clave en el llavero", file=sys.stderr)
            return 1
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f"nimbo-keyring: {exc}", file=sys.stderr)
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
