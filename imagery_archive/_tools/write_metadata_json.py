"""Publish each AOI's sidecars as a metadata.json the application will actually read.

The archive keeps one JSON per scene under `sidecar/`, which is the right shape for
provenance. The application looks in exactly two places: `<scene>.json` beside the raster,
or `metadata.json` in the raster's own folder, keyed by filename. This writes the second
form, so nothing has to be duplicated and the sidecar directory stays authoritative.

Without it the application still reads date, sensor and CRS from the GeoTIFF tags, but the
scene id, licence, source and pixel window never reach the provenance export.

    python write_metadata_json.py
"""

from __future__ import annotations

import json
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds

ARCHIVE = Path(__file__).resolve().parent.parent

# Keys the application reads off the sidecar, in app/main.py:
#   date / acquisition_date, sensor / platform,
#   bbox | footprint | geometry, and for the footprint record:
#   source_scene_id, source_path, source_sha256, pixel_window
KEEP = ("acquisition_date", "sensor", "platform", "licence", "source",
        "reflectance_formula", "boa_offset_applied", "crs", "gsd_m",
        "granule_cloud_cover_pct", "tile_cloud_shadow_pct", "quality_flag", "nodata_pct")


def build(tif_dir: Path, side_dir: Path) -> int:
    out = {}
    for tif in sorted(tif_dir.glob("*.tif")):
        sc = side_dir / f"{tif.stem}.json"
        if not sc.is_file():
            print(f"  no sidecar for {tif.name}")
            continue
        s = json.loads(sc.read_text(encoding="utf-8"))
        with rasterio.open(tif) as src:
            west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            shape = [src.width, src.height]
        rec = {k: s[k] for k in KEEP if k in s}
        rec["date"] = s.get("acquisition_date")
        rec["bbox"] = [round(v, 6) for v in (west, south, east, north)]
        rec["source_scene_id"] = s.get("scene_id")
        rec["source_path"] = s.get("stac_item")
        rec["pixel_window"] = {"width": shape[0], "height": shape[1],
                               "bounds_native": s.get("bounds_native")}
        out[tif.name] = rec
    if out:
        (tif_dir / "metadata.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return len(out)


total = 0
for folder in sorted(ARCHIVE.iterdir()):
    tif_dir, side_dir = folder / "sentinel2_l2a", folder / "sidecar"
    if not (tif_dir.is_dir() and side_dir.is_dir()):
        continue
    n = build(tif_dir, side_dir)
    if n:
        print(f"{folder.name:34s} {n} scenes -> metadata.json")
        total += n

print(f"\n{total} scenes described")
