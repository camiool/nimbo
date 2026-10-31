"""Traducción mínima: los textos se escriben en español y se traducen al
inglés si el sistema no está en español. Para añadir un idioma, agrega un
diccionario a `_CATALOGS`."""

from __future__ import annotations

import locale
import os

_EN = {
    "Abrir carpeta de iCloud": "Open iCloud folder",
    "Pausar sincronización": "Pause sync",
    "Reanudar sincronización": "Resume sync",
    "Volver a iniciar sesión…": "Sign in again…",
    "Iniciar sesión en iCloud…": "Sign in to iCloud…",
    "Preferencias…": "Preferences…",
    "Ver registro": "Show log",
    "Acerca de Nimbo": "About Nimbo",
    "Salir": "Quit",
    "Conectado": "Connected",
    "Conectando…": "Connecting…",
    "En pausa": "Paused",
    "Sin configurar": "Not set up",
    "Error": "Error",
    "Hay que volver a iniciar sesión": "You need to sign in again",
    "Sincronizando {n} archivo(s) · {speed}": "Syncing {n} file(s) · {speed}",
    "Tu sesión de iCloud caducó": "Your iCloud session expired",
    "Apple pide verificar tu identidad cada cierto tiempo. Haz clic para "
    "introducir el código.": "Apple asks you to verify your identity "
    "periodically. Click to enter the code.",
    "No se pudo montar iCloud Drive": "Could not mount iCloud Drive",
    "Revisa el registro para más detalles.": "Check the log for details.",
    "Iniciar sesión en iCloud": "Sign in to iCloud",
    "Antes de empezar": "Before you start",
    "Para que Nimbo pueda acceder a tu iCloud Drive, comprueba esto en tu "
    "iPhone, iPad o Mac:": "For Nimbo to reach your iCloud Drive, check the "
    "following on your iPhone, iPad or Mac:",
    "<b>Protección de datos avanzada</b> debe estar <b>desactivada</b>.":
    "<b>Advanced Data Protection</b> must be <b>turned off</b>.",
    "<b>Acceder a datos de iCloud en la web</b> debe estar <b>activado</b> "
    "(Ajustes → tu nombre → iCloud).": "<b>Access iCloud Data on the Web</b> "
    "must be <b>on</b> (Settings → your name → iCloud).",
    "Tu contraseña viaja solo entre este equipo y Apple. Se guarda en este "
    "equipo cifrada con una clave que vive en el llavero del sistema.":
    "Your password only travels between this computer and Apple. It is stored "
    "on this computer, encrypted with a key kept in the system keyring.",
    "Apple ID (correo)": "Apple ID (email)",
    "Contraseña": "Password",
    "Contraseña (déjala vacía si no la has cambiado)":
    "Password (leave empty if unchanged)",
    "Siguiente": "Next",
    "Cancelar": "Cancel",
    "Enviar": "Submit",
    "Enviar código por SMS": "Send code by SMS",
    "Terminar": "Finish",
    "Hablando con Apple…": "Talking to Apple…",
    "Revisa tu iPhone, iPad o Mac: Apple te mostrará un código de 6 dígitos.":
    "Check your iPhone, iPad or Mac: Apple will show you a 6-digit code.",
    "Código de verificación": "Verification code",
    "Introduce el código que recibiste por SMS.": "Enter the code you received by SMS.",
    "Elige el teléfono al que enviar el SMS.": "Choose the phone to send the SMS to.",
    "Comprobando el acceso a iCloud Drive…": "Checking access to iCloud Drive…",
    "¡Listo!": "All set!",
    "Tus archivos de iCloud Drive aparecerán en:": "Your iCloud Drive files will appear in:",
    "Carpeta de iCloud": "iCloud folder",
    "Elegir…": "Choose…",
    "Espacio máximo para la caché local": "Maximum space for local cache",
    "Iniciar Nimbo al iniciar sesión": "Start Nimbo at login",
    "Guardar": "Save",
    "Cerrar sesión en iCloud": "Sign out of iCloud",
    "¿Cerrar sesión? La carpeta se desmontará y se borrarán las credenciales "
    "y la caché de este equipo. Tus archivos en iCloud no se tocan.":
    "Sign out? The folder will be unmounted and credentials and cache on this "
    "computer will be deleted. Your files in iCloud are not touched.",
    "Falta rclone": "rclone is missing",
    "Nimbo necesita rclone {min} o más nuevo. Instálalo con:":
    "Nimbo needs rclone {min} or newer. Install it with:",
    "No hay llavero disponible": "No keyring available",
    "No se encontró secret-tool (paquete libsecret). La configuración se "
    "guardará sin cifrar (solo legible por tu usuario). ¿Continuar?":
    "secret-tool (libsecret package) was not found. The configuration will be "
    "stored unencrypted (readable only by your user). Continue?",
    "La carpeta elegida no está vacía. Elige una carpeta vacía o nueva.":
    "The chosen folder is not empty. Pick an empty or new folder.",
    "Cliente libre de iCloud Drive para Linux.": "Free iCloud Drive client for Linux.",
    "Nimbo no está afiliado a Apple. iCloud es una marca de Apple Inc.":
    "Nimbo is not affiliated with Apple. iCloud is a trademark of Apple Inc.",
    "Registro de Nimbo": "Nimbo log",
    "Cerrar": "Close",
    "No hay bandeja del sistema disponible.": "No system tray available.",
}

_CATALOGS = {"en": _EN}


def _detect() -> str:
    for var in ("NIMBO_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return value.split(":")[0][:2].lower()
    lang = locale.getlocale()[0] or ""
    return lang[:2].lower()


_LANG = _detect()
# El español es el idioma base; cualquier idioma sin catálogo usa inglés.
_CATALOG = {} if _LANG == "es" else _CATALOGS.get(_LANG, _EN)


def _(text: str, **kwargs: object) -> str:
    translated = _CATALOG.get(text, text)
    return translated.format(**kwargs) if kwargs else translated
