"""`nimbo-edit-copy`: copia fotos a iCloud Drive y las abre para editarlas.

iCloud Fotos es de solo lectura. Este comando (que se llama desde el menú
del clic derecho de Dolphin o Nautilus) copia los archivos elegidos a
``~/iCloud/Fotos editadas/`` y los abre en el editor. Al guardar, la versión
editada se sube sola a iCloud Drive. El original no se toca.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import i18n
from . import settings as st
from .i18n import _


def unique_path(folder: Path, name: str) -> Path:
    """``folder/name``, o ``folder/nombre (2).ext`` si ya existe."""
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


def notify(title: str, body: str, error: bool = False) -> None:
    if shutil.which("notify-send"):
        icon = "dialog-error" if error else "nimbo"
        subprocess.run(["notify-send", "-a", "Nimbo", "-i", icon, title, body], check=False)
    else:
        print(f"{title}: {body}", file=sys.stderr if error else sys.stdout)


def open_files(paths: list[Path], editor: str) -> None:
    if editor.strip():
        cmd = [*shlex.split(editor), *map(str, paths)]
        subprocess.Popen(cmd, start_new_session=True)
        return
    for path in paths:
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)


def copy_for_editing(files: list[Path], cfg: st.Settings) -> list[Path]:
    """Copia los archivos a la carpeta de editadas. Devuelve las copias."""
    drive = Path(cfg.mount_point).expanduser()
    # Si iCloud Drive no está montado, la copia caería en la carpeta vacía de
    # debajo y luego impediría montar. Mejor avisar.
    if not os.path.ismount(drive):
        raise RuntimeError(_("iCloud Drive no está conectado. Reanuda la sincronización "
                             "desde el icono de Nimbo e inténtalo otra vez."))
    folder = drive / cfg.edited_subfolder
    folder.mkdir(parents=True, exist_ok=True)
    copies = []
    for src in files:
        if not src.is_file():
            continue
        target = unique_path(folder, src.name)
        shutil.copy2(src, target)
        copies.append(target)
    return copies


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cfg = st.Settings.load()
    i18n.set_language(cfg.language)
    files = [Path(a).expanduser().resolve() for a in args if not a.startswith("-")]
    if not files:
        print(_("Uso: nimbo-edit-copy ARCHIVO…"), file=sys.stderr)
        return 2
    try:
        copies = copy_for_editing(files, cfg)
    except (OSError, RuntimeError) as exc:
        notify(_("No se pudo copiar"), str(exc), error=True)
        return 1
    if not copies:
        return 1
    folder = copies[0].parent
    notify(_("Copia lista para editar"),
           _("Se guardó en {folder}. Al guardar los cambios se subirán a iCloud Drive.",
             folder=str(folder).replace(str(Path.home()), "~")))
    open_files(copies, cfg.photo_editor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
