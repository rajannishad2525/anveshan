"""Fetch Sentinel-2 L2A tiles for an ANVESHAN AOI, straight from the public COG archive.

No login, no API key. Reads a windowed 1024x1024 crop out of each Cloud Optimized
GeoTIFF over HTTPS, so one date costs ~5 MB instead of ~800 MB for the full granule.

Every output carries what the PS asks for and the current archive lacks:
  - a real acquisition date (PS 2.2.2)
  - a near-infrared band, B08 (PS 2.2.3)
  - an embedded CRS (PS 2.2.6)
  - a declared sensor (PS 2.2.6)
  - an SCL scene-classification band -> a real cloud mask, not an RGB heuristic

Usage:
    python fetch_sentinel2.py --aoi 7
    python fetch_sentinel2.py --aoi 7 --start 2024-01-01 --end 2024-12-31 --dates 8
    python fetch_sentinel2.py --aoi 7 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("VSI_CACHE", "TRUE")

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.warp import transform as warp_transform  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

ARCHIVE = Path(__file__).resolve().parent.parent
STAC = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"

# 10 m bands the brief names, plus the scene-classification layer (20 m, resampled on read)
BANDS = [("blue", "B02"), ("green", "B03"), ("red", "B04"), ("nir", "B08"), ("scl", "SCL")]

TILE_PX = 1024
GSD_M = 10.0

LICENCE = "Copernicus Sentinel data, free and open (CC BY-SA 3.0 IGO)"
SOURCE = "Copernicus Sentinel-2 L2A via AWS Open Data (sentinel-cogs), catalogued by earth-search"


def load_aois() -> dict[int, dict]:
    out = {}
    with open(ARCHIVE / "AOI-INDEX.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[int(row["n"])] = row
    return out


def stac_search(lat: float, lon: float, start: str, end: str, max_cloud: int) -> list[dict]:
    d = 0.02  # ~2 km, comfortably inside one granule
    body = {
        "collections": [COLLECTION],
        "bbox": [lon - d, lat - d, lon + d, lat + d],
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 200,
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        # Trim the response: the full item carries 36 assets we never open.
        "fields": {
            "include": [
                "id",
                "properties.datetime",
                "properties.eo:cloud_cover",
                "properties.proj:epsg",
                "properties.platform",
                "properties.s2:processing_baseline",
                "properties.earthsearch:boa_offset_applied",
                *[f"assets.{k}.href" for k, _ in BANDS],
            ],
            "exclude": ["geometry", "bbox", "links", "collection", "stac_extensions"],
        },
    }
    req = urllib.request.Request(
        STAC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["features"]
        except Exception as e:  # transient TLS/read timeouts are common here
            last = e
            print(f"  catalogue attempt {attempt + 1} failed ({type(e).__name__}), retrying")
    raise RuntimeError(f"STAC search failed after 4 attempts: {last}")


def pick_dates(feats: list[dict], n_clear: int, n_hazy: int) -> list[dict]:
    """Spread clear scenes across the window, then deliberately add hazy ones.

    The brief is explicit: keep 2-3 hazy or partly clouded scenes per AOI, because
    false-alarm suppression (PS 2.2.3) cannot be demonstrated on clear imagery alone.
    """
    clear = [f for f in feats if f["properties"]["eo:cloud_cover"] < 10]
    hazy = [f for f in feats if 20 <= f["properties"]["eo:cloud_cover"] < 70]

    def spread(items, k):
        if not items or k <= 0:
            return []
        if len(items) <= k:
            return items
        step = (len(items) - 1) / (k - 1) if k > 1 else 0
        return [items[round(i * step)] for i in range(k)]

    chosen = spread(clear, n_clear) + spread(hazy, n_hazy)
    return sorted(chosen, key=lambda f: f["properties"]["datetime"])


def centre_bounds(lat: float, lon: float, epsg: int) -> tuple[float, float, float, float]:
    xs, ys = warp_transform("EPSG:4326", f"EPSG:{epsg}", [lon], [lat])
    half = TILE_PX * GSD_M / 2.0
    return xs[0] - half, ys[0] - half, xs[0] + half, ys[0] + half


def fetch_scene(feat: dict, lat: float, lon: float, out_tif: Path) -> dict:
    epsg = feat["properties"]["proj:epsg"]
    left, bottom, right, top = centre_bounds(lat, lon, epsg)

    stack, profile = [], None
    for key, label in BANDS:
        href = feat["assets"][key]["href"]
        url = href.replace("https://sentinel-cogs.s3.us-west-2.amazonaws.com",
                           "/vsicurl/https://sentinel-cogs.s3.us-west-2.amazonaws.com")
        with rasterio.open(url) as src:
            win = from_bounds(left, bottom, right, top, transform=src.transform)
            arr = src.read(1, window=win, out_shape=(TILE_PX, TILE_PX), boundless=True, fill_value=0)
            if profile is None:
                profile = {
                    "driver": "GTiff",
                    "height": TILE_PX,
                    "width": TILE_PX,
                    "count": len(BANDS),
                    "dtype": "uint16",
                    "crs": rasterio.crs.CRS.from_epsg(epsg),
                    "transform": rasterio.transform.from_bounds(
                        left, bottom, right, top, TILE_PX, TILE_PX
                    ),
                    "compress": "deflate",
                    "predictor": 2,
                    "tiled": True,
                    "blockxsize": 512,
                    "blockysize": 512,
                }
        stack.append(arr.astype("uint16"))
        print(f"      {label:4s} ok  min={int(arr.min()):5d} max={int(arr.max()):5d}")

    p = feat["properties"]
    # Reflectance convention, verified empirically against deep water on 2026-09-13:
    # NIR DN over Sardar Sarovar reads ~0 on a baseline-02.14 scene and ~359 on a
    # baseline-05.10 scene, not ~1000. The -1000 BOA_ADD_OFFSET is therefore ALREADY
    # applied in the sentinel-cogs pixels. Reflectance = DN * 0.0001, nothing subtracted.
    # Subtracting it again drives red negative and inflates NDVI from 0.17 to 0.65.
    boa_applied = bool(p.get("earthsearch:boa_offset_applied", True))
    with rasterio.open(out_tif, "w", **profile) as dst:
        for i, band in enumerate(stack, start=1):
            dst.write(band, i)
            dst.set_band_description(i, BANDS[i - 1][1])
        dst.update_tags(
            TIFFTAG_DATETIME=p["datetime"],
            ACQUISITION_DATE=p["datetime"][:10],
            SENSOR="Sentinel-2 MSI",
            PLATFORM=p.get("platform", ""),
            SOURCE=SOURCE,
            LICENCE=LICENCE,
            SCENE_ID=feat["id"],
            CLOUD_COVER=str(p.get("eo:cloud_cover")),
            PROCESSING_BASELINE=str(p.get("s2:processing_baseline", "")),
            BOA_OFFSET_APPLIED=str(boa_applied),
            REFLECTANCE_SCALE="0.0001",
            REFLECTANCE_FORMULA="reflectance = DN * 0.0001  (do NOT subtract 1000)",
        )

    scl = stack[4]
    # SCL classes 8,9,10 = cloud medium, cloud high, thin cirrus; 3 = cloud shadow
    cloudy_px = int(np.isin(scl, [3, 8, 9, 10]).sum())
    # SCL 0 = nodata. A tile near a granule edge comes back mostly empty; the STAC bbox
    # match only proves the centre is inside the footprint, not the whole 10 km tile.
    nodata_px = int((scl == 0).sum())
    cc = float(p.get("eo:cloud_cover", 0.0))
    return {
        "nodata_pct": round(100.0 * nodata_px / (TILE_PX * TILE_PX), 3),
        "scene_id": feat["id"],
        "datetime": p["datetime"],
        "acquisition_date": p["datetime"][:10],
        "sensor": "Sentinel-2 MSI",
        "platform": p.get("platform"),
        "bands": [b for _, b in BANDS],
        "band_index": {b: i + 1 for i, (_, b) in enumerate(BANDS)},
        "gsd_m": GSD_M,
        "processing_baseline": p.get("s2:processing_baseline"),
        "boa_offset_applied": boa_applied,
        "reflectance_scale": 0.0001,
        "reflectance_formula": "reflectance = DN * 0.0001 (do NOT subtract 1000)",
        "crs": f"EPSG:{epsg}",
        "tile_size_px": TILE_PX,
        "bounds_native": [left, bottom, right, top],
        "centre_lonlat": [lon, lat],
        "granule_cloud_cover_pct": cc,
        "tile_cloud_shadow_px": cloudy_px,
        "tile_cloud_shadow_pct": round(100.0 * cloudy_px / (TILE_PX * TILE_PX), 3),
        "quality_flag": "clear" if cc < 10 else ("hazy" if cc < 40 else "partly_clouded"),
        "source": SOURCE,
        "licence": LICENCE,
        "stac_item": f"https://earth-search.aws.element84.com/v1/collections/{COLLECTION}/items/{feat['id']}",
        "download_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", type=int, required=True, help="AOI number from AOI-INDEX.csv")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--dates", type=int, default=6, help="clear scenes to keep")
    ap.add_argument("--hazy", type=int, default=2, help="hazy/clouded scenes to keep on purpose")
    ap.add_argument("--max-cloud", type=int, default=70)
    ap.add_argument("--max-nodata", type=float, default=2.0,
                    help="reject a tile with more than this %% nodata (granule edge)")
    ap.add_argument("--out", default=None, help="override output dir (used for the held-out set)")
    ap.add_argument("--prefix", default=None,
                    help="filename prefix instead of AOInn (e.g. HELDOUT)")
    ap.add_argument("--centre", default=None, metavar="LAT,LON",
                    help="override the AOI centre without editing AOI-INDEX.csv; "
                         "used for the held-out Punjab patch, which must not reuse AOI 07 pixels")
    ap.add_argument("--dry-run", action="store_true", help="list what would be downloaded")
    a = ap.parse_args()

    aois = load_aois()
    if a.aoi not in aois:
        print(f"AOI {a.aoi} not in AOI-INDEX.csv", file=sys.stderr)
        return 1
    aoi = aois[a.aoi]
    if a.centre:
        lat, lon = (float(v) for v in a.centre.split(","))
    else:
        lat, lon = float(aoi["centre_lat"]), float(aoi["centre_lon"])

    print(f"AOI {a.aoi:02d}  {aoi['location']}   {lat}N {lon}E   [{aoi['set']}]")
    print(f"window {a.start} .. {a.end}\n")

    feats = stac_search(lat, lon, a.start, a.end, a.max_cloud)
    print(f"catalogue returned {len(feats)} scenes under {a.max_cloud}% cloud")

    chosen = pick_dates(feats, a.dates, a.hazy)
    print(f"selected {len(chosen)}: "
          f"{sum(1 for f in chosen if f['properties']['eo:cloud_cover'] < 10)} clear, "
          f"{len(chosen) - sum(1 for f in chosen if f['properties']['eo:cloud_cover'] < 10)} hazy\n")

    base = Path(a.out) if a.out else ARCHIVE / aoi["folder"]
    tif_dir, side_dir = base / "sentinel2_l2a", base / "sidecar"

    if a.dry_run:
        for f in chosen:
            p = f["properties"]
            cc = p["eo:cloud_cover"]
            flag = "clear" if cc < 10 else ("hazy" if cc < 40 else "partly_clouded")
            print(f"  {p['datetime'][:10]}_s2_{flag}.tif   cloud={cc:.2f}%  {f['id']}")
        print("\ndry run - nothing written")
        return 0

    tif_dir.mkdir(parents=True, exist_ok=True)
    side_dir.mkdir(parents=True, exist_ok=True)

    # Reserve pool, so a scene rejected for granule-edge nodata can be replaced rather
    # than silently shrinking the date count.
    picked_ids = {f["id"] for f in chosen}
    reserve = [f for f in feats if f["id"] not in picked_ids]
    queue, kept, rejected = list(chosen), 0, 0

    while queue:
        f = queue.pop(0)
        p = f["properties"]
        date, cc = p["datetime"][:10], p["eo:cloud_cover"]
        flag = "clear" if cc < 10 else ("hazy" if cc < 40 else "partly_clouded")
        # AOI prefix is not decoration. Scanned into the application, scenes are listed by
        # filename alone, and two AOIs imaged on the same date produce byte-identical names
        # - an operator could pair Ludhiana with Leh without noticing.
        name = f"{a.prefix or f'AOI{a.aoi:02d}'}_{date}_s2_{flag}"
        # Adjacent orbits can image the same point on the same day, producing two scenes
        # that reduce to one filename. Left alone, the second one overwrites the first,
        # and if the second is then rejected for granule-edge nodata its unlink() deletes
        # the good tile too, leaving a sidecar with no raster. Disambiguate instead.
        if (tif_dir / f"{name}.tif").exists():
            for suffix in "bcdefgh":
                if not (tif_dir / f"{name}{suffix}.tif").exists():
                    name = f"{name}{suffix}"
                    break
        out_tif = tif_dir / f"{name}.tif"
        print(f"  {name}.tif   cloud={cc:.2f}%  {f['id']}")

        meta = fetch_scene(f, lat, lon, out_tif)
        if meta["nodata_pct"] > a.max_nodata:
            print(f"      REJECTED: {meta['nodata_pct']:.1f}% nodata "
                  f"(granule edge, tile not fully covered)")
            out_tif.unlink(missing_ok=True)
            rejected += 1
            if reserve:
                # Replace with the reserve scene CLOSEST IN TIME to the one just rejected.
                # Taking the head of the list instead would pile every substitution into
                # whichever month happens to sort first, collapsing the temporal spread
                # that "6-8 dates spanning before, during and after" depends on.
                want = p["datetime"][:10]
                nxt = min(reserve, key=lambda g: abs(
                    (datetime.fromisoformat(g["properties"]["datetime"][:10])
                     - datetime.fromisoformat(want)).days))
                reserve.remove(nxt)
                print(f"      substituting {nxt['properties']['datetime'][:10]} "
                      f"(nearest in time to {want})")
                queue.append(nxt)
            continue

        meta["aoi"] = {"index": a.aoi, "slug": aoi["folder"], "centre_lat": lat, "centre_lon": lon}
        meta["ps_clause"] = aoi["ps_clause"]
        (side_dir / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        kept += 1

    print(f"\nkept {kept} scenes in {tif_dir}" + (f", rejected {rejected} on nodata" if rejected else ""))
    if kept == 0:
        print("NOTHING USABLE. The AOI centre is probably on a granule edge - move it, "
              "or widen the date window.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
