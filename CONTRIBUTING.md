# Cómo contribuir

¡Gracias por querer ayudar! Puedes contribuir en español o en inglés.

1. Abre un *issue* para hablar de cambios grandes antes de programarlos.
2. Haz un *fork*, crea una rama y envía un *pull request*.
3. Antes de enviarlo, ejecuta:
   ```bash
   ruff check .
   QT_QPA_PLATFORM=offscreen pytest
   ```
4. Los textos de la interfaz se escriben en español con `_("...")`. Añade la traducción al inglés en `src/nimbo/i18n.py`. Si falta alguna, la prueba `test_every_ui_string_has_english` falla.

### Traducciones a otros idiomas

Para añadir, por ejemplo, portugués:

1. En `src/nimbo/i18n.py`, crea un diccionario `_PT` con el mismo formato que `_EN` (texto en español → traducción).
2. Regístralo en `_CATALOGS = {"en": _EN, "pt": _PT}` y en `LANGUAGES` (`"pt": "Português"`).
3. Aparecerá solo en Preferencias → Idioma.

Reglas de seguridad para cualquier cambio:

- Nunca pases credenciales como argumentos de un proceso.
- Nunca escribas credenciales en el registro.
- No añadas conexiones a servidores que no sean de Apple.
- No uses logotipos ni elementos gráficos de Apple.

Ideas pendientes: iconos de estado por archivo en Dolphin y Nautilus, carpetas "siempre disponibles sin conexión", iCloud Fotos, paquete en el AUR y Flatpak.
