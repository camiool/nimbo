# Seguridad

## Cómo reportar una vulnerabilidad

No abras un *issue* público. Usa **Security → Report a vulnerability** en GitHub (avisos privados) para escribir a quien mantiene el proyecto. Intentaremos responder en un plazo de 7 días.

## Modelo de seguridad

| Dato | Dónde vive | Protección |
|---|---|---|
| Contraseña de Apple (ofuscada por rclone) y token de sesión | `~/.config/nimbo/rclone.conf` | Archivo cifrado por rclone con una clave aleatoria; permisos `0600` |
| Clave de cifrado de la configuración | Llavero del sistema (libsecret) | La gestiona KWallet o GNOME Keyring |
| Socket de control de rclone | `$XDG_RUNTIME_DIR/nimbo/` | Carpeta `0700`: solo la usa tu usuario |
| Archivos en caché (Drive y Fotos) | `~/.cache/nimbo/drive`, `~/.cache/nimbo/photos` | Carpetas `0700` |

Qué protege:

- Copias de seguridad, sincronizaciones o capturas de `~/.config` que lleguen a terceros: el archivo de configuración está cifrado.
- Otros usuarios del mismo equipo: no pueden leer los archivos ni usar el socket.
- La contraseña nunca aparece en argumentos de procesos (`ps`) ni en el registro.

Qué no protege:

- Malware que se ejecute **con tu propio usuario** mientras tu llavero está desbloqueado. Esto pasa con cualquier cliente de sincronización.
- La API de iCloud que usa rclone no es pública. Apple podría cambiarla o restringirla.

Nimbo no tiene servidores ni telemetría. Solo se conecta a Apple, a través de rclone.
