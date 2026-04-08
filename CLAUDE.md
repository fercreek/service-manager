# Service Manager — contexto para Claude Code

## Qué es este proyecto

Gestor local de servicios de desarrollo para macOS. Dos interfaces:
- **Menu bar app** (`menubar.py`) — ícono ⚡ en la barra superior, nativa AppKit/PyObjC
- **Web UI** (`app.py`) — dashboard Gradio en `http://localhost:9000`

## Cómo iniciar

```bash
# Menu bar app (recomendado)
.venv/bin/python menubar.py

# Web UI
./run.sh
```

## Arquitectura

| Archivo | Rol |
|---------|-----|
| `menubar.py` | App de barra de menú (AppKit puro, sin rumps). NSStatusItem + NSMenu. |
| `app.py` | Web UI con Gradio. Inicia/detiene servicios, muestra logs en tiempo real. |
| `services.json` | Config local de servicios (gitignoreado). Copiar de `services.example.json`. |
| `ServiceManager.app` | Wrapper `.app` para lanzar `menubar.py` con doble click desde Finder. |
| `run.sh` | Launcher de la Web UI. Crea `.venv` si no existe. |

## Decisiones técnicas importantes

- **No uses rumps** — rumps 0.4.0 no responde a clicks en macOS Sequoia. `menubar.py` usa AppKit directamente via PyObjC.
- **pyobjc debe ser `<12`** — pyobjc 12.x no compila con Python 3.9. Usar `pyobjc-core<12` y `pyobjc-framework-Cocoa<12`.
- **services.json es privado** — contiene rutas locales. Está en `.gitignore`. Nunca commitear.
- El stop de servicios funciona por puerto (lsof) aunque el manager no los haya iniciado.
- El auto-refresh del menú actualiza solo los **títulos** de los items — no reconstruye el menú, para no interferir con clicks activos.

## Dependencias

```
gradio==4.36.0
pyobjc-core<12
pyobjc-framework-Cocoa<12
rumps>=0.4.0   # instalado pero NO usado en menubar.py
```

## Comandos útiles

```bash
# Instalar dependencias
.venv/bin/pip install -r requirements.txt

# Ver si el menubar está corriendo
pgrep -af "python.*menubar"

# Matar instancias huérfanas
pkill -9 -f "python.*menubar"

# Ver logs del menubar
tail -f /tmp/menubar.log
```

## Repo

https://github.com/fercreek/service-manager
