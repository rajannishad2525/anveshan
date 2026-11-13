"""Confounder signals read from the Sentinel-2 Scene Classification Layer.

The SCL band ships inside our L2A GeoTIFFs and already separates snow, cloud,
cloud shadow and water. It was being ignored: intake quality only looked at
band 1 brightness, so PS 2.2.3 confounders had no evidence behind them.

This is ESA's own per-pixel classification, not our own model. Treat it as a
triage signal: it is known to confuse bright snow with cloud over mountains.
"""
from __future__ import annotations

from pathlib import Path

# Sentinel-2 L2A SCL class codes.
SCL_CLASSES = {
    0: "no data",
    1: "saturated or defective",
    2: "dark area",
    3: "cloud shadow",
    4: "vegetation",
    5: "not vegetated",
    6: "water",
    7: "unclassified",
    8: "cloud medium probability",
    9: "cloud high probability",
    10: "thin cirrus",
    11: "snow or ice",
}

CLOUD = (8, 9, 10)
SHADOW = (2, 3)
SNOW = (11,)
WATER = (6,)
UNUSABLE = (0, 1)

# Fraction of the scene a confounder must cover before it is worth an
# analyst's attention. Below this it is speckle, not a scene-level problem.
FLAG_AT = 0.05


def scl_band_index(src) -> int | None:
    """Which 1-based band is the SCL, or None if this raster has no SCL."""
    for i, name in enumerate(src.descriptions or (), start=1):
        if name and name.strip().upper() == "SCL":
            return i
    return None


def sidecar_scl(path: Path) -> Path | None:
    """Some exports ship SCL as a separate file next to the visual raster."""
    stem = path.stem
    for suffix in ("_visual", "_rgb", ""):
        if suffix and not stem.endswith(suffix):
            continue
        candidate = path.with_name(stem[: len(stem) - len(suffix)] + "_scl" + path.suffix)
        if candidate.exists():
            return candidate
    return None


def scl_summary(path: str | Path, max_side: int = 512) -> dict:
    """Per-class coverage plus confounder flags. Empty dict when no SCL band."""
    import numpy as np
    import rasterio

    path = Path(path)
    with rasterio.open(path) as src:
        band = scl_band_index(src)
        if band is None:
            sidecar = sidecar_scl(path)
            if sidecar is None:
                return {"available": False, "reason": "no SCL band in this raster"}
            # A lone single-band raster named *_scl is the SCL itself.
            return scl_summary_from(sidecar, 1, max_side)
    return scl_summary_from(path, band, max_side)


def scl_summary_from(path: Path, band: int, max_side: int = 512) -> dict:
    import numpy as np
    import rasterio

    with rasterio.open(path) as src:
        scale = min(1.0, max_side / max(src.width, src.height))
        w, h = max(1, int(src.width * scale)), max(1, int(src.height * scale))
        # Nearest neighbour: SCL codes are labels, interpolating them is wrong.
        arr = src.read(band, out_shape=(h, w), resampling=rasterio.enums.Resampling.nearest)

    total = arr.size
    codes, counts = np.unique(arr, return_counts=True)
    coverage = {int(c): float(n) / total for c, n in zip(codes, counts)}

    def frac(group):
        return round(sum(coverage.get(c, 0.0) for c in group), 4)

    snow, cloud, shadow, water, unusable = (
        frac(SNOW), frac(CLOUD), frac(SHADOW), frac(WATER), frac(UNUSABLE))

    flags = []
    if snow >= FLAG_AT:
        flags.append(f"snow or ice covers {snow:.0%} (SCL 11)")
    if cloud >= FLAG_AT:
        flags.append(f"cloud covers {cloud:.0%} (SCL 8/9/10)")
    if shadow >= FLAG_AT:
        flags.append(f"shadow or dark area covers {shadow:.0%} (SCL 2/3)")
    if unusable >= FLAG_AT:
        flags.append(f"no-data or saturated pixels cover {unusable:.0%} (SCL 0/1)")

    return {
        "available": True,
        "source": "Sentinel-2 L2A Scene Classification Layer",
        "coverage": {SCL_CLASSES.get(c, str(c)): round(v, 4)
                     for c, v in sorted(coverage.items(), key=lambda kv: -kv[1])},
        "snow_fraction": snow,
        "cloud_fraction": cloud,
        "shadow_fraction": shadow,
        "water_fraction": water,
        "unusable_fraction": unusable,
        "valid_fraction": round(1.0 - unusable, 4),
        "flags": flags,
    }


def seasonality_signal(before: dict, after: dict) -> dict | None:
    """Vegetation swing between two dates, the usual cause of a false alarm.

    A large vegetation change with no built-up change is a seasonal cycle, not
    a physical change. This does not prove seasonality - it flags the pattern
    so the analyst is told why a candidate was down-weighted.
    """
    if not (before.get("available") and after.get("available")):
        return None
    veg = SCL_CLASSES[4]
    veg_before = before["coverage"].get(veg, 0.0)
    veg_after = after["coverage"].get(veg, 0.0)
    swing = round(abs(veg_after - veg_before), 4)
    return {
        "vegetation_before": veg_before,
        "vegetation_after": veg_after,
        "vegetation_swing": swing,
        "seasonal_suspect": swing >= 0.20,
        "note": "Vegetation swing is a seasonality hint, not a proof of no change.",
    }
