"""Windowed, offline GeoTIFF tiles with source identity and georeferencing."""

import json
import hashlib
import threading
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class TileRequest(BaseModel):
    tile_size: int = Field(default=512, ge=128, le=2048)


def build_tiles(jid, rows, size):
    import rasterio
    from rasterio.windows import Window
    from app.main import DATA, jobs, _scan

    batch_key = hashlib.sha256(
        json.dumps([size, sorted(r["sha256"] for r in rows)]).encode()
    ).hexdigest()[:24]
    batch = DATA / "tiles" / batch_key
    batch.mkdir(parents=True, exist_ok=True)
    try:
        total = sum(
            ((r["width"] + size - 1) // size) * ((r["height"] + size - 1) // size)
            for r in rows
        )
        jobs[jid].update(state="scanning", total=total, done=0)
        for row in rows:
            with rasterio.open(row["path"]) as src:
                if not src.crs:
                    raise ValueError("Source GeoTIFF has no CRS")
                for y in range(0, src.height, size):
                    for x in range(0, src.width, size):
                        window = Window(
                            x, y, min(size, src.width - x), min(size, src.height - y)
                        )
                        # Stable tile identity permits provenance lookup and deduplication.
                        key = hashlib.sha256(
                            f"{row['sha256']}:{x}:{y}:{size}".encode()
                        ).hexdigest()[:24]
                        target = batch / (key + ".tif")
                        profile = src.profile.copy()
                        for option in ("blockxsize", "blockysize", "tiled"):
                            profile.pop(option, None)
                        profile.update(
                            driver="GTiff",
                            width=int(window.width),
                            height=int(window.height),
                            transform=src.window_transform(window),
                            compress="deflate",
                        )
                        with rasterio.open(target, "w", **profile) as dst:
                            dst.write(src.read(window=window))
                            dst.update_tags(**src.tags())
                        metadata = {
                            "date": row.get("date"),
                            "sensor": row.get("sensor"),
                            "source_scene_id": row["id"],
                            "source_path": row["path"],
                            "source_sha256": row["sha256"],
                            "pixel_window": [
                                x,
                                y,
                                int(window.width),
                                int(window.height),
                            ],
                            "operation": "GeoTIFF window extraction",
                        }
                        target.with_suffix(".json").write_text(
                            json.dumps(metadata), encoding="utf-8"
                        )
                        jobs[jid].update(
                            done=jobs[jid]["done"] + 1, current=target.name
                        )
        _scan(jid, str(batch))
    except Exception as exc:
        jobs[jid].update(state="failed", error=str(exc))


@router.post("/api/tiles/build")
def start_tiles(body: TileRequest):
    from app.main import conn, jobs, cluster_engine

    if cluster_engine.running or any(
        j.get("state") in {"queued", "scanning", "indexing"} for j in jobs.values()
    ):
        raise HTTPException(409, "Wait for current processing to finish")
    with conn() as c:
        rows = [
            dict(r)
            for r in c.execute(
                "select * from scenes where status='ready' and kind='GeoTIFF/COG'"
            )
            if r["width"] > body.tile_size or r["height"] > body.tile_size
        ]
    if not rows:
        raise HTTPException(400, "No GeoTIFF larger than the selected tile size")
    cluster_engine.clear()
    jid = uuid.uuid4().hex
    jobs[jid] = {
        "id": jid,
        "state": "queued",
        "total": 0,
        "done": 0,
        "current": "",
        "kind": "tiling",
    }
    threading.Thread(
        target=build_tiles, args=(jid, rows, body.tile_size), daemon=True
    ).start()
    return jobs[jid]
