"""Offline instance/place matching; dates and filenames never score a match."""

import cv2
import numpy as np
import re
from pathlib import Path


def period_info(path, declared=None):
    """Preserve folder periods, without claiming an exact capture timestamp."""
    if declared and re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.*)?", declared):
        return {
            "period_label": declared,
            "period_start": declared,
            "period_source": "imported metadata",
        }
    label = Path(path).parent.name
    if re.fullmatch(r"20\d{2}(?:[-_]\d{2,4})*", label):
        values = label.replace("_", "-").split("-")
        years = [int(v) if len(v) == 4 else int(values[0][:2] + v) for v in values]
        return {
            "period_label": (
                str(min(years))
                if min(years) == max(years)
                else f"{min(years)}–{max(years)}"
            ),
            "period_start": str(min(years)),
            "period_source": f"folder: {label}",
        }
    return {
        "period_label": declared or "date unavailable",
        "period_start": declared or "9999",
        "period_source": "imported metadata" if declared else "unknown",
    }


def local_features(image):
    gray = np.asarray(image.convert("L"))
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    h, w = gray.shape
    mask = np.zeros_like(gray)
    # Ignore common tile-edge labels/watermarks rather than matching their text.
    mask[
        max(1, h // 20) : h - max(1, h // 20), max(1, w // 20) : w - max(1, w // 20)
    ] = 255
    keys, desc = cv2.SIFT_create(
        nfeatures=1600, contrastThreshold=0.02
    ).detectAndCompute(gray, mask)
    points = np.array([k.pt for k in keys], dtype="float32").reshape(-1, 2)
    if desc is not None:
        desc = np.sqrt(desc / np.maximum(desc.sum(axis=1, keepdims=True), 1e-8))
    return points, desc, (w, h)


def verify_place(left, right):
    """Mutual RootSIFT ratio matches, RANSAC, spatial coverage and overlap."""
    a, da, sizea = left
    b, db, sizeb = right
    fail = {"matched": False, "method": "RootSIFT + RANSAC"}
    if da is None or db is None or min(len(da), len(db)) < 12:
        return fail
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    def ratios(x, y):
        return {
            pair[0].queryIdx: pair[0].trainIdx
            for pair in matcher.knnMatch(x, y, k=2)
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance
        }

    forward, backward = ratios(da, db), ratios(db, da)
    pairs = [(i, j) for i, j in forward.items() if backward.get(j) == i]
    if len(pairs) < 12:
        return fail
    src = np.float32([a[i] for i, j in pairs])
    dst = np.float32([b[j] for i, j in pairs])
    cv2.setRNGSeed(7)
    H, mask = cv2.findHomography(
        src, dst, cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995
    )
    if H is None or mask is None or not np.isfinite(H).all():
        return fail
    good = mask.ravel().astype(bool)
    n = int(good.sum())
    ratio = n / len(pairs)
    covera = (
        cv2.contourArea(cv2.convexHull(src[good])) / (sizea[0] * sizea[1])
        if n >= 3
        else 0
    )
    coverb = (
        cv2.contourArea(cv2.convexHull(dst[good])) / (sizeb[0] * sizeb[1])
        if n >= 3
        else 0
    )
    corners = np.float32([[0, 0], [sizea[0], 0], sizea, [0, sizea[1]]]).reshape(
        -1, 1, 2
    )
    quad = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
    if not cv2.isContourConvex(quad):
        return fail
    area = abs(cv2.contourArea(quad))
    target = sizeb[0] * sizeb[1]
    rectangle = np.float32([[0, 0], [sizeb[0], 0], sizeb, [0, sizeb[1]]])
    intersection = cv2.intersectConvexConvex(quad, rectangle)[0]
    overlap = intersection / max(area + target - intersection, 1)
    matched = (
        n >= 12
        and ratio >= 0.5
        and min(covera, coverb) >= 0.12
        and overlap >= 0.6
        and 0.4 <= area / target <= 2.5
    )
    return {
        "matched": bool(matched),
        "method": "RootSIFT + RANSAC",
        "inliers": n,
        "inlier_fraction": round(ratio, 4),
        "coverage": round(min(covera, coverb), 4),
        "overlap": round(overlap, 4),
        "homography": H.tolist() if matched else None,
    }


def group_places(scenes, vectors, features, compatible, use_geometry=True):
    """Retrieve broadly, then join verified same-place links; no colour cutoff.

    Geographic buckets add candidates even when appearance changes drastically.
    Unknown-location images require structural evidence. Each accepted merge is
    checked for contradictory known footprints across the combined group.
    """
    import faiss

    count = len(scenes)
    if not count:
        return [], [], []
    # A callable lets the caller compute RootSIFT only for the pairs that reach
    # verify_place; a plain sequence still works for tests and direct callers.
    feature = features if callable(features) else features.__getitem__
    x = np.ascontiguousarray(vectors, dtype="float32")
    faiss.normalize_L2(x)
    index = faiss.IndexHNSWFlat(x.shape[1], 32, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efSearch = 128
    index.add(x)
    _, neighbours = index.search(x, min(64, count))
    candidates = {
        (min(i, int(j)), max(i, int(j)))
        for i, row in enumerate(neighbours)
        for j in row
        if j >= 0 and j != i
    }
    buckets = {}
    if use_geometry:
        for i, s in enumerate(scenes):
            geo = s.get("geometry")
            if geo:
                key = (geo["crs"], tuple(round(v, 6) for v in geo["bounds"]))
                buckets.setdefault(key, []).append(i)
        for members in buckets.values():
            candidates.update((members[0], i) for i in members[1:])
    edges = []
    for i, j in sorted(candidates):
        a, b = scenes[i], scenes[j]
        if use_geometry and not compatible(a, b):
            continue
        if use_geometry and a.get("geometry") and b.get("geometry"):
            proof = {"matched": True, "method": "embedded footprint agreement"}
        else:
            proof = verify_place(feature(i), feature(j))
        if proof["matched"]:
            edges.append((i, j, proof))
    # Process stronger geographic edges first; then verified structural edges.
    edges.sort(
        key=lambda e: (
            e[2]["method"] != "embedded footprint agreement",
            -e[2].get("inliers", 0),
            e[0],
            e[1],
        )
    )
    parent = list(range(count))
    members = {i: [i] for i in range(count)}
    accepted = []

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j, proof in edges:
        ra, rb = root(i), root(j)
        if ra == rb:
            continue
        if use_geometry and not all(
            compatible(scenes[a], scenes[b]) for a in members[ra] for b in members[rb]
        ):
            continue
        parent[rb] = ra
        members[ra] += members.pop(rb)
        accepted.append((i, j, proof))
    return (
        [sorted(v) for v in members.values() if len(v) > 1],
        [v[0] for v in members.values() if len(v) == 1],
        accepted,
    )
