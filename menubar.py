#!/usr/bin/env python3
"""
Service Manager — macOS menu bar app (raw AppKit, no rumps).
"""
import json
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import objc
from AppKit import (
    NSApplication, NSStatusBar, NSMenu, NSMenuItem, NSObject,
    NSVariableStatusItemLength, NSImage,
)
from Foundation import NSTimer, NSRunLoop
from PyObjCTools import AppHelper

SERVICES_FILE = Path(__file__).parent / "services.json"
PIDS: dict[str, int] = {}


# ── helpers ────────────────────────────────────────────────────────

def load_services() -> list[dict]:
    with open(SERVICES_FILE) as f:
        return json.load(f)


def port_in_use(port: int) -> bool:
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
    name = svc["name"]
    port = svc.get("port")
    if name in PIDS and pid_running(PIDS[name]):
        return "running"
    if port and port_in_use(port):
        return "running"
    return "stopped"


def do_start(name: str):
    services = load_services()
    svc = next((s for s in services if s["name"] == name), None)
    if not svc or service_status(svc) == "running":
        return
    proc = subprocess.Popen(
        svc["cmd"], shell=True, cwd=svc["dir"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    PIDS[name] = proc.pid


def do_stop(name: str):
    services = load_services()
    svc = next((s for s in services if s["name"] == name), None)
    if not svc:
        return
    if name in PIDS:
        pid = PIDS.pop(name)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(0.5)
            if pid_running(pid):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            return
        except ProcessLookupError:
            pass
    port = svc.get("port")
    if port and port_in_use(port):
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = [int(p) for p in result.stdout.strip().split() if p]
        for p in pids:
            try:
                os.kill(p, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1)
        for p in pids:
            if pid_running(p):
                try:
                    os.kill(p, signal.SIGKILL)
                except ProcessLookupError:
                    pass


# ── AppKit delegate ────────────────────────────────────────────────

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, notification):
        self._services = load_services()
        self._parent_items: dict[str, NSMenuItem] = {}

        # Status bar item
        self._status_item = (
            NSStatusBar.systemStatusBar()
            .statusItemWithLength_(NSVariableStatusItemLength)
        )
        self._status_item.button().setTitle_("⚡")

        # Build & attach menu
        self._menu = self._build_menu()
        self._status_item.setMenu_(self._menu)

        # Auto-refresh every 5s
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0, self, "refreshTitles:", None, True
        )

    # ── menu builder ──────────────────────────────────────────────

    def _build_menu(self) -> NSMenu:
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        prev_group = None

        for svc in self._services:
            group = svc.get("group", "Other")
            if group != prev_group:
                if prev_group is not None:
                    menu.addItem_(NSMenuItem.separatorItem())
                header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    group.upper(), None, ""
                )
                header.setEnabled_(False)
                menu.addItem_(header)
                prev_group = group

            name = svc["name"]
            port = svc.get("port", "")
            url = svc.get("url")
            status = service_status(svc)
            dot = "●" if status == "running" else "○"
            label = f"{dot}  {name}" + (f"  :{port}" if port else "")

            # Parent item — opens submenu
            parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, None, ""
            )
            submenu = NSMenu.alloc().init()
            submenu.setAutoenablesItems_(False)

            start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "▶  Iniciar", "startService:", ""
            )
            start_item.setTarget_(self)
            start_item.setRepresentedObject_(name)
            submenu.addItem_(start_item)

            stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "■  Detener", "stopService:", ""
            )
            stop_item.setTarget_(self)
            stop_item.setRepresentedObject_(name)
            submenu.addItem_(stop_item)

            if url:
                open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "↗  Abrir en browser", "openService:", ""
                )
                open_item.setTarget_(self)
                open_item.setRepresentedObject_(url)
                submenu.addItem_(open_item)

            parent.setSubmenu_(submenu)
            menu.addItem_(parent)
            self._parent_items[name] = parent

        menu.addItem_(NSMenuItem.separatorItem())

        refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "🔄  Refrescar", "refreshTitles:", ""
        )
        refresh_item.setTarget_(self)
        menu.addItem_(refresh_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Salir", "quitApp:", ""
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        return menu

    # ── actions ───────────────────────────────────────────────────

    def startService_(self, sender):
        name = sender.representedObject()
        threading.Thread(target=do_start, args=(name,), daemon=True).start()

    def stopService_(self, sender):
        name = sender.representedObject()
        threading.Thread(target=do_stop, args=(name,), daemon=True).start()

    def openService_(self, sender):
        url = sender.representedObject()
        subprocess.run(["open", url])

    def refreshTitles_(self, sender):
        for svc in self._services:
            name = svc["name"]
            item = self._parent_items.get(name)
            if item is None:
                continue
            status = service_status(svc)
            dot = "●" if status == "running" else "○"
            port = svc.get("port", "")
            label = f"{dot}  {name}" + (f"  :{port}" if port else "")
            item.setTitle_(label)

    def quitApp_(self, sender):
        NSApplication.sharedApplication().terminate_(None)


# ── entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import fcntl
    lock_fd = open("/tmp/service-manager-menubar.lock", "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(0)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    AppHelper.runEventLoop()
