"""Registered local change screening. Outputs are candidates, not object labels."""

import cv2
import numpy as np
from PIL import Image
from app.place_matching import local_features, verify_place


def analyze(
    left,
    right,
    threshold=0.18,
    *,
    source_grid=None,
    left_valid=None,
    right_valid=None,
    typer=None,
):
    """Screen a registered pair for change.

    ``typer`` is optional. When a ``ChangeTyper`` is supplied, the largest
    candidate regions also receive a zero-shot land-cover change type and a
    directional form (PS 2.2.2). Typing never decides whether a region is a
    candidate, and a failure inside it degrades to the untyped result rather
    than losing the screening.
    """
    proof = (
        {
            "matched": True,
            "method": "declared identical source GeoTIFF grid",
            "homography": np.eye(3).tolist(),
            "source_grid": source_grid,
            "note": "Source grid agreement; independent geolocation accuracy is not measured.",
        }
        if source_grid and source_grid.get("verified") and left.shape == right.shape
        else verify_place(
            local_features(Image.fromarray(right)),
            local_features(Image.fromarray(left)),
        )
    )
    if not proof["matched"]:
        raise ValueError(
            "Image registration could not be verified; no change conclusion is available"
        )
    h, w = left.shape[:2]
    matrix = np.asarray(proof["homography"])
    aligned = cv2.warpPerspective(right, matrix, (w, h))
    right_valid = (
        np.ones(right.shape[:2], np.uint8)
        if right_valid is None
        else right_valid.astype(np.uint8)
    )
    valid = cv2.warpPerspective(
        right_valid, matrix, (w, h), flags=cv2.INTER_NEAREST
    ).astype(bool)
    if left_valid is not None:
        valid &= left_valid
    # Exclude interpolation edges from the common footprint.
    valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    from app.main import _false_alarm_signals

    nuisance = _false_alarm_signals(left, aligned)
    usable = valid & ~nuisance["candidate_mask"]
    if usable.mean() < 0.25:
        raise ValueError("Insufficient usable overlap after quality screening")
    # Robust additive colour correction with bounded gains on common pixels.
    normalized = aligned.astype(np.float32)
    adjustments = []
    for channel in range(3):
        a = left[:, :, channel][usable].astype(float)
        b = normalized[:, :, channel][usable]
        spread_a = np.percentile(a, 75) - np.percentile(a, 25)
        spread_b = np.percentile(b, 75) - np.percentile(b, 25)
        gain = float(np.clip(spread_a / max(spread_b, 1), 0.8, 1.25))
        offset = float(np.clip(np.median(a) - gain * np.median(b), -30, 30))
        normalized[:, :, channel] = normalized[:, :, channel] * gain + offset
        adjustments.append({"gain": gain, "offset": offset})
    normalized = np.clip(normalized, 0, 255)
    delta = np.abs(left.astype(float) - normalized).max(axis=2) / 255
    changed = (delta >= threshold) & usable
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        changed.astype(np.uint8), 8
    )
    regions = []
    for x, y, rw, rh, area in stats[1:]:
        if area < 9:
            continue
        regions.append(
            {
                "bbox_pixels": [int(x), int(y), int(x + rw), int(y + rh)],
                "changed_pixels": int(area),
                "coordinate_space": "analysis image pixels",
            }
        )
    regions.sort(key=lambda r: -r["changed_pixels"])
    # Only the 100 largest are drawn; the count must still be the real one.
    region_total = len(regions)
    regions = regions[:100]

    typing = None
    if typer is not None and regions:
        try:
            typing = typer.type_regions(
                left.astype(np.uint8), normalized.astype(np.uint8), regions
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            typing = {
                "error": f"{type(exc).__name__}: {exc}",
                "note": "Change typing failed; regions remain untyped candidates.",
            }

    classification = "unclassified visual change"
    if typing and typing.get("dominant_type"):
        classification = typing["dominant_type"]

    return {
        "analysis_status": "registered visual screening",
        "registration": proof,
        "normalization": {
            "method": "bounded robust per-channel affine correction",
            "channels": adjustments,
        },
        "usable_fraction": round(float(usable.mean()), 4),
        "adjusted_changed_pixel_ratio": round(float(changed.sum() / usable.sum()), 4),
        "regions": regions,
        "region_count": region_total,
        "regions_listed": len(regions),
        "analysis_size": {"width": w, "height": h},
        "threshold": threshold,
        "quality_flags": nuisance["flags"],
        "classification": classification,
        "change_typing": typing,
        "note": "Changes are candidates; seasonal effects and RGB quality heuristics need review.",
    }
