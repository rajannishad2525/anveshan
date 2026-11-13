"""Offline measurement tools. Human judgments are never manufactured."""

from datetime import datetime, timezone
import hashlib
import json
import platform
import time
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import numpy as np

router = APIRouter()


class QuerySet(BaseModel):
    queries: list[str] = Field(min_length=10, max_length=15)


def archive_signature(rows):
    return hashlib.sha256(
        json.dumps([(r["id"], r["sha256"], r["imported_at"]) for r in rows]).encode()
    ).hexdigest()


def frozen_pool(body):
    from app.main import cluster_engine

    if cluster_engine.status.get("state") != "ready":
        raise HTTPException(409, "Build the local index and wait for READY first")
    queries = list(dict.fromkeys(q.strip() for q in body.queries if q.strip()))
    if len(queries) < 10:
        raise HTTPException(400, "Supply 10–15 distinct, nonempty evaluation queries")
    rows = cluster_engine.snapshot()
    signature = archive_signature(rows)
    pool = []
    for query in queries:
        result = cluster_engine.search(query, limit=10)
        pool.append(
            {
                "query": query,
                "results": [
                    {
                        "scene_id": r["id"],
                        "name": r["name"],
                        "sha256": r["sha256"],
                        "rank": i + 1,
                        "judge_a": None,
                        "judge_b": None,
                    }
                    for i, r in enumerate(result["results"])
                ],
            }
        )
    if signature != archive_signature(cluster_engine.snapshot()):
        raise HTTPException(409, "Archive changed during evaluation; freeze again")
    return {
        "schema": "anveshan-retrieval-judgments-v1",
        "archive_signature": signature,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "queries": pool,
        "note": "Two independent reviewers must judge relevance. Frozen top-10 pool; no recall claim.",
    }


@router.post("/api/evaluation/retrieval/freeze")
def freeze(body: QuerySet):
    from app.main import DATA

    data = frozen_pool(body)
    data["freeze_id"] = str(uuid.uuid4())
    directory = DATA / "evaluations"
    directory.mkdir(exist_ok=True)
    (directory / (data["freeze_id"] + ".json")).write_text(
        json.dumps(data), encoding="utf-8"
    )
    return data


class Judgment(BaseModel):
    query_index: int = Field(ge=0, le=14)
    scene_id: int
    judge_a: bool
    judge_b: bool


class Judgments(BaseModel):
    freeze_id: uuid.UUID
    reviewer_a: str = Field(min_length=1, max_length=120)
    reviewer_b: str = Field(min_length=1, max_length=120)
    judgments: list[Judgment] = Field(max_length=150)


def calculate_retrieval(pool, judgments):
    lookup = {(j.query_index, j.scene_id): j for j in judgments}
    expected = {
        (i, r["scene_id"]) for i, q in enumerate(pool["queries"]) for r in q["results"]
    }
    if len(lookup) != len(judgments) or set(lookup) != expected:
        raise ValueError(
            "Every frozen result needs exactly one judgment from each reviewer"
        )
    a = []
    b = []
    metrics = []
    for i, q in enumerate(pool["queries"]):
        labels = []
        for row in q["results"]:
            item = lookup[(i, row["scene_id"])]
            a.append(item.judge_a)
            b.append(item.judge_b)
            labels.append(item.judge_a if item.judge_a == item.judge_b else None)
        resolved = all(v is not None for v in labels)
        metrics.append(
            {
                "query": q["query"],
                "precision_at_5": sum(labels[:5]) / 5 if resolved else None,
                "precision_at_10": sum(labels[:10]) / 10 if resolved else None,
                "reciprocal_rank": (
                    next((1 / (j + 1) for j, v in enumerate(labels) if v), 0)
                    if resolved
                    else None
                ),
            }
        )
    kappa = None
    if a:
        pa = sum(a) / len(a)
        pb = sum(b) / len(b)
        chance = pa * pb + (1 - pa) * (1 - pb)
        agreement = sum(x == y for x, y in zip(a, b)) / len(a)
        if chance < 1:
            kappa = (agreement - chance) / (1 - chance)
    resolved = all(m["precision_at_5"] is not None for m in metrics)
    return {
        "status": (
            "scored"
            if resolved
            else "reviewer disagreements require independent adjudication"
        ),
        "cohen_kappa": kappa,
        "disagreements": sum(x != y for x, y in zip(a, b)),
        "precision_at_5": (
            float(np.mean([m["precision_at_5"] for m in metrics])) if resolved else None
        ),
        "precision_at_10": (
            float(np.mean([m["precision_at_10"] for m in metrics]))
            if resolved
            else None
        ),
        "mrr": (
            float(np.mean([m["reciprocal_rank"] for m in metrics]))
            if resolved
            else None
        ),
        "queries": metrics,
        "note": "Frozen pooled top-10 relevance evaluation. Not model probability calibration or an independent geography guarantee.",
    }


@router.post("/api/evaluation/retrieval/score")
def score(body: Judgments):
    from app.main import DATA, cluster_engine

    if body.reviewer_a.strip().casefold() == body.reviewer_b.strip().casefold():
        raise HTTPException(400, "Use two independent reviewers with different names")
    path = DATA / "evaluations" / (str(body.freeze_id) + ".json")
    if not path.exists():
        raise HTTPException(404, "Frozen query pool not found")
    pool = json.loads(path.read_text(encoding="utf-8"))
    if pool["archive_signature"] != archive_signature(cluster_engine.snapshot()):
        raise HTTPException(409, "The archive changed; freeze a new evaluation pool")
    try:
        result = calculate_retrieval(pool, body.judgments)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    result.update(
        freeze_id=str(body.freeze_id),
        reviewer_a=body.reviewer_a,
        reviewer_b=body.reviewer_b,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )
    return result


@router.post("/api/benchmark/current")
def benchmark():
    from app.main import cluster_engine, DATA, jobs

    if cluster_engine.status.get("state") != "ready":
        raise HTTPException(409, "Wait for the local index to be READY")
    rows = cluster_engine.snapshot()
    signature = archive_signature(rows)
    timings = []
    queries = [
        "river",
        "urban buildings",
        "agricultural fields",
        "roads",
        "water bodies",
    ]
    # Separate first request (potential cold model load) from warm requests.
    started = time.perf_counter()
    cluster_engine.search(queries[0], limit=10)
    first = time.perf_counter() - started
    for _ in range(3):
        for q in queries:
            started = time.perf_counter()
            cluster_engine.search(q, limit=10)
            timings.append(time.perf_counter() - started)
    if signature != archive_signature(cluster_engine.snapshot()):
        raise HTTPException(409, "Archive changed; run benchmark again")
    storage = sum(p.stat().st_size for p in DATA.rglob("*") if p.is_file())
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "archive_signature": signature,
        "scene_count": len(rows),
        "indexed_representatives": cluster_engine.status.get("accepted"),
        "tile_count": sum(
            bool(json.loads(r["footprint"]).get("pixel_window"))
            for r in rows
            if r.get("footprint") and isinstance(json.loads(r["footprint"]), dict)
        ),
        "archive_source_bytes": sum(r["bytes"] for r in rows),
        "data_directory_bytes_including_staged_sources": storage,
        "build_seconds": cluster_engine.status.get("build_seconds"),
        "last_completed_import_seconds": next(
            (
                j["elapsed_seconds"]
                for j in reversed(list(jobs.values()))
                if j.get("state") == "complete" and "elapsed_seconds" in j
            ),
            None,
        ),
        "covered_area_km2": None,
        "peak_process_ram_bytes": None,
        "platform": platform.platform(),
        "device": getattr(cluster_engine, "device", "unknown"),
        "first_query_seconds": first,
        "warm_query_count": len(timings),
        "warm_query_p50_seconds": float(np.percentile(timings, 50)),
        "warm_query_p95_seconds": float(np.percentile(timings, 95)),
        "note": "Measured on this archive and machine. Null means unmeasured. No 1k/10k-scene extrapolation. First request may already be warm.",
    }
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak_working_set",
                    "working_set",
                    "peak_paged",
                    "paged",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ]

        counter = Counters()
        counter.cb = ctypes.sizeof(counter)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        if psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counter), counter.cb
        ):
            result["peak_process_ram_bytes"] = counter.peak_working_set
        result["ram_scope"] = (
            "Process lifetime peak working set, not isolated benchmark allocation"
        )
    return result
