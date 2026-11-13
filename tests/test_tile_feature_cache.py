"""Tile vectors are reused only while the scene's pixels are unchanged.

Re-encoding an unchanged 121-scene archive costs ~2 minutes of CPU for
identical numbers, so build_tile_features stamps each row with the encoder
version *and* the scene's pixel digest. These tests pin both halves of that
bargain: reuse when the digest matches, re-encode when it does not.
"""

import sqlite3

import numpy as np
import pytest
from PIL import Image

from app.semantic_clusters import ClusterEngine, TILE_PX


class _StubEncoder:
    """Stands in for RemoteCLIP: counts how many tiles were actually encoded."""

    def __init__(self):
        self.encoded = 0

    def encode_image(self, stacked):
        import torch

        self.encoded += len(stacked)
        return torch.ones(len(stacked), 8)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("ANVESHAN_DATA_DIR", str(tmp_path))
    e = ClusterEngine(tmp_path, lambda: sqlite3.connect(":memory:"))
    e.data = tmp_path
    e.device = "cpu"
    e.model = _StubEncoder()
    import torch

    e.preprocess = lambda crop: torch.zeros(3, 224, 224)
    return e


def _scene(tmp_path, name, seed):
    """A scene big enough to tile into more than one window."""
    rng = np.random.default_rng(seed)
    path = tmp_path / name
    Image.fromarray(
        rng.integers(0, 255, (TILE_PX * 2, TILE_PX * 2, 3), dtype="uint8")
    ).save(path)
    return {"id": 1, "name": name, "path": str(path)}


def _rows(data):
    with sqlite3.connect(data / "semantic_cache.sqlite3") as c:
        return c.execute("select count(*) from tile_features").fetchone()[0]


def test_unchanged_scene_is_not_re_encoded(engine, tmp_path):
    scene = _scene(tmp_path, "a.png", 1)
    total = engine.build_tile_features([scene], "v1", {1: "digest-a"})
    first = engine.model.encoded
    assert total == 4 and first == 4

    assert engine.build_tile_features([scene], "v1", {1: "digest-a"}) == total
    assert engine.model.encoded == first, "unchanged scene was encoded again"
    assert engine.status["tiles_reused"] == total
    assert engine.status["tiles_encoded"] == 0
    assert _rows(tmp_path) == total


def test_changed_pixels_invalidate_the_cached_tiles(engine, tmp_path):
    scene = _scene(tmp_path, "a.png", 1)
    engine.build_tile_features([scene], "v1", {1: "digest-a"})
    before = engine.model.encoded

    engine.build_tile_features([scene], "v1", {1: "digest-b"})
    assert engine.model.encoded == before * 2, "changed scene was not re-encoded"
    assert engine.status["tiles_encoded"] == before
    assert _rows(tmp_path) == before, "stale rows survived the re-encode"


def test_new_encoder_version_invalidates_the_cached_tiles(engine, tmp_path):
    scene = _scene(tmp_path, "a.png", 1)
    engine.build_tile_features([scene], "v1", {1: "digest-a"})
    before = engine.model.encoded

    engine.build_tile_features([scene], "v2", {1: "digest-a"})
    assert engine.model.encoded == before * 2, "version bump did not re-encode"


def test_scene_dropped_from_the_archive_loses_its_rows(engine, tmp_path):
    a = _scene(tmp_path, "a.png", 1)
    b = dict(_scene(tmp_path, "b.png", 2), id=2)
    engine.build_tile_features([a, b], "v1", {1: "digest-a", 2: "digest-b"})
    assert _rows(tmp_path) == 8

    engine.build_tile_features([a], "v1", {1: "digest-a"})
    assert _rows(tmp_path) == 4, "removed scene kept its tile vectors"
