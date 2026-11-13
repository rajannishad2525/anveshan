from __future__ import annotations

import hashlib
import json
import mimetypes
import csv
import sqlite3
import threading
import uuid
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
from app.semantic_clusters import ClusterEngine, compatible_footprints, read_rgb
from app.spatial import filter_rows, parse_bbox, parse_date_filter
from app.spectral import scl_summary, seasonality_signal

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ANVESHAN_DATA_DIR", str(ROOT / "datasets"))).resolve()
DB_PATH = DATA / "library.sqlite3"
WEB = ROOT / "web"
DATA.mkdir(parents=True, exist_ok=True)
MAX_MANIFEST_BYTES = 10 * 1024 * 1024
MAX_MANIFEST_ROWS = 10_000

app = FastAPI(title="ANVESHAN Offline Analyst Workstation")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
jobs: dict[str, dict] = {}
lock = threading.Lock()
# Injected by the native desktop launcher. Browser/dev-server mode keeps this
# unset and receives a clear typed-path fallback instead of pretending to open
# a native dialog.
NATIVE_FOLDER_PICKER = None

SCHEMA = """CREATE TABLE IF NOT EXISTS scenes(
 id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 kind TEXT NOT NULL, bytes INTEGER NOT NULL, width INTEGER, height INTEGER,
 bands INTEGER, crs TEXT, date TEXT, sensor TEXT, status TEXT NOT NULL,
 sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, error TEXT, footprint TEXT);
CREATE TABLE IF NOT EXISTS scene_index(
 scene_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
 encoder TEXT NOT NULL, indexed_at TEXT NOT NULL,
 FOREIGN KEY(scene_id) REFERENCES scenes(id))
"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        c.execute("alter table scenes add column footprint text")
    except sqlite3.OperationalError:
        pass
    c.commit()
    return c


def _visual_fingerprint(path: str) -> str:
    """Deterministic local thumbnail histogram; not a semantic embedding."""
    # read_rgb, not Image.open: PIL cannot decode multi-band uint16 GeoTIFFs,
    # which is most of a real Sentinel-2 archive, and read_rgb falls back to
    # rasterio. Opening with PIL alone left every such scene unindexed.
    pixels = list(read_rgb(path).resize((32, 32)).getdata())
    bins = []
    for channel in range(3):
        hist = [0] * 16
        for px in pixels:
            hist[px[channel] // 16] += 1
        bins.extend(round(v / len(pixels), 6) for v in hist)
    return json.dumps(bins, separators=(",", ":"))


def _cosine_similarity(left: str, right: str) -> float:
    """Compare two local histogram fingerprints without a model claim."""
    a, b = json.loads(left), json.loads(right)
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _build_index(job_id: str):
    try:
        c = conn()
        rows = c.execute(
            # Also re-index anything stamped with an older encoder, so an
            # archive is never a silent mix of two fingerprint versions.
            "select s.id,s.path from scenes s left join scene_index i on i.scene_id=s.id"
            " where s.status='ready' and (i.scene_id is null or i.encoder<>?)",
            ("local-thumbnail-histogram-v2",),
        ).fetchall()
        jobs[job_id].update(total=len(rows), state="indexing")
        workers = max(2, min(32, (os.cpu_count() or 4) * 2))
        done = 0
        batch = []

        def make_fp(row):
            try:
                return row["id"], _visual_fingerprint(row["path"]), None
            except Exception as exc:
                return row["id"], None, str(exc)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for scene_id, fp, error in pool.map(make_fp, rows):
                done += 1
                if error:
                    jobs[job_id].setdefault("errors", []).append(
                        {"scene_id": scene_id, "error": error}
                    )
                else:
                    batch.append(
                        (
                            scene_id,
                            fp,
                            "local-thumbnail-histogram-v2",
                            datetime.now(timezone.utc).isoformat(),
                        )
                    )
                if len(batch) >= 128:
                    c.executemany(
                        "insert into scene_index(scene_id,fingerprint,encoder,indexed_at) values(?,?,?,?) on conflict(scene_id) do update set fingerprint=excluded.fingerprint,encoder=excluded.encoder,indexed_at=excluded.indexed_at",
                        batch,
                    )
                    c.commit()
                    batch = []
                jobs[job_id].update(done=done, current=str(scene_id))
        if batch:
            c.executemany(
                "insert into scene_index(scene_id,fingerprint,encoder,indexed_at) values(?,?,?,?) on conflict(scene_id) do update set fingerprint=excluded.fingerprint,encoder=excluded.encoder,indexed_at=excluded.indexed_at",
                batch,
            )
        c.commit()
        c.close()
        failed = len(jobs[job_id].get("errors") or [])
        indexed = jobs[job_id].get("total", 0) - failed
        if not rows:
            # Nothing pending is a finished index, not a failed build.
            jobs[job_id].update(state="complete", current="", indexed=0, error=None,
                                message="Index already up to date; nothing new to index")
            return
        # "complete" next to 24 errors and 0 indexed scenes reads as success.
        jobs[job_id].update(
            state="complete" if indexed else "failed",
            current="",
            indexed=indexed,
            error=None if indexed else f"No scene could be indexed; {failed} failed",
        )
    except Exception as exc:
        jobs[job_id].update(state="failed", error=str(exc))


def _footprint_relation(before: str | None, after: str | None) -> str:
    """Whether two scenes actually cover the same ground.

    This used to answer "verified by matching footprint" whenever both scenes
    merely had a footprint, without ever comparing them, so two AOIs 150 km
    apart came back verified.
    """
    if not before or not after:
        return "unverified: footprint missing"
    try:
        geo_before, geo_after = json.loads(before), json.loads(after)
    except (TypeError, ValueError):
        return "unverified: footprint unreadable"
    if compatible_footprints({"geometry": geo_before}, {"geometry": geo_after}):
        return "verified by matching footprint"
    return "different ground area"


def _file_kind(p: Path) -> str | None:
    if p.suffix.lower() in {".tif", ".tiff", ".cog"}:
        return "GeoTIFF/COG"
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return "Raster image"
    return None


# Bump when _inspect changes what it records; re-import then re-inspects files.
INTAKE_VERSION = "intake-2"


def _date_from_name(stem: str) -> str | None:
    """A real calendar date written in the file name (2024-01-04 or 20240104)."""
    for y, m, d in re.findall(
        r"(?<![0-9])(20\d{2})[-_]?(\d{2})[-_]?(\d{2})(?![0-9])", stem
    ):
        try:
            return datetime(int(y), int(m), int(d)).date().isoformat()
        except ValueError:
            continue
    return None


def _period_from_folder(name: str) -> str | None:
    """Year or year range from a period folder: '2017', '2016-2012', and the
    Bhuvan shorthand '2021-19' (= 2019 to 2021)."""
    years = {int(y) for y in re.findall(r"(?<![0-9a-zA-Z])20\d{2}(?![0-9])", name)}
    for full, short in re.findall(r"(?<![0-9])(20\d{2})-(\d{2})(?![0-9])", name):
        years.add(int(full[:2] + short))
    if not years:
        return None
    lo, hi = min(years), max(years)
    return str(lo) if lo == hi else f"{lo}-{hi}"


def _inspect(p: Path):
    kind = _file_kind(p)
    if not kind:
        return None
    width = height = bands = None
    crs = None
    error = None
    try:
        if kind == "GeoTIFF/COG":
            import rasterio

            with rasterio.open(p) as src:
                width, height, bands, crs = (
                    src.width,
                    src.height,
                    src.count,
                    str(src.crs) if src.crs else None,
                )
                # A truncated GeoTIFF still has a readable header: it reports
                # its size, CRS and band count, and used to be accepted as
                # ready. Only a real pixel read proves the data is there.
                src.read(
                    1,
                    window=rasterio.windows.Window(
                        0, 0, min(64, src.width), min(64, src.height)
                    ),
                )
                src.read(
                    1,
                    window=rasterio.windows.Window(
                        max(0, src.width - 64), max(0, src.height - 64),
                        min(64, src.width), min(64, src.height),
                    ),
                )
        else:
            with Image.open(p) as im:
                width, height = im.size
                bands = len(im.getbands())
                # Map services answer an unavailable period with a fully
                # transparent tile. It decodes cleanly, so it used to be
                # imported as a ready scene with no pixels in it.
                if "A" in im.getbands() and im.getchannel("A").getextrema()[1] == 0:
                    error = "Blank tile: every pixel is fully transparent (no imagery)"
    except Exception as exc:
        error = str(exc)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    date = sensor = footprint = None
    item = {}
    sidecars = [p.with_suffix(".json"), p.parent / "metadata.json"]
    for sidecar in sidecars:
        if sidecar.exists():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                item = data.get(p.name, data) if isinstance(data, dict) else {}
                date = item.get("date") or item.get("acquisition_date")
                sensor = item.get("sensor") or item.get("platform")
                fp = item.get("bbox") or item.get("footprint") or item.get("geometry")
                footprint = json.dumps(fp) if isinstance(fp, (dict, list)) else fp
                break
            except Exception:
                pass
    if kind == "GeoTIFF/COG" and not error:
        import rasterio

        with rasterio.open(p) as src:
            if src.crs:
                footprint = json.dumps(
                    {
                        "crs": str(src.crs),
                        "bounds": list(src.bounds),
                        "transform": list(src.transform)[:6],
                        "source_scene_id": item.get("source_scene_id"),
                        "source_path": item.get("source_path"),
                        "source_sha256": item.get("source_sha256"),
                        "pixel_window": item.get("pixel_window"),
                    }
                )
            tags = src.tags()
            date = date or tags.get("ACQUISITION_DATE") or tags.get("TIFFTAG_DATETIME")
            sensor = sensor or tags.get("SENSOR") or tags.get("SPACECRAFT_NAME")
    date = date or _date_from_name(p.stem) or _period_from_folder(p.parent.name)
    return dict(
        path=str(p),
        name=p.name,
        kind=kind,
        bytes=p.stat().st_size,
        width=width,
        height=height,
        bands=bands,
        crs=crs,
        date=date,
        sensor=sensor,
        footprint=footprint,
        error=error,
        sha256=h.hexdigest(),
    )


def _quality_for_path(p: Path) -> dict:
    """Compute lightweight, deterministic intake signals from a local raster.
    The checks are triage gates for an analyst; they do not claim atmospheric
    correction or scientific image quality assessment.
    """
    result = {
        "available": False,
        "blank": False,
        "low_contrast": False,
        "blur_suspected": False,
        "flags": [],
        "sample_width": None,
        "sample_height": None,
        "mean": None,
        "stddev": None,
        "edge_variance": None,
    }
    try:
        import numpy as np

        kind = _file_kind(p)
        if kind == "GeoTIFF/COG":
            import rasterio

            with rasterio.open(p) as src:
                # A bounded sample keeps quality scans fast for large COGs.
                scale = min(1.0, 512 / max(src.width, src.height))
                w, h = max(1, int(src.width * scale)), max(1, int(src.height * scale))
                arr = (
                    src.read(1, out_shape=(h, w), masked=True)
                    .filled(0)
                    .astype("float32")
                )
        elif kind:
            with Image.open(p) as im:
                im = im.convert("L")
                scale = min(1.0, 512 / max(im.width, im.height))
                w, h = max(1, int(im.width * scale)), max(1, int(im.height * scale))
                arr = np.asarray(im.resize((w, h)), dtype="float32")
        else:
            result["flags"] = ["unsupported raster"]
            return result
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            result["flags"] = ["no valid pixels"]
            return result
        mean, std = float(finite.mean()), float(finite.std())
        # Mean absolute neighbour gradient is a simple blur/edge signal.
        dx = np.diff(arr, axis=1) if arr.shape[1] > 1 else np.zeros_like(arr)
        dy = np.diff(arr, axis=0) if arr.shape[0] > 1 else np.zeros_like(arr)
        edge_variance = float(np.var(np.concatenate((dx.ravel(), dy.ravel()))))
        result.update(
            available=True,
            sample_width=int(arr.shape[1]),
            sample_height=int(arr.shape[0]),
            mean=round(mean, 3),
            stddev=round(std, 3),
            edge_variance=round(edge_variance, 3),
        )
        result["blank"] = bool(std < 1.0 or float(finite.max() - finite.min()) < 2.0)
        result["low_contrast"] = bool(
            std < 5.0 or float(finite.max() - finite.min()) < 10.0
        )
        # This is deliberately a suspicion threshold; the analyst still reviews the image.
        result["blur_suspected"] = bool(edge_variance < 2.0 and not result["blank"])
        if result["blank"]:
            result["flags"].append("blank or constant image")
        elif result["low_contrast"]:
            result["flags"].append("very low contrast")
        if result["blur_suspected"]:
            result["flags"].append("blur suspected")
        # PS 2.2.3 confounders. The SCL band was already in the GeoTIFF and was
        # being ignored, so cloud/shadow/snow had no evidence behind them.
        if kind == "GeoTIFF/COG":
            try:
                scl = scl_summary(p)
                result["scene_classification"] = scl
                if scl.get("available"):
                    result["flags"].extend(scl["flags"])
            except Exception as exc:
                result["scene_classification"] = {
                    "available": False, "reason": f"SCL read failed: {exc}"}
        return result
    except Exception as exc:
        result["flags"] = [f"quality scan failed: {exc}"]
        return result


def _source_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _scan(job_id: str, folder: str):
    import time

    started = time.perf_counter()
    try:
        base = Path(folder).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("Folder does not exist or is not a directory")
        files = [p for p in base.rglob("*") if p.is_file() and _file_kind(p)]
        existing = {}
        c0 = conn()
        c0.execute(
            "create table if not exists intake_metadata(path text primary key, digest text not null)"
        )
        metadata_digests = dict(c0.execute("select path,digest from intake_metadata"))
        for row in c0.execute("select * from scenes").fetchall():
            existing[row["path"]] = dict(row)
        c0.commit()
        c0.close()

        def metadata_digest(p):
            # INTAKE_VERSION is part of the digest so a change to how files are
            # inspected (dates, blank tiles) reaches already-imported scenes.
            return hashlib.sha256(
                INTAKE_VERSION.encode() + b"|" + b"|".join(
                    s.read_bytes() if s.is_file() else b"<missing>"
                    for s in (p.with_suffix(".json"), p.parent / "metadata.json")
                )
            ).hexdigest()

        current_metadata = {str(p.resolve()): metadata_digest(p) for p in files}
        unchanged = {
            str(p.resolve())
            for p in files
            if existing.get(str(p.resolve()), {}).get("sha256") == _source_hash(p)
            and existing[str(p.resolve())]["status"] == "ready"
            and metadata_digests.get(str(p.resolve()))
            == current_metadata[str(p.resolve())]
        }
        files = [p for p in files if str(p.resolve()) not in unchanged]
        jobs[job_id].update(total=len(files), state="scanning")
        found = []
        workers = max(2, min(32, (os.cpu_count() or 4) * 2))
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_inspect, p): p for p in files}
            for future in as_completed(futures):
                p = futures[future]
                found.append(future.result())
                done += 1
                jobs[job_id].update(done=done, current=p.name)
        with lock:
            c = conn()
            for x in found:
                c.execute(
                    "insert or replace into intake_metadata values(?,?)",
                    (x["path"], current_metadata[x["path"]]),
                )
                old = existing.get(x["path"])
                if (
                    old
                    and old["status"] == "ready"
                    and not x["error"]
                    and all(
                        old.get(k) == x.get(k)
                        for k in (
                            "sha256",
                            "date",
                            "sensor",
                            "footprint",
                            "width",
                            "height",
                            "bands",
                            "crs",
                        )
                    )
                ):
                    continue
                c.execute(
                    "delete from scene_index where scene_id in (select id from scenes where path=?)",
                    (x["path"],),
                )
                c.execute(
                    """INSERT INTO scenes(path,name,kind,bytes,width,height,bands,crs,date,sensor,status,sha256,imported_at,error,footprint)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET status=excluded.status,error=excluded.error,footprint=excluded.footprint,date=excluded.date,sensor=excluded.sensor,crs=excluded.crs,sha256=excluded.sha256,bytes=excluded.bytes,width=excluded.width,height=excluded.height,bands=excluded.bands,imported_at=excluded.imported_at""",
                    (
                        x["path"],
                        x["name"],
                        x["kind"],
                        x["bytes"],
                        x["width"],
                        x["height"],
                        x["bands"],
                        x["crs"],
                        x.get("date"),
                        x.get("sensor"),
                        "ready" if not x["error"] else "error",
                        x["sha256"],
                        datetime.now(timezone.utc).isoformat(),
                        x["error"],
                        x.get("footprint"),
                    ),
                )
            c.commit()
            c.close()
        # The job used to report errors=0 while individual files were stored
        # with status='error'. An operator watching the job saw a clean import.
        rejected = [
            {"file": Path(x["path"]).name, "error": x["error"]}
            for x in found
            if x.get("error")
        ]
        jobs[job_id].setdefault("errors", []).extend(rejected)
        accepted = len(found) - len(rejected)
        jobs[job_id].update(
            state="complete",
            current="",
            elapsed_seconds=round(time.perf_counter() - started, 3),
            unchanged=len(unchanged),
            accepted=accepted,
            rejected=len(rejected),
            # Silence on an empty folder reads as a successful import.
            message=(
                "No supported imagery found in this folder"
                if not found and not unchanged
                else f"{accepted} accepted, {len(rejected)} rejected"
            ),
        )
    except Exception as exc:
        jobs[job_id].update(state="failed", error=str(exc))


class ScanRequest(BaseModel):
    folder: str
    mode: str = "append"


class DecisionRequest(BaseModel):
    scene_id: int
    decision: str
    note: str = ""


class ManifestEvaluationRequest(BaseModel):
    manifest: str
    pixel_threshold: float = 0.18
    change_ratio_threshold: float = 0.03


class EvaluationPair(BaseModel):
    before_id: int
    after_id: int
    label: int


class EvaluationRequest(BaseModel):
    pairs: list[EvaluationPair]
    threshold: float = 0.18
    prediction_ratio: float = 0.03


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status():
    c = conn()
    row = c.execute(
        "select count(*) n, coalesce(sum(bytes),0) bytes, sum(status='error') errors from scenes"
    ).fetchone()
    indexed = c.execute("select count(*) n from scene_index").fetchone()["n"]
    c.close()
    return {
        "scenes": row["n"] or 0,
        "bytes": row["bytes"] or 0,
        "errors": row["errors"] or 0,
        "offline": True,
        "model": "Semantic encoder staged; local visual index available",
        "semantic_index": (
            f"Semantic index ready · {cluster_engine.status.get('accepted', 0)} scenes"
            if cluster_engine.status.get("state") == "ready"
            else "Semantic index not built yet"
        ),
        "index": {"indexed": indexed, "state": "ready" if indexed else "not built"},
    }


@app.get("/api/evaluation/summary")
def evaluation_summary():
    c = conn()
    total = c.execute("select count(*) from scenes").fetchone()[0]
    dated = c.execute(
        "select count(*) from scenes where date is not null and date!=''"
    ).fetchone()[0]
    geo = c.execute(
        "select count(*) from scenes where crs is not null and crs!=''"
    ).fetchone()[0]
    ready = c.execute("select count(*) from scenes where status='ready'").fetchone()[0]
    c.close()
    return {
        "offline": True,
        "indexed_scenes": total,
        "ready_scenes": ready,
        "dated_scenes": dated,
        "crs_declared_scenes": geo,
        "semantic_evaluation": "pending held-out set",
        "change_evaluation": "pending labelled change/no-change pairs",
        "note": "Counts describe archive readiness; they are not accuracy metrics.",
    }


def _manifest_rows(manifest: str) -> list[dict]:
    """Read a small, operator-editable labelled pair manifest from local disk.

    CSV columns are before, after, label. JSON may be a list or {"pairs": [...]}
    with the same keys. This deliberately keeps labels external to the image
    archive so a held-out evaluation set can be swapped in without re-importing.
    """
    raw = str(manifest or "").strip()
    # This endpoint is intentionally local-only: reject URL-like values and
    # directories before opening anything. The operator may choose a manifest
    # from any local drive (for example a staged Downloads folder).
    if not raw or "://" in raw or raw.startswith(("\\\\", "//")):
        raise ValueError("manifest must be a local JSON or CSV file path")
    candidate = Path(raw).expanduser()
    if candidate.is_symlink():
        raise ValueError("manifest symlinks are not accepted")
    p = candidate.resolve()
    if not p.is_file():
        raise ValueError(f"manifest not found: {p}")
    if p.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(
            f"manifest exceeds {MAX_MANIFEST_BYTES // (1024 * 1024)} MB limit"
        )
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    elif p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("pairs", data) if isinstance(data, dict) else data
    else:
        raise ValueError("manifest must be .csv or .json")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest contains no labelled pairs")
    if len(rows) > MAX_MANIFEST_ROWS:
        raise ValueError(f"manifest contains more than {MAX_MANIFEST_ROWS} rows")
    required = {"before", "after", "label"}
    if any(not isinstance(row, dict) or not required.issubset(row) for row in rows):
        raise ValueError("each manifest row requires before, after and label")
    for index, row in enumerate(rows, 1):
        if (
            not str(row.get("before", "")).strip()
            or not str(row.get("after", "")).strip()
        ):
            raise ValueError(f"row {index} has an empty before or after reference")
        _label_bool(row["label"])
    return rows


def _label_bool(value) -> bool:
    value = str(value).strip().lower()
    if value in {"1", "true", "yes", "change", "changed", "positive"}:
        return True
    if value in {"0", "false", "no", "no-change", "no_change", "unchanged", "negative"}:
        return False
    raise ValueError(f"unsupported label: {value}")


def _resolve_scene(ref):
    c = conn()
    try:
        if str(ref).strip().isdigit():
            row = c.execute(
                "select * from scenes where id=?", (int(str(ref).strip()),)
            ).fetchone()
        else:
            raw = str(ref)
            row = c.execute(
                "select * from scenes where path=? or name=? order by id desc limit 1",
                (raw, Path(raw).name),
            ).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def _alignment_report(before: dict, after: dict) -> dict:
    """Check whether two local rasters share a pixel grid.

    A matching filename, dimensions or CRS is insufficient for pixel
    comparison.  GeoTIFF transforms are read from the source files and are
    compared exactly (within a tiny floating point tolerance).  PNG/JPEG
    scenes have no declared map grid and therefore remain unverified.
    """
    report = {
        "before_id": before.get("id"),
        "after_id": after.get("id"),
        "verified": False,
        "pixel_comparison_allowed": False,
        "flags": [],
        "before": {},
        "after": {},
        "method": "source GeoTIFF CRS, transform, dimensions and band count",
    }
    tif_suffixes = {".tif", ".tiff", ".cog"}
    if (
        Path(before["path"]).suffix.lower() not in tif_suffixes
        or Path(after["path"]).suffix.lower() not in tif_suffixes
    ):
        report["flags"].append(
            "source raster is not GeoTIFF/COG with a declared pixel grid"
        )
        return report
    try:
        import rasterio

        with rasterio.open(before["path"]) as b, rasterio.open(after["path"]) as a:

            def details(src):
                return {
                    "width": src.width,
                    "height": src.height,
                    "bands": src.count,
                    "crs": str(src.crs) if src.crs else None,
                    "transform": [round(float(x), 12) for x in src.transform],
                    "bounds": [round(float(x), 12) for x in src.bounds],
                    "resolution": [round(float(x), 12) for x in src.res],
                }

            report["before"], report["after"] = details(b), details(a)
    except Exception as exc:
        report["flags"].append(f"unable to inspect GeoTIFF grid: {exc}")
        return report
    b, a = report["before"], report["after"]
    if not b["crs"] or not a["crs"]:
        report["flags"].append("CRS missing")
    elif b["crs"] != a["crs"]:
        report["flags"].append("CRS differs")
    if (b["width"], b["height"]) != (a["width"], a["height"]):
        report["flags"].append("dimensions differ")
    if b["bands"] != a["bands"]:
        report["flags"].append("band count differs")
    if b.get("transform") != a.get("transform"):
        report["flags"].append("pixel transform differs")
    if b.get("bounds") != a.get("bounds"):
        report["flags"].append("spatial bounds differ")
    report["verified"] = not report["flags"]
    report["pixel_comparison_allowed"] = report["verified"]
    return report


def _screen_pair(before, after, pixel_threshold: float):
    import numpy as np

    left, right = _analysis_image(before["path"]), _analysis_image(after["path"])
    if left.shape[:2] != right.shape[:2]:
        right = np.asarray(
            Image.fromarray(right).resize(
                (left.shape[1], left.shape[0]), Image.Resampling.BILINEAR
            )
        )
    delta = np.abs(left.astype("float32") - right.astype("float32")).max(axis=2) / 255.0
    ratio = float((delta >= pixel_threshold).mean())
    return ratio, float(delta.mean())


def evaluate_manifest_file(
    manifest: str, pixel_threshold: float = 0.18, change_ratio_threshold: float = 0.03
):
    if not 0.01 <= pixel_threshold <= 1.0 or not 0.0 <= change_ratio_threshold <= 1.0:
        raise ValueError("thresholds are out of range")
    rows = _manifest_rows(manifest)
    details = []
    tp = tn = fp = fn = 0
    errors = []
    for index, item in enumerate(rows, 1):
        try:
            expected = _label_bool(item["label"])
            before, after = _resolve_scene(item["before"]), _resolve_scene(
                item["after"]
            )
            if not before or not after:
                raise ValueError("scene reference not found in local library")
            if before.get("status") != "ready" or after.get("status") != "ready":
                raise ValueError("scene is not ready")
            ratio, mad = _screen_pair(before, after, pixel_threshold)
            predicted = ratio >= change_ratio_threshold
            if predicted and expected:
                tp += 1
            elif predicted:
                fp += 1
            elif expected:
                fn += 1
            else:
                tn += 1
            details.append(
                {
                    "row": index,
                    "before_id": before["id"],
                    "after_id": after["id"],
                    "expected_change": expected,
                    "predicted_change": predicted,
                    "changed_pixel_ratio": round(ratio, 4),
                    "mean_absolute_difference": round(mad, 4),
                }
            )
        except Exception as exc:
            errors.append({"row": index, "error": str(exc)})
    evaluated = tp + tn + fp + fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / evaluated if evaluated else 0.0
    return {
        "offline": True,
        "manifest": str(Path(manifest).expanduser().resolve()),
        "total_rows": len(rows),
        "evaluated_pairs": evaluated,
        "errors": errors,
        "thresholds": {
            "pixel": pixel_threshold,
            "change_ratio": change_ratio_threshold,
        },
        "confusion_matrix": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
        },
        "details": details,
        "method": "offline pixel-difference screening; labelled evaluation only",
    }


@app.post("/api/evaluation/run")
def run_evaluation(body: ManifestEvaluationRequest):
    try:
        return evaluate_manifest_file(
            body.manifest, body.pixel_threshold, body.change_ratio_threshold
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(422, f"evaluation failed: {exc}")


@app.get("/api/index/status")
def index_status():
    c = conn()
    total = c.execute("select count(*) n from scenes where status='ready'").fetchone()[
        "n"
    ]
    indexed = c.execute("select count(*) n from scene_index").fetchone()["n"]
    latest = c.execute("select max(indexed_at) value from scene_index").fetchone()[
        "value"
    ]
    c.close()
    return {
        "indexed": indexed,
        "ready_scenes": total,
        "pending": max(0, total - indexed),
        "complete": total > 0 and indexed >= total,
        "encoder": "local-thumbnail-histogram-v2",
        "semantic_encoder": "staged; requires separate validated model index",
        "last_indexed_at": latest,
    }


@app.post("/api/index/build")
def build_index():
    active = next(
        (
            j
            for j in jobs.values()
            if j.get("kind") == "index" and j.get("state") in {"queued", "indexing"}
        ),
        None,
    )
    if active:
        return active
    jid = uuid.uuid4().hex
    jobs[jid] = {
        "id": jid,
        "kind": "index",
        "state": "queued",
        "total": 0,
        "done": 0,
        "current": "",
        "errors": [],
    }
    threading.Thread(target=_build_index, args=(jid,), daemon=True).start()
    return jobs[jid]


@app.post("/api/scan")
def scan(body: ScanRequest):
    if body.mode not in {"append", "replace"}:
        raise HTTPException(400, "Import mode must be append or replace")
    if not Path(body.folder).expanduser().is_dir():
        raise HTTPException(400, "Folder does not exist or is not a directory")
    if cluster_engine.running or any(
        j.get("state") in {"queued", "scanning", "indexing"} for j in jobs.values()
    ):
        raise HTTPException(409, "Wait for the current import or index build to finish")
    if body.mode == "replace":
        _reset_archive_for_new_import()
    else:
        cluster_engine.clear()
    jid = uuid.uuid4().hex
    jobs[jid] = {
        "id": jid,
        "state": "queued",
        "total": 0,
        "done": 0,
        "current": "",
        "folder": body.folder,
    }
    threading.Thread(target=_scan, args=(jid, body.folder), daemon=True).start()
    return jobs[jid]


@app.post("/api/scan/upload")
async def scan_upload(
    files: list[UploadFile] = File(...),
    paths: list[str] = Form(default=[]),
    mode: str = Form("append"),
):
    """Ingest a browser-selected local folder into a local staging batch."""
    if mode not in {"append", "replace"}:
        raise HTTPException(400, "Import mode must be append or replace")
    if cluster_engine.running or any(
        j.get("state") in {"queued", "scanning", "indexing"} for j in jobs.values()
    ):
        raise HTTPException(409, "Wait for the current import or index build to finish")
    if mode == "replace":
        _reset_archive_for_new_import()
    else:
        cluster_engine.clear()
    batch = DATA / "import_batches" / uuid.uuid4().hex
    batch.mkdir(parents=True, exist_ok=True)
    for i, upload in enumerate(files):
        rel = (paths[i] if i < len(paths) else upload.filename or f"file_{i}").replace(
            "\\", "/"
        )
        safe = Path(*[part for part in rel.split("/") if part not in ("", ".", "..")])
        target = batch / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                out.write(chunk)
        await upload.close()
    jid = uuid.uuid4().hex
    jobs[jid] = {
        "id": jid,
        "state": "queued",
        "total": 0,
        "done": 0,
        "current": "",
        "folder": str(batch),
        "source": "browser folder upload",
    }
    threading.Thread(target=_scan, args=(jid, str(batch)), daemon=True).start()
    return jobs[jid]


@app.delete("/api/library")
def clear_library():
    """Clear the local scene archive and fingerprints after UI confirmation."""
    if cluster_engine.running or any(
        j.get("state") in {"queued", "scanning", "indexing"} for j in jobs.values()
    ):
        raise HTTPException(
            409, "Wait for active processing before clearing the archive"
        )
    with lock:
        c = conn()
        c.execute("delete from scene_index")
        c.execute("delete from scenes")
        c.execute("drop table if exists intake_metadata")
        c.commit()
        c.close()
        # Derived semantic vectors are separate from the archive database.
        # Clear them too, otherwise old embeddings can repopulate results.
        semantic_db = DATA / "semantic_cache.sqlite3"
        if semantic_db.exists():
            sc = sqlite3.connect(semantic_db)
            for table in ("scene_features", "features"):
                exists = sc.execute(
                    "select 1 from sqlite_master where type='table' and name=?",
                    (table,),
                ).fetchone()
                if exists:
                    sc.execute(f"delete from {table}")
            sc.commit()
            sc.close()
    cluster_engine.clear()
    return {"cleared": True}


def _reset_archive_for_new_import():
    """Start a new operator session scoped to the folder just selected.

    Imported originals remain on disk; only the app's previous session index
    and derived vectors are replaced so searches and clusters cannot mix roots.
    """
    with lock:
        c = conn()
        c.execute("delete from scene_index")
        c.execute("delete from scenes")
        c.execute("drop table if exists intake_metadata")
        c.commit()
        c.close()
        semantic_db = DATA / "semantic_cache.sqlite3"
        if semantic_db.exists():
            sc = sqlite3.connect(semantic_db)
            for table in ("scene_features", "features"):
                exists = sc.execute(
                    "select 1 from sqlite_master where type='table' and name=?",
                    (table,),
                ).fetchone()
                if exists:
                    sc.execute(f"delete from {table}")
            sc.commit()
            sc.close()
    cluster_engine.clear()


@app.get("/api/pick-folder")
def pick_folder():
    """Open pywebview's native folder dialog in the packaged desktop app."""
    if NATIVE_FOLDER_PICKER is None:
        raise HTTPException(
            503,
            "Native folder picker is only available in the ANVESHAN desktop app. "
            "Paste the absolute folder path instead.",
        )
    try:
        chosen = NATIVE_FOLDER_PICKER()
    except Exception as exc:
        raise HTTPException(503, f"Native folder picker unavailable: {exc}")
    if isinstance(chosen, (list, tuple)):
        chosen = chosen[0] if chosen else ""
    chosen = str(chosen or "")
    return {"folder": chosen, "cancelled": not bool(chosen)}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "job not found")
    return jobs[job_id]


@app.get("/api/scenes")
def scenes(
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    kind: str = "",
    limit: int = 100,
    sensor: str = "",
    bbox: str = "",
):
    try:
        date_from = parse_date_filter(date_from, "date_from")
        date_to = parse_date_filter(date_to, "date_to")
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from is after date_to")
    except ValueError as exc:
        # A malformed date used to reach SQL and match nothing, which the
        # operator reads as "there is no imagery", not "your filter is wrong".
        raise HTTPException(400, str(exc))
    clauses = ["(name like ? or path like ?)"]
    args = [f"%{q}%", f"%{q}%"]
    if date_from:
        clauses.append("date >= ?")
        args.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        args.append(date_to)
    if kind:
        clauses.append("kind = ?")
        args.append(kind)
    c = conn()
    rows = c.execute(
        "select * from scenes where "
        + " and ".join(clauses)
        + " order by imported_at desc",
        args,
    ).fetchall()
    c.close()
    try:
        return filter_rows([dict(r) for r in rows], sensor, bbox)[
            : max(1, min(limit, 10000))
        ]
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/search")
def content_search(
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    kind: str = "",
    limit: int = 30,
    sensor: str = "",
    bbox: str = "",
):
    """Offline deterministic discovery baseline. Scores lexical metadata matches;
    it never presents a filename match as a learned semantic confidence."""
    tokens = [t.lower() for t in q.split() if len(t) > 1]
    rows = scenes(
        q="",
        date_from=date_from,
        date_to=date_to,
        kind=kind,
        limit=10000,
        sensor=sensor,
        bbox=bbox,
    )
    scored = []
    for r in rows:
        # Directory names are provenance only; including them makes a query like
        # "river" match every scene stored under a river-named folder.
        hay = (r["name"] + " " + (r["sensor"] or "") + " " + (r["date"] or "")).lower()
        score = sum(1 for t in tokens if t in hay) / (len(tokens) or 1)
        if not tokens or score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    for score, r in scored[:limit]:
        r["match_score"] = round(score, 3)
        r["score_type"] = "metadata match"
    return {
        "query": q,
        "results": [r for _, r in scored[:limit]],
        "method": "offline metadata baseline",
        "semantic_encoder": "staged for next index build",
    }


@app.get("/api/search/semantic")
def semantic_search(
    q: str = "",
    reference_scene_id: Optional[int] = None,
    date_from: str = "",
    date_to: str = "",
    kind: str = "",
    limit: int = 30,
    sensor: str = "",
    bbox: str = "",
    feedback_scene_ids: str = "",
    near_water: bool = False,
    water_min: float | None = None,
):
    """PS 2.2.1: free-text and image-to-image retrieval, fully local.

    near_water restricts ranking to windows within one 2.24 km window of
    Sentinel-2 SCL water, for queries like "newly built structures near a river".
    """
    try:
        feedback = (
            [int(v) for v in feedback_scene_ids.split(",")]
            if feedback_scene_ids
            else None
        )
        return cluster_engine.search(
            query=q,
            reference_id=reference_scene_id,
            date_from=date_from,
            date_to=date_to,
            kind=kind,
            limit=limit,
            sensor=sensor,
            bbox=bbox,
            feedback_ids=feedback,
            near_water=near_water,
            water_min=water_min,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(503, f"Local semantic index is still preparing: {exc}")


@app.post("/api/search/semantic/upload")
async def semantic_upload(
    file: UploadFile = File(...),
    date_from: str = "",
    date_to: str = "",
    kind: str = "",
    limit: int = 30,
    sensor: str = "",
    bbox: str = "",
):
    """Search with a reference image without copying it into the archive."""
    allowed_types = {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/tiff",
        "image/x-tiff",
    }
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    # Chromium/Windows commonly labels TIFF uploads as application/octet-stream
    # (and can omit the MIME type entirely). The decoder below remains the
    # authority, so accept a supported filename when the browser MIME is vague.
    if content_type not in allowed_types and suffix not in allowed_suffixes:
        raise HTTPException(415, "Choose a PNG, JPEG, WebP or TIFF image")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Reference image is empty")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Reference image is larger than 25 MB")
    try:
        from io import BytesIO

        image = read_rgb(BytesIO(data))
        return cluster_engine.search_image(
            image,
            date_from=date_from,
            date_to=date_to,
            kind=kind,
            limit=limit,
            sensor=sensor,
            bbox=bbox,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Could not read the reference image: {exc}")
    except Exception as exc:
        raise HTTPException(503, f"Local semantic index is still preparing: {exc}")


@app.get("/api/search/visual")
def visual_search(
    scene_id: int,
    date_from: str = "",
    date_to: str = "",
    kind: str = "",
    limit: int = 30,
):
    """Find visually similar indexed scenes using the local histogram baseline.

    This is deliberately a separate endpoint from text search. A histogram is
    useful for deterministic visual-neighbour discovery, but it is not a
    semantic embedding and must not be presented as one.
    """
    # Semantic index is the primary image-to-image path. Keep the old histogram
    # code below as a compatibility fallback for archives indexed before it.
    try:
        return cluster_engine.search(
            reference_id=scene_id,
            date_from=date_from,
            date_to=date_to,
            kind=kind,
            limit=limit,
        )
    except Exception:
        pass
    limit = max(1, min(int(limit), 200))
    c = conn()
    query = c.execute("select * from scenes where id=?", (scene_id,)).fetchone()
    if not query:
        c.close()
        raise HTTPException(404, "reference scene not found")
    try:
        qfp_row = c.execute(
            "select fingerprint from scene_index where scene_id=?", (scene_id,)
        ).fetchone()
        qfp = qfp_row["fingerprint"] if qfp_row else _visual_fingerprint(query["path"])
        try:
            date_from = parse_date_filter(date_from, "date_from")
            date_to = parse_date_filter(date_to, "date_to")
            if date_from and date_to and date_from > date_to:
                raise ValueError("date_from is after date_to")
        except ValueError as exc:
            # A malformed date used to reach SQL and match nothing, which the
            # operator reads as "there is no imagery", not "your filter is wrong".
            raise HTTPException(400, str(exc))
        clauses = ["s.status='ready'", "s.id != ?"]
        args = [scene_id]
        if date_from:
            clauses.append("s.date >= ?")
            args.append(date_from)
        if date_to:
            clauses.append("s.date <= ?")
            args.append(date_to)
        if kind:
            clauses.append("s.kind = ?")
            args.append(kind)
        rows = c.execute(
            "select s.*, i.fingerprint, i.encoder from scenes s join scene_index i on i.scene_id=s.id where "
            + " and ".join(clauses),
            args,
        ).fetchall()
    finally:
        c.close()
    scored = []
    for row in rows:
        try:
            score = _cosine_similarity(qfp, row["fingerprint"])
        except Exception:
            continue
        item = dict(row)
        item.pop("fingerprint", None)
        item["match_score"] = round(max(0.0, min(1.0, score)), 4)
        item["score_type"] = "local visual fingerprint similarity"
        item["reference_scene_id"] = scene_id
        scored.append(item)
    scored.sort(key=lambda item: (-item["match_score"], item["name"]))
    return {
        "query_scene_id": scene_id,
        "results": scored[:limit],
        "method": "offline local thumbnail histogram similarity",
        "encoder": "local-thumbnail-histogram-v2",
        "semantic": False,
        "note": "Visual-neighbour baseline only; this is not semantic retrieval.",
    }


cluster_engine = ClusterEngine(ROOT, conn)


@app.get("/api/clusters/status")
def cluster_status():
    return dict(cluster_engine.status)


@app.post("/api/clusters/build")
def build_clusters():
    """Explicit operator gate for local screening, embeddings and groups."""
    cluster_engine.rebuild()
    return dict(cluster_engine.status)


@app.get("/api/clusters")
def clusters(limit: int = 100, mode: str = "temporal"):
    if mode not in ("temporal", "similar"):
        raise HTTPException(400, "Unknown cluster view")
    return cluster_engine.result(limit, mode)


@app.get("/api/scenes/{scene_id}")
def scene_detail(scene_id: int):
    c = conn()
    row = c.execute("select * from scenes where id=?", (scene_id,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "scene not found")
    return dict(row)


@app.get("/api/scenes/{scene_id}/preview")
def preview(scene_id: int):
    c = conn()
    r = c.execute("select path from scenes where id=?", (scene_id,)).fetchone()
    c.close()
    if not r or not Path(r["path"]).exists():
        raise HTTPException(404, "scene unavailable")
    if Path(r["path"]).suffix.lower() in (".tif", ".tiff"):
        import io
        from fastapi.responses import Response

        buf = io.BytesIO()
        read_rgb(r["path"]).save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")
    return FileResponse(
        r["path"],
        media_type=mimetypes.guess_type(r["path"])[0] or "application/octet-stream",
    )


@app.get("/api/quality/{scene_id}")
def quality(scene_id: int):
    """Return local raster quality triage for one imported scene."""
    c = conn()
    r = c.execute(
        "select id,name,path,width,height,bands,crs,status from scenes where id=?",
        (scene_id,),
    ).fetchone()
    c.close()
    if not r:
        raise HTTPException(404, "scene not found")
    p = Path(r["path"])
    out = (
        _quality_for_path(p)
        if p.exists()
        else {"available": False, "flags": ["source file unavailable"]}
    )
    out.update(
        {
            "scene_id": r["id"],
            "name": r["name"],
            "declared_width": r["width"],
            "declared_height": r["height"],
            "declared_bands": r["bands"],
            "crs": r["crs"],
            "ingest_status": r["status"],
            "source": "local raster sample",
        }
    )
    out["quality_gate"] = "review required" if out.get("flags") else "pass"
    return out


@app.get("/api/quality")
def quality_summary(limit: int = 100):
    """Summarize quality flags across the local library for operator triage."""
    c = conn()
    rows = c.execute(
        "select id,name,path from scenes order by imported_at desc limit ?",
        (max(1, min(limit, 1000)),),
    ).fetchall()
    c.close()
    items = []
    for r in rows:
        q = (
            _quality_for_path(Path(r["path"]))
            if Path(r["path"]).exists()
            else {"available": False, "flags": ["source file unavailable"]}
        )
        items.append(
            {
                "scene_id": r["id"],
                "name": r["name"],
                "quality_gate": "review required" if q.get("flags") else "pass",
                "flags": q.get("flags", []),
                "metrics": q,
            }
        )
    return {
        "scenes": items,
        "review_required": sum(x["quality_gate"] == "review required" for x in items),
        "source": "local raster samples",
        "offline": True,
    }


@app.get("/api/scenes/{scene_id}/labels")
def scene_labels(scene_id: int, top: int = 3):
    """PS 2.2.1: what each 224 m-scale window of a scene looks like.

    Offline zero-shot prompt matching over the tile vectors that the local
    index already holds - no language model, no extra image pass.
    """
    c = conn()
    row = c.execute("select id from scenes where id=?", (scene_id,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "scene not found")
    try:
        return cluster_engine.scene_labels(scene_id, top=max(1, min(int(top), 5)))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/scenes/{scene_id}/footprint")
def footprint(scene_id: int):
    c = conn()
    r = c.execute(
        "select id,name,crs,footprint from scenes where id=?", (scene_id,)
    ).fetchone()
    c.close()
    if not r:
        raise HTTPException(404, "scene not found")
    value = r["footprint"]
    if value:
        try:
            value = json.loads(value)
        except Exception:
            pass
    return {
        "id": r["id"],
        "name": r["name"],
        "crs": r["crs"],
        "footprint": value,
        "available": bool(value),
        "source": "local sidecar metadata",
    }


@app.get("/api/scenes/{scene_id}/ground-scale")
def ground_scale(scene_id: int):
    """Ground extent of one scene, so on-screen measurement can report metres.

    The viewer divides this extent by the pixel size of the preview it actually
    loaded, which keeps the conversion correct even if a preview is resampled.
    A scene with no declared footprint returns ``available: false``; the viewer
    then reports pixels and says so, rather than inventing a distance.
    """
    c = conn()
    r = c.execute(
        "select id,name,crs,footprint from scenes where id=?", (scene_id,)
    ).fetchone()
    c.close()
    if not r:
        raise HTTPException(404, "scene not found")

    unavailable = {
        "id": scene_id,
        "available": False,
        "reason": "no declared footprint or CRS for this scene",
    }
    if not r["footprint"]:
        return unavailable
    try:
        fp = json.loads(r["footprint"])
        crs, bounds = fp.get("crs"), fp.get("bounds")
        west, south, east, north = (float(v) for v in bounds)
    except (TypeError, ValueError, KeyError):
        return unavailable
    if not crs:
        return unavailable

    try:
        import math

        from rasterio.warp import transform_bounds

        lon0, lat0, lon1, lat1 = transform_bounds(
            crs, "EPSG:4326", west, south, east, north
        )
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        return {**unavailable, "reason": f"could not reproject bounds: {exc}"}
    if not all(math.isfinite(v) for v in (lon0, lat0, lon1, lat1)):
        return {**unavailable, "reason": "reprojected bounds are not finite"}

    radius = 6_371_008.8
    mean_lat = math.radians((lat0 + lat1) / 2.0)
    width_m = abs(math.radians(lon1 - lon0)) * radius * math.cos(mean_lat)
    height_m = abs(math.radians(lat1 - lat0)) * radius
    return {
        "id": scene_id,
        "name": r["name"],
        "available": True,
        "crs": crs,
        "wgs84_bounds": [lon0, lat0, lon1, lat1],
        "ground_width_m": round(width_m, 3),
        "ground_height_m": round(height_m, 3),
        "method": (
            "footprint bounds reprojected to WGS84 and measured on a sphere; "
            "divide by the loaded preview's pixel size for metres per pixel"
        ),
        "note": (
            "Approximate. This is a spherical computation over the declared "
            "footprint, not a geodetic survey measurement."
        ),
    }


@app.get("/api/alignment")
def alignment(before: int, after: int):
    """Return source-grid readiness for a before/after pair.

    This endpoint is intentionally conservative: a pair is verified only
    when both source files are GeoTIFF/COG rasters with identical CRS,
    dimensions, band count and affine transform/bounds.
    """
    c = conn()
    rows = c.execute(
        "select * from scenes where id in (?,?)", (before, after)
    ).fetchall()
    c.close()
    if len(rows) != 2:
        raise HTTPException(404, "both scenes are required")
    b = next(dict(r) for r in rows if r["id"] == before)
    a = next(dict(r) for r in rows if r["id"] == after)
    return _alignment_report(b, a)


@app.get("/api/compare")
def compare(before: int, after: int):
    c = conn()
    rows = c.execute(
        "select * from scenes where id in (?,?)", (before, after)
    ).fetchall()
    c.close()
    if len(rows) != 2:
        raise HTTPException(404, "both scenes are required")
    b = dict(rows[0] if rows[0]["id"] == before else rows[1])
    a = dict(rows[1] if rows[1]["id"] == after else rows[0])
    quality = []
    if not b.get("date") or not a.get("date"):
        quality.append("acquisition date missing")
    if b.get("width") != a.get("width") or b.get("height") != a.get("height"):
        quality.append("dimensions differ")
    if b.get("crs") != a.get("crs"):
        quality.append("CRS missing or differs")
    if b.get("bands") != a.get("bands"):
        quality.append("band count differs")
    if not b.get("footprint") or not a.get("footprint"):
        quality.append("geospatial footprint missing")
    grid = _alignment_report(b, a)
    if not grid["verified"]:
        quality.extend(x for x in grid["flags"] if x not in quality)
    for side, row in (("before", b), ("after", a)):
        try:
            if not _has_detail(_analysis_image(row["path"], 256)):
                quality.append(f"{side} image has no usable detail")
        except Exception as exc:
            quality.append(f"{side} image could not be read: {exc}")
    return {
        "before": b,
        "after": a,
        "quality_flags": quality,
        "quality_gate": "pass" if not quality else "review required",
        "alignment": grid,
        # These were hardcoded, so a pair that passed every check was still
        # told its comparison was withheld while /api/change-score returned
        # numbers for it.
        "analysis_status": "screening available" if not quality else "review required",
        "message": (
            "Source grids match. Change screening is a ranking aid, not a"
            " validated change detection result."
            if not quality
            else "Pixel comparison is withheld until both scenes pass"
            " source-grid alignment checks."
        ),
    }


def _analysis_image(path: str, max_side: int = 1024):
    """Load a small RGB array for the transparent pixel-difference baseline.

    This is deliberately a screening aid, not a trained change detector. GeoTIFF
    bands are stretched independently for display-style comparison, so callers
    must treat the result as a review cue and retain the original raster.
    """
    import numpy as np

    p = Path(path)
    if p.suffix.lower() in {".tif", ".tiff", ".cog"}:
        import rasterio

        with rasterio.open(p) as src:
            indexes = list(range(1, min(src.count, 3) + 1))
            scale = min(1, max_side / max(src.height, src.width))
            data = src.read(
                indexes,
                out_shape=(
                    len(indexes),
                    max(1, int(src.height * scale)),
                    max(1, int(src.width * scale)),
                ),
                masked=True,
            )
        channels = []
        for band in data:
            band = band.astype("float32")
            values = band.compressed()
            values = values[np.isfinite(values)]
            if not values.size:
                raise ValueError("No valid source pixels")
            lo, hi = np.percentile(values, [2, 98])
            channels.append(
                np.nan_to_num(
                    np.clip((band.filled(lo) - lo) / max(hi - lo, 1e-6) * 255, 0, 255)
                ).astype("uint8")
            )
        if len(channels) < 3:
            channels = [channels[0]] * 3
        arr = np.stack(channels, axis=-1)
    else:
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.Resampling.BILINEAR)
            arr = np.asarray(im, dtype="uint8")
    return arr


@app.get("/api/change-score")
def change_score(before: int, after: int, threshold: float = 0.18):
    """Return an interpretable offline pixel-difference screening score.

    The score is useful for prioritising analyst review only. It does not
    distinguish construction from seasonal, illumination, cloud, haze or
    registration effects, and it is never presented as semantic AI confidence.
    """
    if not 0.01 <= threshold <= 1.0:
        raise HTTPException(400, "threshold must be between 0.01 and 1.0")
    c = conn()
    rows = c.execute(
        "select * from scenes where id in (?,?)", (before, after)
    ).fetchall()
    c.close()
    if len(rows) != 2:
        raise HTTPException(404, "both scenes are required")
    b = next(dict(r) for r in rows if r["id"] == before)
    a = next(dict(r) for r in rows if r["id"] == after)
    if b.get("status") != "ready" or a.get("status") != "ready":
        raise HTTPException(422, "both scenes must be ready")
    try:
        return _score_pair(b, a, threshold)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/change-report")
def change_report(before: int, after: int, threshold: float = 0.18):
    """Create an evidence-bound offline sentence report for an image pair.

    This is intentionally deterministic today. A local text LLM can later be
    plugged in as a wording layer, but it must receive these measurements and
    cannot invent an object or change type.
    """
    score = change_score(before, after, threshold)
    ratio = float(score.get("adjusted_changed_pixel_ratio", 0)) * 100
    flags = score.get("false_alarm_signals", {}).get("flags", [])
    if score["analysis_status"] == "cannot determine":
        return {
            "before_id": before,
            "after_id": after,
            "narrative": "Cannot determine change: " + "; ".join(score["caveats"][:2]) + ".",
            "source": "offline change score + nuisance-signal heuristics",
            "llm_used": False,
            "confidence": "none - no usable imagery on at least one date",
            "measurements": score,
        }
    if ratio < 3:
        sentence = "No substantial pixel change was screened between the selected observations."
    elif ratio < 15:
        sentence = f"A localized visual difference was screened across approximately {ratio:.1f}% of the image area."
    else:
        sentence = f"A broad visual difference was screened across approximately {ratio:.1f}% of the image area."
    caveat = " Possible " + ", ".join(flags[:2]) + "." if flags else ""
    return {
        "before_id": before,
        "after_id": after,
        "narrative": sentence + caveat,
        "source": "offline change score + nuisance-signal heuristics",
        "llm_used": False,
        "confidence": "screening cue only",
        "measurements": score,
    }


@app.get("/api/compare/verified-pair")
def verified_pair(before: int, after: int):
    """Verify visual correspondence before suggesting a pair for review."""
    from app.place_matching import local_features, verify_place

    c = conn()
    rows = {
        r["id"]: dict(r)
        for r in c.execute("select * from scenes where id in (?,?)", (before, after))
    }
    c.close()
    if before == after or len(rows) != 2:
        raise HTTPException(400, "Select two different images in the active archive")
    try:
        proof = verify_place(
            local_features(read_rgb(rows[before]["path"])),
            local_features(read_rgb(rows[after]["path"])),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    return {"before": before, "after": after, "evidence": proof}


def _score_pair(b: dict, a: dict, threshold: float) -> dict:
    try:
        grid = _alignment_report(b, a)
        # Preserve the lightweight PNG/JPEG screening baseline for intake
        # fixtures, but never resize and compare GeoTIFFs with an unverified
        # source grid. Operational GeoTIFF analysis must be aligned first.
        tif_suffixes = {".tif", ".tiff", ".cog"}
        if (
            Path(b["path"]).suffix.lower() in tif_suffixes
            or Path(a["path"]).suffix.lower() in tif_suffixes
        ) and not grid["verified"]:
            raise ValueError(
                "pixel comparison refused: source GeoTIFF grid is unverified; resolve alignment flags first"
            )
        import numpy as np

        left, right = _analysis_image(b["path"]), _analysis_image(a["path"])
        # Align only the analysis thumbnails; original GeoTIFF registration is
        # still required before an operational decision.
        if left.shape[:2] != right.shape[:2]:
            right = np.asarray(
                Image.fromarray(right).resize(
                    (left.shape[1], left.shape[0]), Image.Resampling.BILINEAR
                )
            )
        delta = (
            np.abs(left.astype("float32") - right.astype("float32")).max(axis=2) / 255.0
        )
        changed = delta >= threshold
        signals = _false_alarm_signals(left, right)
        suppressed = changed & ~signals["candidate_mask"]
        ratio = float(changed.mean())
        adjusted_ratio = float(suppressed.mean())
        # Named evidence, not a confidence percentage. Similarity and pixel
        # difference are uncalibrated, so the analyst gets the checks that
        # fired instead of a number that looks like an accuracy.
        scl_before, scl_after = scl_summary(b["path"]), scl_summary(a["path"])
        season = seasonality_signal(scl_before, scl_after)
        evidence = []
        for label, side in (("before", scl_before), ("after", scl_after)):
            for flag in side.get("flags", []):
                evidence.append(f"{label}: {flag}")
        if season and season["seasonal_suspect"]:
            evidence.append(
                f"vegetation cover swings {season['vegetation_swing']:.0%} between the"
                " two dates, which is the signature of a seasonal cycle"
            )
        blind = [side for side, arr in (("before", left), ("after", right))
                 if not _has_detail(arr)]
        return {
            "before_id": b["id"],
            "after_id": a["id"],
            "threshold": threshold,
            "mean_absolute_difference": round(float(delta.mean()), 4),
            "changed_pixel_ratio": round(ratio, 4),
            "adjusted_changed_pixel_ratio": round(adjusted_ratio, 4),
            "false_alarm_signals": {
                k: v for k, v in signals.items() if k != "candidate_mask"
            },
            "suppression_applied": bool(signals["candidate_mask"].any()),
            "scene_classification": {"before": scl_before, "after": scl_after},
            "seasonality": season,
            # PS 2.2.3: why this candidate was down-weighted, in words.
            "confounder_evidence": evidence,
            # Saying nothing about a confounder reads as "it is handled".
            "not_assessed": [
                "view angle: Sentinel-2 per-band viewing zenith is not carried in"
                " these GeoTIFF tags, so view-geometry differences between the two"
                " acquisitions are not checked"
            ],
            "checks_run": len(scl_before.get("flags", [])) + len(scl_after.get("flags", []))
            + (1 if season else 0),
            "thumbnail_size": {
                "width": int(left.shape[1]),
                "height": int(left.shape[0]),
            },
            "screening_label": (
                "review candidate"
                if adjusted_ratio >= 0.03
                else "low pixel difference after quality suppression"
            ),
            "analysis_status": "cannot determine" if blind else "screening only",
            "caveats": [f"{side} image has no usable detail (blank, saturated or fully"
                        " obscured, e.g. by cloud)" for side in blind] + [
                "pixel difference is sensitive to season, illumination, cloud, haze, snow, shadow and registration",
                "no semantic object or change type is inferred",
                "analyst must inspect the original imagery and provenance",
            ],
        }
    except Exception as exc:
        raise ValueError(f"could not analyze imagery: {exc}")


def _has_detail(arr) -> bool:
    """False for a frame that is one flat colour: blank, saturated, or a scene
    fully covered by cloud. Such a frame cannot show what is on the ground."""
    return float(arr.std()) >= 1.0


def _false_alarm_signals(left, right) -> dict:
    """Transparent RGB-thumbnail nuisance signals for analyst triage."""
    import numpy as np

    l, r = left.astype("float32") / 255.0, right.astype("float32") / 255.0
    lum_l = 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]
    lum_r = 0.2126 * r[..., 0] + 0.7152 * r[..., 1] + 0.0722 * r[..., 2]
    chroma_l, chroma_r = l.max(axis=2) - l.min(axis=2), r.max(axis=2) - r.min(axis=2)
    bright_l, bright_r = (lum_l >= 0.86) & (chroma_l <= 0.12), (lum_r >= 0.86) & (
        chroma_r <= 0.12
    )
    dark_l, dark_r = lum_l <= 0.14, lum_r <= 0.14
    haze_l = (lum_l >= 0.58) & (lum_l < 0.86) & (chroma_l <= 0.10)
    haze_r = (lum_r >= 0.58) & (lum_r < 0.86) & (chroma_r <= 0.10)
    candidate = bright_l | bright_r | dark_l | dark_r | haze_l | haze_r
    bright_share = float((bright_l | bright_r).mean())
    haze_share = float((haze_l | haze_r).mean())
    dark_share = float((dark_l | dark_r).mean())
    mean_shift = float(abs(float(lum_l.mean()) - float(lum_r.mean())))
    flags = []
    if bright_share >= 0.08:
        flags.append("cloud/snow-like bright low-chroma area")
    if bright_share >= 0.25:
        flags.append("snow-like or saturated bright cover candidate")
    if haze_share >= 0.12:
        flags.append("haze-like low-chroma veil candidate")
    if dark_share >= 0.10:
        flags.append("shadow-like dark area candidate")
    if mean_shift >= 0.10:
        flags.append("illumination or exposure shift candidate")
    return {
        "flags": flags,
        "bright_low_chroma_fraction": round(bright_share, 4),
        "haze_like_fraction": round(haze_share, 4),
        "dark_shadow_fraction": round(dark_share, 4),
        "mean_luminance_shift": round(mean_shift, 4),
        "candidate_pixel_fraction": round(float(candidate.mean()), 4),
        "method": "RGB thumbnail heuristics; review required",
        "candidate_mask": candidate,
    }


@app.post("/api/evaluation/metrics")
def evaluation_metrics(body: EvaluationRequest):
    """Evaluate the transparent screening baseline against analyst labels.

    Labels are explicit: 1 means a meaningful change is present and 0 means
    no meaningful change. This endpoint computes metrics only for the supplied
    pairs; it does not create labels or call an external service.
    """
    if not body.pairs:
        raise HTTPException(400, "at least one labelled pair is required")
    if not 0.01 <= body.threshold <= 1.0:
        raise HTTPException(400, "threshold must be between 0.01 and 1.0")
    if not 0.0 <= body.prediction_ratio <= 1.0:
        raise HTTPException(400, "prediction_ratio must be between 0 and 1")
    c = conn()
    evaluated = []
    skipped = []
    for pair in body.pairs:
        if pair.label not in (0, 1):
            raise HTTPException(400, "labels must be 0 or 1")
        rows = c.execute(
            "select * from scenes where id in (?,?)", (pair.before_id, pair.after_id)
        ).fetchall()
        if len(rows) != 2 or any(r["status"] != "ready" for r in rows):
            skipped.append(
                {
                    "before_id": pair.before_id,
                    "after_id": pair.after_id,
                    "reason": "both scenes must exist and be ready",
                }
            )
            continue
        b = next(dict(r) for r in rows if r["id"] == pair.before_id)
        a = next(dict(r) for r in rows if r["id"] == pair.after_id)
        try:
            score = _score_pair(b, a, body.threshold)
            predicted = int(score["changed_pixel_ratio"] >= body.prediction_ratio)
            evaluated.append(
                {
                    "before_id": pair.before_id,
                    "after_id": pair.after_id,
                    "label": pair.label,
                    "predicted": predicted,
                    "changed_pixel_ratio": score["changed_pixel_ratio"],
                }
            )
        except ValueError as exc:
            skipped.append(
                {
                    "before_id": pair.before_id,
                    "after_id": pair.after_id,
                    "reason": str(exc),
                }
            )
    c.close()
    tp = sum(x["label"] == 1 and x["predicted"] == 1 for x in evaluated)
    tn = sum(x["label"] == 0 and x["predicted"] == 0 for x in evaluated)
    fp = sum(x["label"] == 0 and x["predicted"] == 1 for x in evaluated)
    fn = sum(x["label"] == 1 and x["predicted"] == 0 for x in evaluated)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negatives = tn + fp
    return {
        "offline": True,
        "metric_status": "labelled screening benchmark",
        "threshold": body.threshold,
        "prediction_ratio": body.prediction_ratio,
        "evaluated_pairs": len(evaluated),
        "skipped_pairs": skipped,
        "confusion_matrix": {
            "true_positive": tp,
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
        },
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "false_alarm_rate": round(fp / negatives, 4) if negatives else None,
            "accuracy": round((tp + tn) / len(evaluated), 4) if evaluated else None,
        },
        "pairs": evaluated,
        "caveats": [
            "Results depend on analyst-provided labels and thresholds",
            "This is a pixel-difference screening baseline, not a validated semantic change detector",
            "Use held-out pairs and include seasonal/cloud no-change examples",
        ],
    }


@app.get("/api/timeline")
def timeline(limit: int = 100):
    """Group local scenes into review cohorts using stable file metadata.

    Dates can occur in the middle of an AOI filename (for example
    ``AOI01_2024-10-30_s2_clear``), so remove date tokens wherever they occur.
    This remains a transparent filename/path aid; it does not infer geographic
    co-registration.
    """
    c = conn()
    # Rejected files (blank tiles, corrupt rasters) are not observations.
    rows = c.execute(
        "select * from scenes where status='ready' order by date, name limit ?", (limit,)
    ).fetchall()
    c.close()
    groups = {}
    for row in rows:
        r = dict(row)
        stem = Path(r["name"]).stem.lower()
        key = re.sub(r"(?:^|[_ -])20\d{2}[-_]\d{2}[-_]\d{2}(?=[_ -]|$)", "", stem)
        key = re.sub(r"(?:^|[_ -])20\d{6}(?=[_ -]|$)", "", key)
        key = re.sub(r"(?:^|[_ -])20\d{2}(?=[_ -]|$)", "", key)
        # Only a short copy counter ("_2", " (3)") is dropped. A long trailing
        # number is identity, e.g. the row of map tile z16_46874_27358.
        key = re.sub(r"\(\d+\)|[_ -]\d{1,2}$", "", key).strip(" _-") or stem
        groups.setdefault(key, []).append(r)
    return [
        {
            "cohort": k,
            "count": len(v),
            "dated": sum(bool(x.get("date")) for x in v),
            "scenes": sorted(v, key=lambda x: (x.get("date") or "9999", x["name"])),
        }
        for k, v in sorted(groups.items(), key=lambda x: (-len(x[1]), x[0]))
    ]


@app.get("/api/pairs")
def candidate_pairs(limit: int = 30):
    """Suggest review pairs only when basic raster identity is compatible.
    Spatial registration is deliberately not inferred from filenames."""
    c = conn()
    rows = [
        dict(r)
        for r in c.execute(
            "select * from scenes where status='ready' order by date, name limit 5000"
        ).fetchall()
    ]
    c.close()
    groups = {}
    for r in rows:
        key = (
            r.get("width"),
            r.get("height"),
            r.get("bands"),
            r.get("crs"),
            r.get("sensor"),
        )
        groups.setdefault(key, []).append(r)
    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        for i in range(len(items) - 1):
            b, a = items[i], items[i + 1]
            flags = []
            if not b.get("date") or not a.get("date"):
                flags.append("acquisition date missing")
            if not b.get("crs") or not a.get("crs"):
                flags.append("CRS missing")
            out.append(
                {
                    "before": b,
                    "after": a,
                    "compatibility": "metadata-compatible",
                    "quality_flags": flags,
                    "same_location": _footprint_relation(
                        b.get("footprint"), a.get("footprint")
                    ),
                }
            )
            if len(out) >= limit:
                return out
    return out


@app.post("/api/decisions")
def decision(body: DecisionRequest):
    if body.decision not in {"accepted", "rejected", "needs-review"}:
        raise HTTPException(400, "invalid decision")
    if not body.note.strip():
        raise HTTPException(400, "Enter a reason for this decision")
    c = conn()
    known = c.execute("select 1 from scenes where id=?", (body.scene_id,)).fetchone()
    c.close()
    if not known:
        raise HTTPException(404, "Scene is not in the archive")
    log = DATA / "audit.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scene_id": body.scene_id,
        "decision": body.decision,
        "note": body.note,
    }
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"saved": True, "entry": entry}


@app.get("/api/reviews")
def reviews():
    log = DATA / "audit.jsonl"
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class EvidenceReview(BaseModel):
    scene_ids: list[int]
    decision: str
    note: str


@app.post("/api/evidence-reviews")
def save_evidence_review(body: EvidenceReview):
    if body.decision not in {"accepted", "rejected", "needs-review"}:
        raise HTTPException(400, "Invalid decision")
    if not body.note.strip() or not body.scene_ids:
        raise HTTPException(400, "Select images and enter a review reason")
    ids = list(dict.fromkeys(body.scene_ids))
    if len(ids) > 200:
        raise HTTPException(400, "Review up to 200 images at a time")
    c = conn()
    scenes = []
    for sid in ids:
        row = c.execute("select * from scenes where id=?", (sid,)).fetchone()
        if not row:
            c.close()
            raise HTTPException(
                409, "Selection is no longer in the active archive; refresh the queue"
            )
        scenes.append(dict(row))
    c.close()
    import uuid

    record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": body.decision,
        "note": body.note.strip(),
        "scenes": scenes,
        "source": "analyst decision",
        "analysis_note": "Human review; not a validated automated change classification",
    }
    with (DATA / "evidence_reviews.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


@app.get("/api/evidence-reviews")
def evidence_reviews():
    log = DATA / "evidence_reviews.jsonl"
    if not log.exists():
        return []
    c = conn()
    active = {
        r["id"]: (r["path"], r["sha256"], r["imported_at"])
        for r in c.execute("select id,path,sha256,imported_at from scenes")
    }
    c.close()
    records = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if all(
            active.get(s["id"]) == (s["path"], s["sha256"], s["imported_at"])
            for s in record["scenes"]
        ):
            records.append(record)
    return records[::-1]


@app.get("/api/evidence-reviews/export")
def export_evidence_reviews():
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "offline": True,
        "scope": "Saved reviews matching the active archive source identities",
        "reviews": evidence_reviews(),
        "processing_history": processing_history(),
        "note": "Contains analyst decisions and source provenance, not certified accuracy or automated object-change conclusions.",
    }


@app.get("/api/export/provenance")
def export_provenance(scene_id: int):
    c = conn()
    r = c.execute("select * from scenes where id=?", (scene_id,)).fetchone()
    c.close()
    if not r:
        raise HTTPException(404, "scene not found")
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "scene": dict(r),
        "processing_history": processing_history(scene_id),
        "provenance": [
            "Original file retained at the indexed local path",
            "SHA-256 recorded at import",
            "Import validation and CRS status recorded",
            "No cloud or external API used at runtime",
        ],
        "analysis_note": "This milestone does not assert a change classification.",
    }


def processing_history(scene_id=None):
    log = DATA / "processing.jsonl"
    if not log.exists():
        return []
    c = conn()
    active = {
        r["id"]: (r["path"], r["sha256"], r["imported_at"])
        for r in c.execute("select id,path,sha256,imported_at from scenes")
    }
    c.close()
    result = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        sources = item.get("sources", [])
        if not sources or not all(
            active.get(s["id"]) == (s["path"], s["sha256"], s["imported_at"])
            for s in sources
        ):
            continue
        if scene_id is None or any(s["id"] == scene_id for s in sources):
            result.append(item)
    return result


from app.audit_routes import router as audit_router

app.include_router(audit_router)

from app.tiling import router as tiling_router

app.include_router(tiling_router)

from app.evaluation import router as evaluation_router

app.include_router(evaluation_router)
