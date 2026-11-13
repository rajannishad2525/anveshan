import time
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import app.main as main


def scan(client, folder, mode="append"):
    r = client.post("/api/scan", json={"folder": str(folder), "mode": mode})
    assert r.status_code == 200, r.text
    for _ in range(100):
        status = client.get("/api/jobs/" + r.json()["id"]).json()
        if status["state"] in {"complete", "failed"}:
            break
        time.sleep(0.01)
    assert status["state"] == "complete"


def test_append_replace_and_same_size_content_change(tmp_path):
    client = TestClient(main.app)
    folder = tmp_path / "new"
    folder.mkdir()
    path = folder / "new.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(path, compress_level=0)
    scan(client, folder)
    rows = client.get("/api/scenes").json()
    assert len(rows) == 3
    old = next(r for r in rows if r["name"] == "new.png")
    Image.new("RGB", (20, 20), (255, 255, 255)).save(path, compress_level=0)
    scan(client, folder)
    new = next(r for r in client.get("/api/scenes").json() if r["name"] == "new.png")
    assert old["bytes"] == new["bytes"] and old["sha256"] != new["sha256"]
    scan(client, folder, "replace")
    assert len(client.get("/api/scenes").json()) == 1
    assert not main.cluster_engine.build_requested
    assert client.get("/api/clusters").json() == []
    assert not main.cluster_engine.running
    assert (
        client.post(
            "/api/scan", json={"folder": str(folder / "absent"), "mode": "replace"}
        ).status_code
        == 400
    )
    assert len(client.get("/api/scenes").json()) == 1


def test_spatial_sensor_filters_and_geotiff_metadata(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    folder = tmp_path / "geo"
    folder.mkdir()
    with rasterio.open(
        folder / "scene.tif",
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=3,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(77, 29, 0.01, 0.01),
    ) as dst:
        dst.write(np.ones((3, 10, 10), dtype="uint8"))
        dst.update_tags(SENSOR="test-sensor", ACQUISITION_DATE="2024-06-02")
    client = TestClient(main.app)
    scan(client, folder)
    result = client.get(
        "/api/scenes", params={"bbox": "76,28,78,30", "sensor": "test-sensor"}
    ).json()
    assert len(result) == 1 and result[0]["date"] == "2024-06-02"
    assert client.get("/api/scenes", params={"bbox": "0,0,1,1"}).json() == []
    assert client.get("/api/scenes", params={"bbox": "nan,0,1,1"}).status_code == 400


def test_registered_change_translation_and_local_change():
    import cv2
    from app.verified_change import analyze

    rng = np.random.default_rng(52)
    left = rng.integers(40, 180, (256, 256, 3), dtype=np.uint8)
    left = cv2.GaussianBlur(left, (3, 3), 0)
    shifted = cv2.warpAffine(left, np.float32([[1, 0, 6], [0, 1, 4]]), (256, 256))
    stable = analyze(left, shifted)
    assert stable["adjusted_changed_pixel_ratio"] < 0.01
    shifted[80:115, 80:115] = [200, 60, 60]
    changed = analyze(left, shifted)
    assert changed["region_count"] > 0
    assert changed["adjusted_changed_pixel_ratio"] > 0.01

    # 144 separate patches: the count is the real one even though only the
    # 100 largest are listed for drawing (it used to report 100).
    many = shifted.copy()
    for y in range(20, 236, 18):
        for x in range(20, 236, 18):
            many[y:y + 5, x:x + 5] = [250, 250, 30]
    out = analyze(left, many)
    assert out["regions_listed"] == 100 < out["region_count"]


def test_onset_refuses_invented_dates():
    client = TestClient(main.app)
    ids = [r["id"] for r in client.get("/api/scenes").json()]
    r = client.post("/api/timeline/onset", json={"scene_ids": ids})
    assert r.status_code == 200
    assert r.json()["first_supporting_observation"] is None
    assert len(r.json()["gaps"]) == 2


def test_tiling_preserves_pixels_and_source(tmp_path):
    import rasterio, json
    from rasterio.transform import from_origin

    folder = tmp_path / "large"
    folder.mkdir()
    pixels = np.arange(3 * 140 * 140, dtype="uint16").reshape(3, 140, 140)
    with rasterio.open(
        folder / "large.tif",
        "w",
        driver="GTiff",
        width=140,
        height=140,
        count=3,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(77, 29, 0.001, 0.001),
    ) as dst:
        dst.write(pixels)
    client = TestClient(main.app)
    scan(client, folder)
    response = client.post("/api/tiles/build", json={"tile_size": 128})
    assert response.status_code == 200
    for _ in range(200):
        job = client.get("/api/jobs/" + response.json()["id"]).json()
        if job["state"] in {"complete", "failed"}:
            break
        time.sleep(0.01)
    assert job["state"] == "complete", job
    tiles = [
        s
        for s in client.get("/api/scenes").json()
        if s["footprint"] and json.loads(s["footprint"]).get("pixel_window")
    ]
    assert len(tiles) == 4
    for tile in tiles:
        fp = json.loads(tile["footprint"])
        x, y, w, h = fp["pixel_window"]
        with rasterio.open(tile["path"]) as src:
            assert np.array_equal(src.read(), pixels[:, y : y + h, x : x + w])
            assert str(src.crs) == "EPSG:4326"
        assert fp["source_sha256"]
