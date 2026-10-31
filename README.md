# Nimbo

**iCloud Drive como una carpeta más en Linux.** Nimbo pone un icono en la bandeja del sistema, te guía para iniciar sesión con tu Apple ID y el código 2FA, y monta tu iCloud Drive en `~/iCloud`. Desde ahí lo usas con Dolphin, Nautilus o cualquier programa, como en macOS.

*English summary below.*

<p align="center">
  <img src="docs/2-inicio-sesion.png" width="45%" alt="Inicio de sesión">
  <img src="docs/3-codigo-2fa.png" width="45%" alt="Código 2FA">
</p>

> Nimbo es un proyecto independiente y no está afiliado a Apple. iCloud es una marca de Apple Inc.

## Qué hace

- **Carpeta montada:** ves todos tus archivos sin descargarlos. Un archivo se descarga cuando lo abres y lo que guardas se sube solo, como con "Optimizar almacenamiento" en el Mac.
- **Caché local con límite:** los archivos que usas quedan disponibles al instante. Tú eliges cuánto espacio ocupa (10 GB por defecto).
- **Icono de estado:** verde si está conectado, azul si está sincronizando, naranja si hay que volver a iniciar sesión, rojo si hay un error.
- **Aviso de sesión caducada:** Apple pide repetir el 2FA más o menos cada 30 días. Nimbo te avisa y te pide el código en una ventana, sin terminal.
- **Se monta al arrancar** mediante un servicio de usuario de systemd, aunque cierres la app.
- Interfaz en español y en inglés.

Por debajo usa el módulo `iclouddrive` de [rclone](https://rclone.org/iclouddrive/), que es el que habla con Apple. Nimbo añade la interfaz, la gestión de la sesión y la parte de seguridad.

## Requisitos

En tu cuenta de Apple (en el iPhone: Ajustes → tu nombre → iCloud):

1. **Protección de datos avanzada desactivada.** Con ella activa, Apple no permite el acceso desde fuera de sus dispositivos.
2. **"Acceder a datos de iCloud en la web" activado.**

En el PC: Linux con systemd, FUSE 3, rclone 1.70 o más nuevo (se recomienda la última versión), Python 3.10 o más nuevo, PySide6 y libsecret (`secret-tool`).

## Instalación

### CachyOS, Arch y derivados

```bash
sudo pacman -S --needed git base-devel
git clone https://github.com/USUARIO/nimbo.git
cd nimbo/packaging/arch
makepkg -si
```

Después abre **Nimbo** desde el menú de aplicaciones.

### Otras distribuciones

Instala `rclone`, `fuse3`, `libsecret` y PySide6 con tu gestor de paquetes. Luego:

```bash
pipx install git+https://github.com/USUARIO/nimbo.git
```

## Uso

1. Abre Nimbo. La primera vez se abre el asistente: Apple ID, contraseña y el código de 6 dígitos que aparece en tu iPhone, iPad o Mac (también puedes pedirlo por SMS).
2. Elige la carpeta (por defecto `~/iCloud`) y el tamaño de la caché.
3. Listo. Haz clic en el icono de la bandeja para abrir la carpeta.

Cuando Apple pida verificar otra vez, el icono se pone naranja y aparece una notificación. Haz clic en ella e introduce el código.

## Seguridad y privacidad

- **Sin servidores intermedios.** Tu equipo habla directamente con Apple. Nimbo no envía nada a nadie más.
- **La contraseña nunca va en la línea de comandos.** Los programas que corren en el equipo pueden ver la línea de comandos con `ps`. Nimbo arranca `rclone rcd` en un socket Unix privado (`$XDG_RUNTIME_DIR/nimbo`, permisos `0700`) y le envía las credenciales por ahí.
- **Configuración cifrada.** rclone guarda la sesión (y la contraseña ofuscada) en `~/.config/nimbo/rclone.conf`. Nimbo cifra ese archivo con una clave aleatoria que vive en el llavero del sistema (KWallet o GNOME Keyring, a través de libsecret). Si no hay llavero, avisa antes de guardarlo sin cifrar, con permisos `0600`.
- **Cerrar sesión** (en Preferencias) desmonta la carpeta y borra la configuración, la clave del llavero y la caché local. Tus archivos en iCloud no se tocan.

Ver también [SECURITY.md](SECURITY.md).

## Limitaciones conocidas

- Los cambios hechos desde otros dispositivos tardan alrededor de un minuto en aparecer. No hay notificaciones instantáneas.
- Aún no hay iconos de estado por archivo (nube o check) en el explorador.
- No incluye iCloud Fotos, Contactos ni Calendario.
- La API que usa rclone no es oficial. Si Apple la cambia, puede dejar de funcionar hasta que rclone se actualice. Mantén rclone al día.

## Cómo funciona

```
 Bandeja (PySide6) ──► systemctl --user ──► nimbo-mount.service
       │                                        │
       │ socket Unix (estado: subidas, errores)  ▼
       └──────────────────────────────► rclone mount icloud: ~/iCloud
                                                │  --password-command nimbo-keyring
                                                ▼
                                          API de iCloud (Apple)
```

| Archivo | Qué hace |
|---|---|
| `src/nimbo/rclone.py` | Habla con rclone por socket Unix: alta, 2FA y estado |
| `src/nimbo/service.py` | Genera y controla el servicio de systemd |
| `src/nimbo/keyring.py` | `nimbo-keyring`: entrega a rclone la clave del llavero |
| `src/nimbo/status.py` | Calcula el estado (conectado, sincronizando, sesión caducada…) |
| `src/nimbo/gui/` | Bandeja, asistente y preferencias |

## Desarrollo

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen pytest
ruff check .
python -m nimbo
```

Las contribuciones son bienvenidas. Lee [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

[GPL-3.0-or-later](LICENSE). Nimbo es software libre: puedes usarlo, estudiarlo, modificarlo y compartirlo.

---

## English summary

Nimbo is a free (GPL-3.0) tray app that mounts **iCloud Drive as a regular folder on Linux**, similar to macOS. It is built on rclone's `iclouddrive` backend. It handles sign-in and 2FA through a GUI, runs the mount as a systemd user service with a capped VFS cache, and warns you when Apple's session expires (about every 30 days) so you can re-enter the code. The rclone config is encrypted with a random key stored in the system keyring via libsecret, and credentials are never passed on the command line. Requirements: Advanced Data Protection off, "Access iCloud Data on the Web" on, rclone ≥ 1.70. Install on Arch/CachyOS with `cd packaging/arch && makepkg -si`. Not affiliated with Apple.
