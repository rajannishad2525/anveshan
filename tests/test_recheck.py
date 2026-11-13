import json
import sqlite3
import numpy as np
import pytest
from fastapi.testclient import TestClient
import app.main as main
from app.semantic_clusters import retain_observation


@pytest.mark.parametrize("reverse", [False, True])
def test_georeferenced_duplicate_is_representative(reverse):
    png = {"id": 1, "path": "one.png"}
    tif = {
        "id": 2,
        "path": "one.tif",
        "geometry": {"crs": "EPSG:4326", "bounds": [77, 28, 78, 29]},
    }
    accepted = []
    seen = {}
    rows = [tif, png] if reverse else [png, tif]
    assert not retain_observation(accepted, seen, ("digest", "2024"), rows[0])
    assert retain_observation(accepted, seen, ("digest", "2024"), rows[1])
    assert accepted == [tif]
    assert tif["duplicate_scene_ids"] == [1]
    assert "geometry" not in png
    assert not retain_observation(accepted, seen, ("digest", "2025"), {"id": 3})
    assert len(accepted) == 2


def test_filter_reuses_index_and_returns_low_ranked_eligible_result():
    engine = main.cluster_engine
    rows = engine.snapshot()
    with sqlite3.connect(main.DATA / "semantic_cache.sqlite3") as c:
        c.execute(
            "create table scene_features(scene_id integer primary key,vector blob,model text)"
        )
        c.executemany(
            "insert into scene_features values(?,?,?)",
            [
                (r["id"], v.tobytes(), "test")
                for r, v in zip(rows, np.eye(2, dtype="float32"))
            ],
        )
    assert engine.rank_vectors(rows, np.array([1, 0]), 1)[0][0]["id"] == rows[0]["id"]
    index = engine._rank_index
    filtered = engine.rank_vectors([rows[1]], np.array([1, 0]), 1)
    assert filtered[0][0]["id"] == rows[1]["id"]
    assert engine._rank_index is index


def test_scene_without_tile_vectors_stays_searchable_in_a_mixed_archive(monkeypatch):
    # A 256 px map tile yields one 224 px window, so it gets a scene vector but
    # no tile vectors. Once any larger scene had tile vectors, ranking switched
    # to tile mode and every small scene silently vanished from search.
    engine = main.cluster_engine
    monkeypatch.setattr(engine, "class_vectors", lambda: (["any"], np.zeros((1, 2), "float32")))
    rows = engine.snapshot()
    small, large = rows[0], rows[1]
    with sqlite3.connect(main.DATA / "semantic_cache.sqlite3") as c:
        c.execute("create table scene_features(scene_id integer primary key,vector blob,model text)")
        c.execute("create table tile_features(scene_id integer, tile_index integer, row integer,"
                  " col integer, water_fraction real, vector blob, model text)")
        c.executemany("insert into scene_features values(?,?,?)", [
            (small["id"], np.array([1, 0], "float32").tobytes(), "t"),
            (large["id"], np.array([0, 1], "float32").tobytes(), "t")])
        c.executemany("insert into tile_features values(?,?,?,?,?,?,?)", [
            (large["id"], i, 0, i, 0.0, np.array([0, 1], "float32").tobytes(), "t") for i in range(2)])
    ranked = engine.rank_vectors(rows, np.array([1, 0], "float32"), 5, cover_weight=0)
    assert [r["id"] for r, _ in ranked] == [small["id"], large["id"]]


def test_labels_fall_back_to_the_scene_vector_for_a_single_window_scene(monkeypatch):
    # A 256 px tile has no tile vectors, and the labels endpoint told the
    # operator to "run the local index build first" after it had run.
    engine = main.cluster_engine
    monkeypatch.setattr(engine, "class_vectors",
                        lambda: (["water", "built-up"], np.eye(2, dtype="float32")))
    row = engine.snapshot()[0]
    with sqlite3.connect(main.DATA / "semantic_cache.sqlite3") as c:
        c.execute("create table scene_features(scene_id integer primary key,vector blob,model text)")
        c.execute("insert into scene_features values(?,?,?)",
                  (row["id"], np.array([0, 1], "float32").tobytes(), "t"))
    out = engine.scene_labels(row["id"])
    assert out["granularity"] == "whole scene"
    assert out["windows"][0]["labels"][0]["class"] == "built-up"
    missing = engine.scene_labels(999999)
    assert missing["windows"] == [] and "not in the semantic index" in missing["note"]


def test_new_intake_rules_reach_scenes_imported_before_them(tmp_path, monkeypatch):
    from PIL import Image

    folder = tmp_path / "2021-19"
    folder.mkdir()
    Image.new("RGB", (32, 32), (60, 90, 30)).save(folder / "z16_1_1.png")
    main.jobs["first"] = {}
    main._scan("first", str(folder))
    with sqlite3.connect(main.DATA / "library.sqlite3") as c:  # old intake read "2021"
        c.execute("update scenes set date='2021' where name='z16_1_1.png'")
    main.jobs["same"] = {}
    main._scan("same", str(folder))
    assert main.jobs["same"]["unchanged"] == 1
    monkeypatch.setattr(main, "INTAKE_VERSION", "intake-next")
    main.jobs["bumped"] = {}
    main._scan("bumped", str(folder))
    row = next(r for r in main.cluster_engine.snapshot() if r["name"] == "z16_1_1.png")
    assert row["date"] == "2019-2021"


def test_sidecar_edits_and_removal_refresh_sensor_without_changing_pixels():
    row = main.cluster_engine.snapshot()[0]
    from pathlib import Path

    path = Path(row["path"])
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps({"date": "2024-03-12", "sensor": "test-sensor"}))
    main.jobs["refresh"] = {}
    main._scan("refresh", str(path.parent))
    new = next(r for r in main.cluster_engine.snapshot() if r["id"] == row["id"])
    assert new["sha256"] == row["sha256"] and new["sensor"] == "test-sensor"
    client = TestClient(main.app)
    assert client.get("/api/archive/sensors").json()["sensors"] == ["test-sensor"]
    unchanged_stamp = new["imported_at"]
    main._scan("refresh", str(path.parent))
    assert (
        next(r for r in main.cluster_engine.snapshot() if r["id"] == row["id"])[
            "imported_at"
        ]
        == unchanged_stamp
    )
    sidecar.unlink()
    main._scan("refresh", str(path.parent))
    assert client.get("/api/archive/sensors").json()["sensors"] == []


def test_grid_screening_masks_nodata_and_preflight_is_readonly(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    folder = tmp_path / "geo"
    folder.mkdir()
    rng = np.random.default_rng(25)
    pixels = rng.integers(50, 190, (3, 96, 96), dtype=np.uint8)
    pixels[:, :, :10] = 0
    for name in ("a", "b"):
        with rasterio.open(
            folder / f"{name}.tif",
            "w",
            driver="GTiff",
            count=3,
            width=96,
            height=96,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(77, 29, 0.001, 0.001),
            nodata=0,
        ) as dst:
            dst.write(pixels)
    main.jobs["geo"] = {}
    main._scan("geo", str(folder))
    ids = [
        r["id"] for r in main.cluster_engine.snapshot() if r["kind"] == "GeoTIFF/COG"
    ]
    client = TestClient(main.app)
    params = {"before": ids[0], "after": ids[1]}
    result = client.get("/api/compare/readiness", params=params)
    assert result.json()["analysable"] is True, result.text
    assert not (main.DATA / "processing.jsonl").exists()
    analysis = client.get("/api/change/registered", params=params).json()
    assert (
        analysis["registration"]["method"] == "declared identical source GeoTIFF grid"
    )
    assert analysis["adjusted_changed_pixel_ratio"] == 0
    assert analysis["usable_fraction"] < 0.95
    with rasterio.open(folder / "b.tif", "r+") as dst:
        dst.transform = from_origin(78, 29, 0.001, 0.001)
    assert not client.get("/api/compare/readiness", params=params).json()["analysable"]


def test_year_onset_never_becomes_exact_date(monkeypatch):
    import app.audit_routes as routes

    ids = [r["id"] for r in main.cluster_engine.snapshot()]
    with main.conn() as c:
        for sid, year in zip(ids, ["2020", "2024"]):
            c.execute("update scenes set date=? where id=?", (year, sid))
    monkeypatch.setattr(
        routes, "registered", lambda *a, **k: {"adjusted_changed_pixel_ratio": 0.2}
    )
    result = routes.onset(routes.TimelineRequest(scene_ids=ids))
    assert result["first_supporting_observation"] is None
    assert result["year_resolution"]["date_precision"] == "year"
    assert result["year_resolution"]["first_supporting_observation"]["year"] == "2024"
    assert "date" not in result["year_resolution"]["first_supporting_observation"]


def test_retrieval_metrics_require_complete_independent_labels():
    from app.evaluation import calculate_retrieval, Judgment

    pool = {
        "queries": [{"query": "river", "results": [{"scene_id": 1}, {"scene_id": 2}]}]
    }
    labels = [
        Judgment(query_index=0, scene_id=1, judge_a=False, judge_b=False),
        Judgment(query_index=0, scene_id=2, judge_a=True, judge_b=True),
    ]
    result = calculate_retrieval(pool, labels)
    assert result["mrr"] == 0.5 and result["precision_at_5"] == 0.2
    assert result["cohen_kappa"] == 1
    labels[0].judge_b = True
    result = calculate_retrieval(pool, labels)
    assert result["mrr"] is None and result["disagreements"] == 1
    with pytest.raises(ValueError):
        calculate_retrieval(pool, labels[:1])


def test_opt_in_query_feedback_is_bounded_and_does_not_mutate_vectors():
    from app.semantic_clusters import refine_query

    query = np.array([1.0, 0.0], dtype="float32")
    examples = np.tile([0.0, 1.0], (5, 1)).astype("float32")
    result = refine_query(query, examples)
    assert result[0] > 0.95 and 0 < result[1] < 0.2
    assert np.all(query == [1, 0]) and np.all(examples == [0, 1])
    with pytest.raises(ValueError):
        refine_query(query, examples[:4])
