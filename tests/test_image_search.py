import sqlite3

from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
import app.semantic_clusters as semantic


def test_upload_accepts_windows_octet_stream_for_tiff(monkeypatch):
    captured = {}

    def search_image(image, **filters):
        captured["size"] = image.size
        captured["filters"] = filters
        return {"mode": "image-to-image", "results": []}

    monkeypatch.setattr(main, "read_rgb", lambda source: Image.new("RGB", (40, 30)))
    monkeypatch.setattr(main.cluster_engine, "search_image", search_image)

    response = TestClient(main.app).post(
        "/api/search/semantic/upload?sensor=Sentinel-2",
        files={"file": ("reference.tif", b"tiff bytes", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert captured == {
        "size": (40, 30),
        "filters": {
            "date_from": "",
            "date_to": "",
            "kind": "",
            "limit": 30,
            "sensor": "Sentinel-2",
            "bbox": "",
        },
    }


def test_uploaded_image_keeps_unverified_visual_neighbours(monkeypatch, tmp_path):
    database = tmp_path / "image-search.sqlite3"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (32, 32), "green").save(candidate)
    with sqlite3.connect(database) as db:
        db.execute(
            "create table scenes (id integer, path text, name text, status text, kind text)"
        )
        db.execute(
            "insert into scenes values (1, ?, 'candidate.png', 'ready', 'PNG')",
            (str(candidate),),
        )

    def connect():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    engine = semantic.ClusterEngine(tmp_path, connect)
    engine.status = {"state": "ready"}

    class FakeModel:
        def encode_image(self, value):
            import torch

            return torch.tensor([[1.0, 0.0]])

    import torch

    engine.model = FakeModel()
    engine.device = "cpu"
    engine.preprocess = lambda image: torch.zeros(3, 2, 2)
    monkeypatch.setattr(engine, "rank_vectors", lambda rows, vector, limit: [(rows[0], 0.81)])
    monkeypatch.setattr(semantic, "local_features", lambda image: ([], None, image.size))
    monkeypatch.setattr(
        semantic,
        "verify_place",
        lambda left, right: {"matched": False, "method": "RootSIFT + RANSAC"},
    )

    result = engine.search_image(Image.new("RGB", (24, 24), "blue"))

    assert len(result["results"]) == 1
    match = result["results"][0]
    assert match["id"] == 1
    assert match["structural_match"] is False
    assert match["retrieval_source"] == "direct_visual_similarity"
    assert "unverified" in match["score_type"]
