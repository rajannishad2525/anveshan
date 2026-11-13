"""ANVESHAN desktop launcher: native window, no terminal, no browser.

Starts the FastAPI app on a loopback ephemeral port inside this process,
then shows it in a WebView2 window. Closing the window stops everything.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# EdgeUpdate's product code for the WebView2 Runtime.
WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def alert(title: str, text: str) -> None:
    """There is no console, and WebView2 may itself be the thing that is
    missing, so an OS dialog is the only channel left."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR


def webview2_version() -> str | None:
    """None means the runtime is absent. pywebview does not raise in that
    case -- it logs to stderr and hangs -- so we have to check first."""
    import winreg

    for hive, path in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + "\\" + WEBVIEW2_CLIENT),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE" + "\\" + WEBVIEW2_CLIENT),
        (winreg.HKEY_CURRENT_USER, "SOFTWARE" + "\\" + WEBVIEW2_CLIENT),
    ):
        try:
            with winreg.OpenKey(hive, path) as key:
                version = winreg.QueryValueEx(key, "pv")[0]
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return version
    return None


WINDOW_TITLE = "ANVESHAN - Offline Analyst Workstation"


def claim_single_instance(name: str = r"Local\ANVESHAN-single-instance") -> bool:
    """False if ANVESHAN is already running. Two instances would open two
    servers over one SQLite archive, and a double-click is easy to do."""
    import ctypes

    # Local\ not Global\: each Windows session has its own archive under its
    # own LOCALAPPDATA, and Global\ needs a privilege a plain user lacks.
    # use_last_error, because plain windll does not preserve GetLastError.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return True
    existing = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    if existing:
        ctypes.windll.user32.ShowWindow(existing, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(existing)
    return False


def data_dir() -> Path:
    """Per-user writable location; Program Files is read-only."""
    if "--data" in sys.argv:
        return Path(sys.argv[sys.argv.index("--data") + 1])
    if os.environ.get("ANVESHAN_DATA_DIR"):
        return Path(os.environ["ANVESHAN_DATA_DIR"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "ANVESHAN" / "datasets"


def attach_logs(base: Path) -> None:
    """A windowless exe has no console, so sys.stdout/stderr are None and
    uvicorn's logging config dies with "Unable to configure formatter".
    Send them to a file the operator can hand to support."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stream = open(logs / "anveshan.log", "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr = stream


def install_folder_picker(picker) -> None:
    """Hand pywebview's native folder dialog to the API.

    It has to land on the app.main *module*: pick_folder() reads a module
    global, so setting the attribute on the FastAPI instance instead looks
    identical at the call site and silently does nothing.
    """
    import app.main

    app.main.NATIVE_FOLDER_PICKER = picker


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_serving(url: str, timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> int:
    if not claim_single_instance():
        return 0

    target = data_dir()
    target.mkdir(parents=True, exist_ok=True)
    os.environ["ANVESHAN_DATA_DIR"] = str(target)
    attach_logs(target.parent)
    log = target.parent / "logs" / "anveshan.log"

    if not os.environ.get("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER") and not webview2_version():
        alert(
            "ANVESHAN cannot start",
            "The Microsoft Edge WebView2 Runtime is not installed on this "
            "computer.\n\nANVESHAN needs it to display its window.\n\n"
            "Re-run the ANVESHAN installer, which installs it without "
            "internet access, or ask your administrator to run "
            "MicrosoftEdgeWebView2RuntimeInstallerX64.exe from the "
            "installation media.",
        )
        return 2

    import uvicorn
    import webview

    from app.main import app as api

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    server = uvicorn.Server(
        uvicorn.Config(api, host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    if not wait_until_serving(url):
        alert(
            "ANVESHAN cannot start",
            f"The local ANVESHAN service did not respond on {url}.\n\n"
            f"Details were written to:\n{log}\n\n"
            "Please send that file to your system administrator.",
        )
        return 1

    window = webview.create_window(WINDOW_TITLE, url,
                                   width=1440, height=900, min_size=(1100, 700))
    # pywebview owns the native folder dialog and works in the embeddable
    # Python runtime without an extra GUI toolkit dependency.
    install_folder_picker(lambda: window.create_file_dialog(webview.FOLDER_DIALOG))
    webview.start()

    # Window closed. torch/faiss worker threads do not join reliably, and a
    # leftover process would fail acceptance test A3, so exit hard.
    server.should_exit = True
    time.sleep(0.3)
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
