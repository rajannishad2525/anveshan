"""Never allow tests to open the operator's live archive or model cache."""

import os
import tempfile

_sandbox = tempfile.TemporaryDirectory(prefix="anveshan-tests-")
os.environ["ANVESHAN_DATA_DIR"] = _sandbox.name

import pytest


def textured(rgb, seed, size=(32, 24)):
    """A small RGB frame of one colour plus deterministic texture."""
    import numpy as np
    from PIL import Image

    noise = np.random.default_rng(seed).integers(-25, 26, (size[1], size[0], 3))
    return Image.fromarray(np.clip(np.array(rgb) + noise, 0, 255).astype("uint8"))


def pytest_configure(config):
    """Give every Windows account its own basetemp.

    The repo is owned by one account and usually run by another, so both a
    repo-relative basetemp and pytest's default pytest-of-<user> end up owned
    by whoever ran first; the other one then gets WinError 5 on every test.
    """
    if config.option.basetemp is None:
        import getpass
        from pathlib import Path

        config.option.basetemp = (
            Path(tempfile.gettempdir()) / f"anveshan-pytest-{getpass.getuser()}"
        )


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    import app.main as main
    from app.semantic_clusters import ClusterEngine
    from PIL import Image

    monkeypatch.setattr(main, "DATA", tmp_path)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "library.sqlite3")
    monkeypatch.setenv("ANVESHAN_DATA_DIR", str(tmp_path))
    engine = ClusterEngine(main.ROOT, main.conn)
    monkeypatch.setattr(main, "cluster_engine", engine)
    # Independent deterministic inputs for the legacy API tests.
    folder = tmp_path / "inputs"
    folder.mkdir()
    # Textured, not flat: a single-colour frame carries no imagery, and change
    # screening rightly refuses to interpret it.
    textured((30, 60, 30), seed=1).save(folder / "scene.png")
    textured((220, 40, 40), seed=2).save(folder / "scene_after.png")
    main.jobs["fixture"] = {}
    main._scan("fixture", str(folder))
    yield
    assert not engine.running, "Test left a background model build running"
