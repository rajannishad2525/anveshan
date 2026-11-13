"""Render a contact sheet from an AOI's Sentinel-2 tiles: true colour over NDVI.

Quick visual proof that an AOI actually shows what the brief claims it shows.

    python make_contact_sheet.py --aoi 7
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import rasterio

ARCHIVE = Path(__file__).resolve().parent.parent


def stretch(a: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    lo, hi = np.percentile(a, [lo_pct, hi_pct])
    if hi <= lo:
        return np.zeros_like(a, dtype="u1")
    return (np.clip((a - lo) / (hi - lo), 0, 1) * 255).astype("u1")


def ndvi_rgb(nd: np.ndarray) -> np.ndarray:
    """Brown (bare) -> yellow -> green (vegetated). Diverging around 0.2."""
    t = np.clip((nd + 0.1) / 0.9, 0, 1)
    r = np.clip(1.6 - 2.0 * t, 0.15, 0.75)
    g = np.clip(0.25 + 0.75 * t, 0.2, 0.95)
    b = np.clip(0.35 - 0.3 * t, 0.05, 0.4)
    return (np.dstack([r, g, b]) * 255).astype("u1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", type=int, required=True)
    ap.add_argument("--thumb", type=int, default=256)
    a = ap.parse_args()

    with open(ARCHIVE / "AOI-INDEX.csv", encoding="utf-8") as f:
        aoi = {int(r["n"]): r for r in csv.DictReader(f)}[a.aoi]

    tifs = sorted((ARCHIVE / aoi["folder"] / "sentinel2_l2a").glob("*.tif"))
    if not tifs:
        print("no tiles; run fetch_sentinel2.py first")
        return 1

    t, n = a.thumb, len(tifs)
    sheet = np.zeros((t * 2, t * n, 3), dtype="u1")
    step = None

    for i, p in enumerate(tifs):
        with rasterio.open(p) as s:
            step = max(1, s.width // t)
            b, g, r, nir = (s.read(k)[::step, ::step][:t, :t].astype("f8") for k in (1, 2, 3, 4))
        rgb = np.dstack([stretch(r), stretch(g), stretch(b)])
        nd = (nir - r) / (nir + r + 1e-9)
        sheet[0:t, i*t:(i+1)*t] = rgb
        sheet[t:2*t, i*t:(i+1)*t] = ndvi_rgb(nd)
        print(f"  {p.name}   NDVI median {np.median(nd):+.2f}")

    # Deliberately outside the archive. The application's folder scan accepts PNG and
    # walks recursively, so a preview left beside the rasters is ingested as if it were
    # a scene - a derived picture with no date, no CRS and no sensor, sitting in the
    # library next to real ones.
    out_dir = ARCHIVE.parent / "imagery_archive_previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{aoi['folder']}_contact_sheet.png"
    with rasterio.open(out, "w", driver="PNG", height=sheet.shape[0], width=sheet.shape[1],
                       count=3, dtype="uint8") as dst:
        for k in range(3):
            dst.write(sheet[:, :, k], k + 1)
    print(f"\ntop row: true colour, bottom row: NDVI (brown = bare, green = vegetated)")
    print(f"left to right, oldest first: {', '.join(p.name[:10] for p in tifs)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
