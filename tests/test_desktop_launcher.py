"""Guards the two things that only break in the packaged, windowless build."""
import socket
import sys
import uuid

import desktop


def test_free_port_is_bindable():
    port = desktop.free_port()
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


def test_uvicorn_config_survives_missing_console(tmp_path, monkeypatch):
    # A windowless exe hands us sys.stdout/stderr = None; uvicorn's logging
    # config then dies with "Unable to configure formatter 'default'".
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop.attach_logs(tmp_path)

    assert sys.stdout is not None and sys.stderr is not None
    assert (tmp_path / "logs" / "anveshan.log").exists()

    import fastapi
    import uvicorn

    uvicorn.Config(fastapi.FastAPI(), host="127.0.0.1", port=0, log_level="warning")


def test_attach_logs_leaves_a_real_console_alone(tmp_path):
    before = sys.stdout
    desktop.attach_logs(tmp_path)
    assert sys.stdout is before
    assert not (tmp_path / "logs").exists()


def test_data_dir_is_user_writable_not_program_files(monkeypatch):
    monkeypatch.delenv("ANVESHAN_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\someone\AppData\Local")
    assert desktop.data_dir() == \
        __import__("pathlib").Path(r"C:\Users\someone\AppData\Local\ANVESHAN\datasets")


def test_webview2_detection_returns_version_or_none():
    # pywebview does not raise when the runtime is missing, it hangs, so the
    # launcher must decide for itself before creating a window.
    v = desktop.webview2_version()
    assert v is None or v.count(".") >= 2


def test_folder_picker_injection_reaches_the_endpoint():
    # The launcher used to set the attribute on the FastAPI instance while
    # pick_folder() read the module global, so SELECT FOLDER returned 503 in
    # the packaged app while every unit test passed.
    from fastapi.testclient import TestClient

    import app.main as main

    original = main.NATIVE_FOLDER_PICKER
    try:
        desktop.install_folder_picker(lambda: r"C:\imagery\mission_archive")
        response = TestClient(main.app).get("/api/pick-folder")
        assert response.status_code == 200
        assert response.json()["folder"] == r"C:\imagery\mission_archive"
    finally:
        main.NATIVE_FOLDER_PICKER = original


def test_second_instance_is_refused():
    # Two instances would run two servers over one SQLite archive, and the
    # installer plus a double-click already produced exactly that.
    # Own mutex name, so a real ANVESHAN running on this machine cannot
    # decide the result of the test.
    name = r"Local\ANVESHAN-test-" + uuid.uuid4().hex
    assert desktop.claim_single_instance(name) is True
    assert desktop.claim_single_instance(name) is False


def test_ui_footer_shows_the_installer_version():
    # The footer said v0.2 while the installer shipped 0.9.5.
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = re.search(r'AppVersion "([^"]+)"', (root / "scripts/anveshan.iss").read_text()).group(1)
    assert f"ANVESHAN v{iss} " in (root / "web/index.html").read_text(encoding="utf-8")
