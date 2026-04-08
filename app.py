"""
Service Manager — visual launcher for local dev services.
Run: python app.py
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import gradio as gr

SERVICES_FILE = Path(__file__).parent / "services.json"
PIDS: dict[str, int] = {}   # name -> pid of launched process
LOGS: dict[str, list[str]] = {}  # name -> last N log lines


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────

def load_services() -> list[dict]:
    with open(SERVICES_FILE) as f:
        return json.load(f)


def port_in_use(port: int) -> bool:
    """Check if a port is actively listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def service_status(svc: dict) -> str:
    """Return 'running' | 'stopped' | 'unknown'."""
    name = svc["name"]
    port = svc.get("port")
    # If we launched it, check pid
    if name in PIDS and pid_running(PIDS[name]):
        return "running"
    # Fallback: check port
    if port and port_in_use(port):
        return "running"
    return "stopped"


def _stream_logs(proc: subprocess.Popen, name: str, max_lines: int = 200):
    """Background thread: collect stdout+stderr lines."""
    LOGS.setdefault(name, [])
    for raw in proc.stdout:  # type: ignore[union-attr]
        line = raw.decode("utf-8", errors="replace").rstrip()
        buf = LOGS[name]
        buf.append(line)
        if len(buf) > max_lines:
            buf.pop(0)


# ──────────────────────────────────────────────────────────────────
#  Actions
# ──────────────────────────────────────────────────────────────────

def start_service(name: str) -> str:
    services = load_services()
    svc = next((s for s in services if s["name"] == name), None)
    if not svc:
        return f"❌ Servicio '{name}' no encontrado"

    if service_status(svc) == "running":
        return f"⚠️  {name} ya está corriendo en :{svc.get('port', '?')}"

    cmd = svc["cmd"]
    cwd = svc["dir"]
    LOGS[name] = [f"▶ Iniciando: {cmd}"]
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,  # new process group so we can kill it
        )
        PIDS[name] = proc.pid
        t = threading.Thread(target=_stream_logs, args=(proc, name), daemon=True)
        t.start()
        # Wait briefly to check it didn't crash immediately
        time.sleep(1.5)
        if not pid_running(proc.pid):
            return f"❌ {name} crasheó al arrancar. Revisa los logs."
        port = svc.get("port", "")
        return f"✅ {name} iniciado (PID {proc.pid}){f'  →  :{port}' if port else ''}"
    except Exception as e:
        return f"❌ Error al iniciar {name}: {e}"


def stop_service(name: str) -> str:
    services = load_services()
    svc = next((s for s in services if s["name"] == name), None)
    if not svc:
        return f"❌ Servicio '{name}' no encontrado"

    # Kill by pid if we have it
    if name in PIDS:
        pid = PIDS.pop(name)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(0.5)
            if pid_running(pid):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            return f"🛑 {name} detenido (PID {pid})"
        except ProcessLookupError:
            return f"🛑 {name} ya estaba detenido"
        except Exception as e:
            return f"⚠️  Error al detener {name}: {e}"

    # Kill by port as fallback
    port = svc.get("port")
    if port and port_in_use(port):
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True
            )
            pids = [int(p) for p in result.stdout.strip().split() if p]
            if not pids:
                return f"⚠️  No se encontró proceso en :{port}"
            for p in pids:
                try:
                    os.kill(p, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            time.sleep(1)
            # Force kill any that survived SIGTERM
            still_alive = [p for p in pids if pid_running(p)]
            for p in still_alive:
                try:
                    os.kill(p, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return f"🛑 {name} detenido (puerto :{port}, PIDs: {pids})"
        except Exception as e:
            return f"⚠️  Error matando :{port}: {e}"

    return f"⚪ {name} no estaba corriendo"


def get_logs(name: str) -> str:
    lines = LOGS.get(name, ["(sin logs)"])
    return "\n".join(lines[-100:])


# ──────────────────────────────────────────────────────────────────
#  Dashboard state (refreshed on poll)
# ──────────────────────────────────────────────────────────────────

def build_status_html() -> str:
    services = load_services()
    groups: dict[str, list[dict]] = {}
    for s in services:
        groups.setdefault(s.get("group", "Other"), []).append(s)

    rows = []
    for group, svcs in groups.items():
        rows.append(f'<div class="grp-label">{group}</div>')
        for s in svcs:
            status = service_status(s)
            dot = "🟢" if status == "running" else "🔴"
            port_badge = f'<span class="port">:{s["port"]}</span>' if s.get("port") else ""
            url_btn = (
                f'<a href="{s["url"]}" target="_blank" class="open-btn">Abrir ↗</a>'
                if s.get("url") else ""
            )
            color = s.get("color", "#6b7280")
            rows.append(f"""
<div class="svc-row">
  <span class="dot">{dot}</span>
  <span class="svc-name" style="border-left:3px solid {color};padding-left:6px">{s['name']}</span>
  {port_badge}
  <span class="svc-status {"status-up" if status == "running" else "status-dn"}">{status}</span>
  {url_btn}
</div>""")
    return "\n".join(rows)


CSS = """
body { font-family: system-ui, sans-serif; }
.svc-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 8px; margin: 4px 0;
  background: #1e1e2e; border: 1px solid #2d2d3f;
}
.grp-label {
  font-size: 11px; font-weight: 600; letter-spacing: 1px;
  color: #6b7280; text-transform: uppercase;
  margin: 14px 0 4px 4px;
}
.svc-name { flex: 1; font-weight: 500; color: #e2e8f0; font-size: 14px; }
.port { font-size: 12px; color: #94a3b8; font-family: monospace;
        background: #2d2d3f; padding: 2px 6px; border-radius: 4px; }
.status-up { color: #4ade80; font-size: 12px; font-weight: 600; }
.status-dn { color: #f87171; font-size: 12px; }
.open-btn {
  font-size: 12px; color: #818cf8; text-decoration: none;
  padding: 2px 8px; border-radius: 4px; border: 1px solid #3730a3;
}
.open-btn:hover { background: #1e1b4b; }
.dot { font-size: 12px; }
"""


# ──────────────────────────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────────────────────────

def service_names() -> list[str]:
    return [s["name"] for s in load_services()]


with gr.Blocks(title="Service Manager", css=CSS, theme=gr.themes.Base()) as demo:
    gr.Markdown("# ⚡ Service Manager\nGestiona tus servicios de desarrollo locales.")

    with gr.Row():
        with gr.Column(scale=2):
            status_html = gr.HTML(build_status_html, label="Estado")
            refresh_btn = gr.Button("🔄 Refrescar", size="sm", variant="secondary")
        with gr.Column(scale=1):
            svc_select = gr.Dropdown(
                label="Servicio",
                choices=service_names(),
                value=service_names()[0] if service_names() else None,
            )
            with gr.Row():
                btn_start = gr.Button("▶ Iniciar", variant="primary")
                btn_stop = gr.Button("■ Detener", variant="stop")
            action_out = gr.Textbox(label="Resultado", lines=2, interactive=False)
            log_out = gr.Textbox(label="Logs (últimas 100 líneas)", lines=12, interactive=False)
            btn_logs = gr.Button("📄 Ver logs", size="sm")

    # Wiring
    def refresh_all():
        names = service_names()
        return build_status_html(), gr.update(choices=names, value=names[0] if names else None)

    refresh_btn.click(fn=refresh_all, outputs=[status_html, svc_select])

    def do_start(name):
        msg = start_service(name)
        return msg, build_status_html()

    def do_stop(name):
        msg = stop_service(name)
        return msg, build_status_html()

    btn_start.click(fn=do_start, inputs=svc_select, outputs=[action_out, status_html])
    btn_stop.click(fn=do_stop, inputs=svc_select, outputs=[action_out, status_html])
    btn_logs.click(fn=get_logs, inputs=svc_select, outputs=log_out)

    # Auto-refresh every 5s — también refresca el dropdown
    demo.load(fn=refresh_all, outputs=[status_html, svc_select], every=5)


if __name__ == "__main__":
    port = int(os.environ.get("SM_PORT", 9000))
    share = os.environ.get("SM_SHARE", "false").lower() == "true"
    demo.launch(server_port=port, share=share)
