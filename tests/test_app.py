from pathlib import Path
import json
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app, DB_PATH, conn, _visual_fingerprint


def test_scan_folder_indexes_images():
    tmp_path = Path(__file__).parent / "_fixture"
    tmp_path.mkdir(exist_ok=True)
    Image.new("RGB", (32, 24), (30, 60, 30)).save(tmp_path / "scene.png")
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(tmp_path)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert j["state"] == "complete"
    scenes = c.get("/api/scenes").json()
    assert any(x["name"] == "scene.png" for x in scenes)


def test_search_and_decision_are_local():
    c = TestClient(app)
    results = c.get("/api/search", params={"q": "scene"}).json()
    assert results["method"] == "offline metadata baseline"
    scene = next(x for x in c.get("/api/scenes").json() if x["name"] == "scene.png")
    saved = c.post(
        "/api/decisions",
        json={
            "scene_id": scene["id"],
            "decision": "needs-review",
            "note": "inspect source",
        },
    ).json()
    assert saved["saved"] is True
    other = next(x for x in c.get("/api/scenes").json() if x["id"] != scene["id"])
    compared = c.get(
        "/api/compare", params={"before": scene["id"], "after": other["id"]}
    )
    assert compared.status_code == 200
    assert compared.json()["before"]["id"] == scene["id"]
    pairs = c.get("/api/pairs", params={"limit": 5})
    assert pairs.status_code == 200
    assert isinstance(pairs.json(), list)
    fp = c.get("/api/scenes/%s/footprint" % scene["id"])
    assert fp.status_code == 200 and fp.json()["available"] is False


def test_local_index_build_is_explicit_and_honest():
    c = TestClient(app)
    s = c.get("/api/index/status").json()
    assert s["indexed"] >= 0 and s["ready_scenes"] >= s["indexed"]
    assert s["encoder"] == "local-thumbnail-histogram-v2"
    assert "staged" in s["semantic_encoder"]


def test_folder_picker_requires_desktop_runtime(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "NATIVE_FOLDER_PICKER", None)
    response = TestClient(app).get("/api/pick-folder")
    assert response.status_code == 503
    message = response.json()["detail"].lower()
    assert "paste" in message and "absolute" in message


def test_folder_picker_uses_injected_pywebview_picker(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "NATIVE_FOLDER_PICKER", lambda: (r"C:\\imagery\\mission_archive",))
    response = TestClient(app).get("/api/pick-folder")
    assert response.status_code == 200
    assert response.json() == {
        "folder": r"C:\\imagery\\mission_archive",
        "cancelled": False,
    }


def test_timeline_groups_dates_embedded_in_aoi_filename():
    """Build Timeline must keep an AOI's dated observations together."""
    folder = Path(__file__).parent / "_fixture" / "timeline"
    folder.mkdir(exist_ok=True)
    for name, color in (
        ("AOI01_2024-01-01_s2_clear.png", (20, 80, 20)),
        ("AOI01_2024-06-01_s2_clear.png", (40, 100, 40)),
    ):
        Image.new("RGB", (32, 24), color).save(folder / name)
    c = TestClient(app)
    response = c.post("/api/scan", json={"folder": str(folder)})
    assert response.status_code == 200
    import time

    for _ in range(30):
        job = c.get("/api/jobs/" + response.json()["id"]).json()
        if job["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert job["state"] == "complete"
    groups = c.get("/api/timeline", params={"limit": 100}).json()
    group = next(g for g in groups if g["cohort"] == "aoi01_s2_clear")
    assert group["count"] == 2


def test_timeline_keeps_map_tiles_apart_and_skips_rejected_files(tmp_path):
    # z16_46874_27358 and z16_46874_27359 are neighbouring tiles. Stripping the
    # trailing number merged three different places into one 30-scene cohort,
    # and rejected blank tiles were listed as observations.
    from conftest import textured
    import app.main as main

    for period in ("2017", "2024-22"):
        (tmp_path / period).mkdir()
        for y in (27358, 27359):
            textured((70, 90, 60), seed=y).save(tmp_path / period / f"z16_46874_{y}.png")
    (tmp_path / "2025").mkdir()
    Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(tmp_path / "2025" / "z16_46874_27358.png")
    main.jobs["tiles"] = {}
    main._scan("tiles", str(tmp_path))
    groups = {g["cohort"]: g for g in TestClient(app).get("/api/timeline").json()}
    assert groups["z16_46874_27358"]["count"] == 2
    assert groups["z16_46874_27359"]["count"] == 2
    assert all(s["status"] == "ready" for g in groups.values() for s in g["scenes"])


def test_visual_search_uses_local_index_and_stays_nonsemantic():
    """Visual-neighbour discovery must expose its baseline method honestly."""
    c = TestClient(app)
    rows = c.get("/api/scenes", params={"q": "scene"}).json()
    reference = next(x for x in rows if x["name"] == "scene.png")
    candidate = next(x for x in rows if x["name"] == "scene_after.png")
    db = conn()
    for item in (reference, candidate):
        db.execute(
            "insert into scene_index(scene_id,fingerprint,encoder,indexed_at) values(?,?,?,datetime('now')) on conflict(scene_id) do update set fingerprint=excluded.fingerprint,encoder=excluded.encoder",
            (
                item["id"],
                _visual_fingerprint(item["path"]),
                "local-thumbnail-histogram-v2",
            ),
        )
    db.commit()
    db.close()
    result = c.get(
        "/api/search/visual", params={"scene_id": reference["id"], "limit": 10}
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["semantic"] is False
    assert payload["encoder"] == "local-thumbnail-histogram-v2"
    assert payload["method"].startswith("offline local thumbnail")
    assert any(x["id"] == candidate["id"] for x in payload["results"])
    assert all(
        x["score_type"] == "local visual fingerprint similarity"
        for x in payload["results"]
    )


def test_change_score_is_transparent_screening_baseline():
    from conftest import textured

    tmp_path = Path(__file__).parent / "_fixture"
    textured((220, 40, 40), seed=2).save(tmp_path / "scene_after.png")
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(tmp_path)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert j["state"] == "complete"
    rows = c.get("/api/scenes", params={"q": "scene"}).json()
    before = next(x for x in rows if x["name"] == "scene.png")
    after = next(x for x in rows if x["name"] == "scene_after.png")
    result = c.get(
        "/api/change-score", params={"before": before["id"], "after": after["id"]}
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["analysis_status"] == "screening only"
    assert payload["changed_pixel_ratio"] > 0.9
    assert payload["caveats"]


def test_quality_triage_flags_blank_raster_and_reports_metrics():
    """Quality triage must expose an honest, reproducible intake signal."""
    tmp_path = Path(__file__).parent / "_fixture"
    blank = tmp_path / "quality_blank.png"
    Image.new("L", (48, 36), 128).save(blank)
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(tmp_path)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert j["state"] == "complete"
    scene = next(
        x for x in c.get("/api/scenes").json() if x["name"] == "quality_blank.png"
    )
    result = c.get("/api/quality/%s" % scene["id"])
    assert result.status_code == 200
    payload = result.json()
    assert payload["available"] is True
    assert payload["blank"] is True
    assert payload["low_contrast"] is True
    assert "blank or constant image" in payload["flags"]
    assert payload["quality_gate"] == "review required"
    assert payload["source"] == "local raster sample"
    assert payload["sample_width"] == 48 and payload["sample_height"] == 36
    assert payload["stddev"] == 0.0


def test_quality_summary_is_offline_and_bounded():
    c = TestClient(app)
    result = c.get("/api/quality", params={"limit": 1})
    assert result.status_code == 200
    payload = result.json()
    assert payload["offline"] is True
    assert len(payload["scenes"]) <= 1
    assert payload["source"] == "local raster samples"


def test_a_frame_without_detail_cannot_support_a_change_call(tmp_path):
    # A fully clouded or saturated frame is one flat colour. It used to pass
    # the compare gate and get a "shadow / illumination" narrative.
    from conftest import textured

    folder = tmp_path / "obscured"
    folder.mkdir()
    Image.new("RGB", (32, 24), (255, 255, 255)).save(folder / "cloud_2024-01-04.png")
    textured((90, 110, 70), seed=3).save(folder / "clear_2024-02-23.png")
    c = TestClient(app)
    import app.main as main
    main.jobs["obscured"] = {}
    main._scan("obscured", str(folder))
    rows = {x["name"]: x for x in c.get("/api/scenes").json()}
    pair = {"before": rows["cloud_2024-01-04.png"]["id"], "after": rows["clear_2024-02-23.png"]["id"]}

    gate = c.get("/api/compare", params=pair).json()
    assert gate["quality_gate"] == "review required"
    assert "before image has no usable detail" in gate["quality_flags"]
    score = c.get("/api/change-score", params=pair).json()
    assert score["analysis_status"] == "cannot determine"
    report = c.get("/api/change-report", params=pair).json()
    assert report["narrative"].startswith("Cannot determine change")


def test_change_score_exposes_transparent_false_alarm_signals():
    """Bright low-chroma cover is surfaced and down-weighted for review."""
    import numpy as np
    from app.main import _false_alarm_signals

    before = np.zeros((12, 12, 3), dtype="uint8")
    after = np.full((12, 12, 3), 245, dtype="uint8")
    signals = _false_alarm_signals(before, after)
    assert "cloud/snow-like bright low-chroma area" in signals["flags"]
    assert signals["candidate_pixel_fraction"] == 1.0
    assert signals["mean_luminance_shift"] > 0.9
    assert signals["method"].startswith("RGB thumbnail heuristics")


def test_false_alarm_pair_endpoint_reports_quality_gate_and_suppression():
    c = TestClient(app)
    rows = c.get("/api/scenes", params={"q": "scene"}).json()
    before = next(x for x in rows if x["name"] == "scene.png")
    after = next(x for x in rows if x["name"] == "scene_after.png")
    result = c.get(
        "/api/false-alarm/pair", params={"before": before["id"], "after": after["id"]}
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["method"] == "offline false-alarm suppression heuristics"
    assert payload["quality_gate"] in {"pass", "review required"}
    assert payload["comparison"]["available"] is True
    assert "raw_changed_pixel_ratio" in payload["comparison"]
    assert "bright_low_chroma_fraction" in payload["signals"]
    assert payload["caveat"]


def test_llm_compare_report_uses_measured_pair_facts(monkeypatch):
    """Analyst brief must be grounded in local measured comparison facts."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    folder = Path(__file__).parent / "_fixture" / "llm_pairs"
    folder.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": 48,
        "width": 48,
        "count": 3,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_origin(77.0, 28.0, 0.001, 0.001),
    }
    base = np.zeros((3, 48, 48), dtype=np.uint8)
    yy, xx = np.indices((48, 48))
    base[0] = (xx * 4 + 40).astype(np.uint8)
    base[1] = (yy * 4 + 50).astype(np.uint8)
    base[2] = ((xx + yy) * 2 + 60).astype(np.uint8)
    changed = base.copy()
    changed[0, 12:28, 15:32] = 230
    changed[1, 12:28, 15:32] = 30
    changed[2, 12:28, 15:32] = 30
    for name, data in [
        ("2024-05-18_before_visual.tif", base),
        ("2024-09-20_after_visual.tif", changed),
    ]:
        with rasterio.open(folder / name, "w", **profile) as dst:
            dst.write(data)
    monkeypatch.setattr(
        "app.local_llm.generate_analyst_brief",
        lambda prompt: (None, {"available": False, "provider": "test", "model": "fallback"}),
    )
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(folder)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    rows = c.get("/api/scenes", params={"q": "visual"}).json()
    before = next(x for x in rows if x["name"] == "2024-05-18_before_visual.tif")
    after = next(x for x in rows if x["name"] == "2024-09-20_after_visual.tif")
    result = c.get(
        "/api/llm/compare-report", params={"before": before["id"], "after": after["id"]}
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["facts"]["date_a"] == "2024-05-18"
    assert payload["facts"]["date_b"] == "2024-09-20"
    assert payload["facts"]["changed_pixel_ratio_percent"] > 0
    assert payload["facts"]["regions"] >= 1
    assert payload["facts"]["false_alarm"] in {
        "not confirmed",
        "possible false alarm / review required",
        "partly suppressed by nuisance screening",
    }
    assert payload["llm"]["available"] is False
    assert "analyst" in payload["caveat"].lower()


def test_labelled_evaluation_accepts_csv_and_reports_metrics():
    """A held-out manifest must produce reproducible confusion metrics locally."""
    folder = Path(__file__).parent / "_fixture" / "eval_pairs"
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 24), (20, 20, 20)).save(folder / "before.png")
    Image.new("RGB", (24, 24), (230, 20, 20)).save(folder / "after.png")
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(folder)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert j["state"] == "complete"
    manifest = folder / "labels.csv"
    manifest.write_text(
        "before,after,label\nbefore.png,after.png,change\n", encoding="utf-8"
    )
    result = c.post("/api/evaluation/run", json={"manifest": str(manifest)})
    assert result.status_code == 200
    payload = result.json()
    assert payload["offline"] is True
    assert payload["evaluated_pairs"] == 1
    assert payload["confusion_matrix"]["true_positive"] == 1
    assert payload["metrics"]["precision"] == 1.0
    assert payload["method"].startswith("offline pixel-difference")


def test_labelled_metrics_report_confusion_and_false_alarm_rate():
    c = TestClient(app)
    rows = c.get("/api/scenes", params={"q": "scene"}).json()
    before = next(x for x in rows if x["name"] == "scene.png")
    after = next(x for x in rows if x["name"] == "scene_after.png")
    # A changed pair labelled 1 should be detected; the same pair labelled 0
    # is a deliberate false-positive fixture for metric arithmetic.
    result = c.post(
        "/api/evaluation/metrics",
        json={
            "pairs": [
                {"before_id": before["id"], "after_id": after["id"], "label": 1},
                {"before_id": before["id"], "after_id": after["id"], "label": 0},
            ],
            "threshold": 0.18,
            "prediction_ratio": 0.03,
        },
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["offline"] is True
    assert payload["evaluated_pairs"] == 2
    assert payload["confusion_matrix"] == {
        "true_positive": 1,
        "true_negative": 0,
        "false_positive": 1,
        "false_negative": 0,
    }
    assert payload["metrics"]["precision"] == 0.5
    assert payload["metrics"]["recall"] == 1.0
    assert payload["metrics"]["f1"] == round(2 * 0.5 * 1.0 / (0.5 + 1.0), 4)
    assert payload["metrics"]["false_alarm_rate"] == 1.0
    assert payload["caveats"]


def test_labelled_evaluation_accepts_json_and_rejects_unsafe_or_invalid_manifest():
    """Manifest intake stays local, bounded and label-validated."""
    folder = Path(__file__).parent / "_fixture" / "eval_pairs"
    test_labelled_evaluation_accepts_csv_and_reports_metrics()
    rows = [{"before": "before.png", "after": "after.png", "label": 1}]
    manifest = folder / "labels.json"
    manifest.write_text(json.dumps({"pairs": rows}), encoding="utf-8")
    c = TestClient(app)
    result = c.post("/api/evaluation/run", json={"manifest": str(manifest)})
    assert result.status_code == 200
    assert result.json()["evaluated_pairs"] == 1

    unsafe = c.post(
        "/api/evaluation/run", json={"manifest": "https://example.invalid/labels.json"}
    )
    assert unsafe.status_code == 400
    invalid = folder / "invalid.csv"
    invalid.write_text(
        "before,after,label\nbefore.png,after.png,maybe\n", encoding="utf-8"
    )
    rejected = c.post("/api/evaluation/run", json={"manifest": str(invalid)})
    assert rejected.status_code == 400


def test_geotiff_alignment_refuses_unverified_pixel_comparison():
    """Operational raster comparison must never hide a source-grid mismatch."""
    import rasterio
    from rasterio.transform import from_origin

    folder = Path(__file__).parent / "_fixture" / "alignment_pairs"
    folder.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": 16,
        "width": 16,
        "count": 3,
        "dtype": "uint8",
        "crs": "EPSG:4326",
    }
    for name, transform in [
        ("aligned_before.tif", from_origin(77.0, 28.0, 0.001, 0.001)),
        ("misaligned_after.tif", from_origin(77.1, 28.0, 0.001, 0.001)),
    ]:
        with rasterio.open(folder / name, "w", transform=transform, **profile) as dst:
            dst.write(__import__("numpy").full((3, 16, 16), 80, dtype="uint8"))
    c = TestClient(app)
    r = c.post("/api/scan", json={"folder": str(folder)})
    assert r.status_code == 200
    import time

    for _ in range(30):
        j = c.get("/api/jobs/" + r.json()["id"]).json()
        if j["state"] in ("complete", "failed"):
            break
        time.sleep(0.03)
    assert j["state"] == "complete"
    rows = c.get("/api/scenes", params={"q": "alignment"}).json()
    before = next(x for x in rows if x["name"] == "aligned_before.tif")
    after = next(x for x in rows if x["name"] == "misaligned_after.tif")
    report = c.get(
        "/api/alignment", params={"before": before["id"], "after": after["id"]}
    )
    assert report.status_code == 200
    assert report.json()["verified"] is False
    assert "spatial bounds differ" in report.json()["flags"]
    refused = c.get(
        "/api/change-score", params={"before": before["id"], "after": after["id"]}
    )
    assert refused.status_code == 422
    assert "pixel comparison refused" in refused.json()["detail"]


def test_status_reports_the_real_semantic_index_state():
    # The status card said "Semantic encoder staged" whether or not the index was built.
    s = TestClient(app).get("/api/status").json()
    assert s["semantic_index"] == "Semantic index not built yet"


def test_a_decision_needs_a_reason_and_a_real_scene():
    # The audit log accepted "rejected" with an empty note, and decisions on
    # scene ids that were never imported.
    c = TestClient(app)
    scene = next(x for x in c.get("/api/scenes").json() if x["name"] == "scene.png")
    blank = c.post("/api/decisions", json={"scene_id": scene["id"], "decision": "rejected", "note": "  "})
    assert blank.status_code == 400
    ghost = c.post("/api/decisions", json={"scene_id": 999999, "decision": "accepted", "note": "x"})
    assert ghost.status_code == 404


def test_rebuilding_an_up_to_date_index_is_not_a_failure():
    # With every scene already indexed the job had nothing to do and reported
    # "failed: No scene could be indexed; 0 failed".
    import app.main as main

    main.jobs["first"] = {}
    main._build_index("first")
    main.jobs["again"] = {}
    main._build_index("again")
    assert main.jobs["again"]["state"] == "complete"
    assert "up to date" in main.jobs["again"]["message"]
