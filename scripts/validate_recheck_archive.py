"""Exercise a copy of the archive; originals and the operator database stay untouched."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import shutil
import uuid
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--source-data", type=Path, default=ROOT / "datasets")
parser.add_argument(
    "--output", type=Path, default=ROOT / "datasets/recheck-validation.json"
)
args = parser.parse_args()
args.source_data = args.source_data.resolve()
with tempfile.TemporaryDirectory(prefix="anveshan-recheck-") as sandbox:
    for name in ("library.sqlite3", "semantic_cache.sqlite3"):
        source = args.source_data / name
        if source.exists():
            with closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            ) as src, closing(sqlite3.connect(Path(sandbox) / name)) as dst:
                src.backup(dst)
    os.environ["ANVESHAN_DATA_DIR"] = sandbox
    import app.main as main
    from app.audit_routes import readiness
    from app.semantic_clusters import read_rgb

    engine = main.cluster_engine
    started = time.monotonic()
    engine.rebuild()
    while engine.running:
        if time.monotonic() - started > 1800:
            raise RuntimeError("Validation build timed out")
        time.sleep(0.5)
    assert engine.status["state"] == "ready", engine.status
    build_seconds = time.monotonic() - started
    groups = engine.result()
    rows = engine.snapshot()
    with closing(sqlite3.connect(Path(sandbox) / "semantic_cache.sqlite3")) as c:
        indexed = {r[0] for r in c.execute("select scene_id from scene_features")}
    representatives = [s for g in groups for s in g["scenes"]]
    assert all(s["id"] in indexed for s in representatives)
    assert all(
        duplicate not in indexed
        for s in representatives
        for duplicate in s.get("duplicate_scene_ids", [])
    )
    checks = []
    for group in groups:
        for a, b in zip(group["scenes"], group["scenes"][1:]):
            checks.append(readiness(a["id"], b["id"]))
    query = engine.search("satellite imagery", bbox="77,28,78,29", limit=200)
    expected = [
        r for r in main.filter_rows(rows, bbox="77,28,78,29") if r["id"] in indexed
    ]
    assert {r["id"] for r in query["results"]} == {r["id"] for r in expected}
    image_count = None
    if groups:
        ref = groups[0]["scenes"][0]
        image_result = engine.search_image(read_rgb(ref["path"]), limit=200)
        result_ids = {r["id"] for r in image_result["results"]}
        assert {s["id"] for s in groups[0]["scenes"]} <= result_ids
        image_count = len(result_ids)
    report = {
        "isolated_database": True,
        "source_files_modified": False,
        "scenes": len(rows),
        "accepted_representatives": len(indexed),
        "groups": len(groups),
        "build_seconds": build_seconds,
        "aoi_results": len(query["results"]),
        "expected_aoi_indexed_observations": len(expected),
        "image_search_result_count": image_count,
        "pair_checks": checks,
        "analysable_pairs": sum(r["analysable"] for r in checks),
        "pair_count": len(checks),
        "note": "Integration checks on the existing archive; not held-out accuracy or novel geography validation.",
    }
    # A second import must work from arbitrary names and a fresh folder/cache.
    if len(groups) >= 2:
        fresh = Path(sandbox) / "fresh-input"
        fresh.mkdir()
        source_groups = {}
        for group in groups[:2]:
            for scene in group["scenes"][:3]:
                target = fresh / (uuid.uuid4().hex + Path(scene["path"]).suffix)
                shutil.copyfile(scene["path"], target)
                target.with_suffix(".json").write_text(
                    json.dumps({"date": scene.get("date")}), encoding="utf-8"
                )
                source_groups[str(target)] = group["key"]
        main._reset_archive_for_new_import()
        main.jobs["fresh-validation"] = {}
        main._scan("fresh-validation", str(fresh))
        assert main.jobs["fresh-validation"]["state"] == "complete"
        assert (
            engine.result() == [] and not engine.build_requested and not engine.running
        )
        fresh_started = time.monotonic()
        engine.rebuild()
        while engine.running:
            if time.monotonic() - fresh_started > 300:
                raise RuntimeError("Fresh-folder build timed out")
            time.sleep(0.25)
        assert engine.status["state"] == "ready", engine.status
        fresh_groups = engine.result()
        assert len(fresh_groups) == 2
        assert all(
            len({source_groups[s["path"]] for s in g["scenes"]}) == 1
            for g in fresh_groups
        )
        ref = fresh_groups[0]["scenes"][0]
        hits = engine.search_image(read_rgb(ref["path"]), limit=200)["results"]
        assert {s["id"] for s in fresh_groups[0]["scenes"]} <= {s["id"] for s in hits}
        assert readiness(*[s["id"] for s in fresh_groups[0]["scenes"][:2]])[
            "analysable"
        ]
        report["fresh_folder"] = {
            "scenes": len(engine.snapshot()),
            "groups": len(fresh_groups),
            "arbitrary_filenames": True,
            "no_clusters_before_button": True,
            "search_and_change_passed": True,
            "note": "New folder and cache using copied existing imagery; not an unseen geography benchmark.",
        }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps({k: v for k, v in report.items() if k != "pair_checks"}, indent=2),
        flush=True,
    )
