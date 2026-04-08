# ⚡ Service Manager

Gestor local de servicios de desarrollo para macOS. Levanta y tumba apps, bases de datos y servidores desde la barra superior del sistema — sin tocar la terminal.

## Interfaces

### Menu bar app (recomendado)

Aparece como `⚡` en la barra superior de macOS. Click para ver el estado de cada servicio con submenú de inicio/parada y link para abrir en browser.

```bash
.venv/bin/python menubar.py
```

O abre directamente `ServiceManager.app` desde Finder.

### Web UI (Gradio)

Dashboard en el browser con estado en tiempo real, botones de inicio/parada y logs.

```bash
./run.sh
# → http://localhost:9000
```

## Instalación

```bash
cd ~/Documents/service-manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Agregar un servicio

Edita `services.json`:

```json
{
  "name": "Mi App",
  "group": "Apps",
  "dir": "/Users/tu-usuario/Documents/mi-app",
  "cmd": "npm run dev",
  "port": 3000,
  "url": "http://localhost:3000",
  "color": "#dc2626"
}
```

| Campo   | Descripción |
|---------|-------------|
| `name`  | Nombre visible |
| `group` | Grupo (`Apps`, `Infrastructure`, etc.) |
| `dir`   | Directorio de trabajo del comando |
| `cmd`   | Comando de arranque (como en terminal) |
| `port`  | Puerto para detectar si está corriendo |
| `url`   | URL para "Abrir en browser" (`null` si no aplica) |
| `color` | Color del borde en la Web UI |

El servicio detecta si ya está corriendo por puerto, incluso si no fue iniciado desde el manager — y puede detenerlo igual.

## Configuración

Crea un `.env` en la raíz (ver `.env.example`):

```env
SM_PORT=9000     # Puerto de la Web UI
SM_SHARE=false   # true = expone en red local
```

## Estructura

```
service-manager/
├── menubar.py        # Menu bar app (AppKit nativo)
├── app.py            # Web UI (Gradio)
├── services.json     # Servicios registrados
├── requirements.txt  # Dependencias Python
├── run.sh            # Launcher de la Web UI
├── ServiceManager.app/  # Wrapper .app para doble click
└── .env.example      # Plantilla de variables de entorno
```

## Requisitos

- macOS 13+
- Python 3.9+
- pyobjc 11.x (para el menu bar app)
