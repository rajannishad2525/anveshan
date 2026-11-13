"""Additional evidence endpoints, reusing the active archive and existing UI."""

from datetime import datetime, timezone
import json
import re
from contextlib import closing
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


@router.get("/api/review-queue")
def ranked_queue():
    from app.main import scenes, processing_history, evidence_reviews

    rows = scenes(limit=10000)
    priorities = {}
    for item in processing_history():
        for source in item["sources"]:
            priorities[source["id"]] = max(
                priorities.get(source["id"], 0), item["adjusted_changed_pixel_ratio"]
            )
    reviewed = {s["id"] for r in evidence_reviews() for s in r["scenes"]}
    for row in rows:
        row["review_priority"] = priorities.get(row["id"], 0)
        row["reviewed"] = row["id"] in reviewed
        row["priority_reason"] = (
            "Registered change candidate"
            if row["review_priority"]
            else "No registered change analysis yet"
        )
    rows.sort(key=lambda r: (r["reviewed"], -r["review_priority"], r["id"]))
    return rows


def source_rows(ids):
    from app.main import conn

    with closing(conn()) as c:
        rows = []
        for sid in ids:
            r = c.execute("select * from scenes where id=?", (sid,)).fetchone()
            if not r:
                raise HTTPException(404, "Selected imagery is no longer in the archive")
            rows.append(dict(r))
    return rows


@router.get("/api/change/registered")
def registered(before: int, after: int, save: bool = True):
    from app.main import _analysis_image, DATA, _alignment_report, cluster_engine
    from app.verified_change import analyze
    from pathlib import Path

    if before == after:
        raise HTTPException(400, "Select two different observations")
    b, a = source_rows([before, after])
    try:
        grid = _alignment_report(b, a)
        if any(
            Path(s["path"]).suffix.lower() in {".tif", ".tiff", ".cog"} for s in (b, a)
        ):
            if not grid["verified"]:
                raise ValueError("Source GeoTIFF grids must be aligned before analysis")
        left, right = _analysis_image(b["path"]), _analysis_image(a["path"])

        def valid_mask(scene, image):
            if Path(scene["path"]).suffix.lower() not in {".tif", ".tiff", ".cog"}:
                return None
            import rasterio
            import numpy as np

            with rasterio.open(scene["path"]) as src:
                masks = src.read_masks(
                    list(range(1, min(3, src.count) + 1)),
                    out_shape=(min(3, src.count), *image.shape[:2]),
                )
                return np.all(masks > 0, axis=0)

        # The retrieval encoder is reused for change typing, so no second
        # checkpoint is loaded. If it is unavailable the screening still runs
        # and the regions simply stay untyped.
        typer = None
        try:
            from app.change_typing import ChangeTyper

            typer = ChangeTyper(cluster_engine)
        except Exception:  # noqa: BLE001 - typing is an enhancement, not a gate
            typer = None

        result = analyze(
            left,
            right,
            source_grid=grid,
            left_valid=valid_mask(b, left),
            right_valid=valid_mask(a, right),
            typer=typer,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc))
    result.update(
        before_id=before,
        after_id=after,
        sources=[b, a],
        processed_at=datetime.now(timezone.utc).isoformat(),
        algorithm_version="registered-screening-v2",
    )
    if save:
        with (DATA / "processing.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    return result


@router.get("/api/compare/readiness")
def readiness(before: int, after: int):
    """Run real checks without adding a processing/review record."""
    try:
        result = registered(before, after, save=False)
        return {
            "analysable": True,
            "before_id": before,
            "after_id": after,
            "method": result["registration"].get("method", "RootSIFT/RANSAC"),
            "usable_fraction": result["usable_fraction"],
            "note": "Ready for visual screening; not a calibrated change conclusion.",
        }
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return {
            "analysable": False,
            "before_id": before,
            "after_id": after,
            "reason": exc.detail,
        }


@router.get("/api/false-alarm/pair")
def false_alarm_pair(before: int, after: int, threshold: float = 0.18):
    """Expose nuisance-signal screening for a selected before/after pair.

    The response is intentionally framed as analyst triage. It identifies
    image-quality and registration risks that can make a pixel difference look
    like a real change; it does not classify the ground object or event.
    """
    from pathlib import Path

    from PIL import Image

    from app.main import (
        _alignment_report,
        _analysis_image,
        _false_alarm_signals,
        _quality_for_path,
    )

    if not 0.01 <= threshold <= 1.0:
        raise HTTPException(400, "threshold must be between 0.01 and 1.0")
    if before == after:
        raise HTTPException(400, "Select two different observations")
    b, a = source_rows([before, after])
    grid = _alignment_report(b, a)
    before_quality = _quality_for_path(Path(b["path"]))
    after_quality = _quality_for_path(Path(a["path"]))
    flags = []
    flags.extend(f"before: {x}" for x in before_quality.get("flags", []))
    flags.extend(f"after: {x}" for x in after_quality.get("flags", []))
    flags.extend(f"alignment: {x}" for x in grid.get("flags", []))
    comparison = {
        "available": False,
        "raw_changed_pixel_ratio": None,
        "adjusted_changed_pixel_ratio": None,
        "suppressed_pixel_fraction": None,
        "note": "Pair-level RGB screening unavailable",
    }
    signals = {
        "flags": [],
        "bright_low_chroma_fraction": None,
        "haze_like_fraction": None,
        "dark_shadow_fraction": None,
        "mean_luminance_shift": None,
        "candidate_pixel_fraction": None,
        "method": "not run",
    }
    try:
        import numpy as np

        left, right = _analysis_image(b["path"]), _analysis_image(a["path"])
        if left.shape[:2] != right.shape[:2]:
            right = np.asarray(
                Image.fromarray(right).resize(
                    (left.shape[1], left.shape[0]), Image.Resampling.BILINEAR
                )
            )
        delta = (
            np.abs(left.astype("float32") - right.astype("float32")).max(axis=2)
            / 255.0
        )
        changed = delta >= threshold
        raw_signals = _false_alarm_signals(left, right)
        nuisance = raw_signals["candidate_mask"]
        adjusted = changed & ~nuisance
        signals = {k: v for k, v in raw_signals.items() if k != "candidate_mask"}
        flags.extend(signals.get("flags", []))
        comparison = {
            "available": True,
            "raw_changed_pixel_ratio": round(float(changed.mean()), 4),
            "adjusted_changed_pixel_ratio": round(float(adjusted.mean()), 4),
            "suppressed_pixel_fraction": round(float((changed & nuisance).mean()), 4),
            "note": "RGB thumbnail nuisance screening; analyst must inspect original imagery",
        }
    except Exception as exc:
        comparison["note"] = f"Pair-level RGB screening unavailable: {exc}"
        flags.append("pair screening unavailable")
    unique_flags = list(dict.fromkeys(flags))
    return {
        "before_id": before,
        "after_id": after,
        "quality_gate": "review required" if unique_flags else "pass",
        "flags": unique_flags,
        "alignment": grid,
        "before_quality": before_quality,
        "after_quality": after_quality,
        "signals": signals,
        "comparison": comparison,
        "threshold": threshold,
        "method": "offline false-alarm suppression heuristics",
        "caveat": "This suppresses common nuisance signals; it is not a labelled atmospheric model.",
    }


def _scene_date(scene: dict) -> str:
    value = scene.get("date")
    if value:
        return str(value)
    found = re.search(r"20\d{2}[-_]\d{2}[-_]\d{2}|20\d{6}|20\d{2}", scene.get("name") or "")
    if found:
        raw = found.group(0).replace("_", "-")
        if re.fullmatch(r"20\d{6}", raw):
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw
    return "date unavailable"


def _false_alarm_status(false_alarm: dict) -> tuple[str, list[str]]:
    flags = list(false_alarm.get("flags") or [])
    if flags:
        return "possible false alarm / review required", flags
    comparison = false_alarm.get("comparison") or {}
    raw = comparison.get("raw_changed_pixel_ratio")
    adjusted = comparison.get("adjusted_changed_pixel_ratio")
    if raw is not None and adjusted is not None and raw - adjusted >= 0.05:
        return "partly suppressed by nuisance screening", [
            "some changed pixels overlapped cloud/shadow/haze-like screening masks"
        ]
    return "not confirmed", ["no strong cloud/shadow/haze/alignment false-alarm signal was confirmed"]


def _cloud_level(signals: dict) -> str:
    bright = signals.get("bright_low_chroma_fraction")
    haze = signals.get("haze_like_fraction")
    if bright is None and haze is None:
        return "unknown"
    value = max(float(bright or 0), float(haze or 0))
    if value >= 0.25:
        return "high"
    if value >= 0.08:
        return "moderate"
    if value > 0:
        return "low"
    return "not indicated"


def _fallback_brief(facts: dict) -> str:
    changed = facts["changed_pixel_ratio_percent"]
    regions = facts["regions"]
    warnings = ", ".join(facts["warnings"][:3])
    if changed < 3:
        level = "No major visual change is measured"
    elif changed < 15:
        level = "A localized visual change is measured"
    else:
        level = "A broad visual difference is measured"
    lines = [
        f"{level} between {facts['date_a']} and {facts['date_b']}.",
        f"The registered comparison reports about {changed:.1f}% changed usable area across {regions} candidate regions.",
    ]
    if warnings:
        lines.append(f"Review warning: {warnings}.")
    lines.append(
        f"False alarm status: {facts['false_alarm']}; cloud/haze indication is {facts['cloud']} and alignment is {facts['alignment']}."
    )
    lines.append(
        "This is an analyst screening brief, not a final object-level change classification."
    )
    return " ".join(lines)


@router.get("/api/llm/compare-report")
def llm_compare_report(before: int, after: int):
    """Generate an offline analyst-language explanation from measured evidence."""
    from app.local_llm import generate_analyst_brief

    b, a = source_rows([before, after])
    try:
        change = registered(before, after, save=False)
    except HTTPException as exc:
        raise exc
    false_alarm = false_alarm_pair(before, after)
    false_alarm_status, warnings = _false_alarm_status(false_alarm)
    warnings = list(dict.fromkeys((change.get("quality_flags") or []) + warnings))
    facts = {
        "before_id": before,
        "after_id": after,
        "date_a": _scene_date(b),
        "date_b": _scene_date(a),
        "scene_a": b.get("name"),
        "scene_b": a.get("name"),
        "changed_pixel_ratio_percent": round(
            float(change.get("adjusted_changed_pixel_ratio") or 0) * 100, 1
        ),
        "usable_overlap_percent": round(float(change.get("usable_fraction") or 0) * 100, 1),
        "regions": int(change.get("region_count") or 0),
        "warnings": warnings,
        "false_alarm": false_alarm_status,
        "cloud": _cloud_level(false_alarm.get("signals") or {}),
        "alignment": (
            "acceptable"
            if change.get("registration", {}).get("matched")
            else "review required"
        ),
        "algorithm": change.get("algorithm_version", "registered-screening-v2"),
    }
    prompt = (
        "Write a concise satellite-image analyst note in simple English. "
        "Use only these facts. Do not invent object types, exact event dates, or military conclusions. "
        f"Facts: {json.dumps(facts, ensure_ascii=True)}"
    )
    llm_text, llm = generate_analyst_brief(prompt)
    return {
        "facts": facts,
        "brief": llm_text or _fallback_brief(facts),
        "llm": llm,
        "source": "registered comparison + false-alarm screening",
        "caveat": (
            "Local LLM wording over measured local evidence; analyst decision is still required."
            if llm_text
            else "Template sentence built from measured local evidence; no language model was used."
            " Analyst decision is still required."
        ),
    }


@router.get("/api/archive/sensors")
def archive_sensors():
    from app.main import conn

    with closing(conn()) as c:
        sensors = [
            r[0]
            for r in c.execute(
                "select distinct sensor from scenes where status='ready' and sensor is not null and trim(sensor)!='' order by sensor"
            )
        ]
        missing = c.execute(
            "select count(*) from scenes where status='ready' and (sensor is null or trim(sensor)='')"
        ).fetchone()[0]
    return {"sensors": sensors, "missing": missing}


class TimelineRequest(BaseModel):
    scene_ids: list[int] = Field(min_length=2, max_length=50)


@router.post("/api/timeline/onset")
def onset(body: TimelineRequest):
    rows = source_rows(list(dict.fromkeys(body.scene_ids)))
    dated = []
    gaps = []
    for row in rows:
        try:
            value = row.get("date") or ""
            if len(value) < 10:
                raise ValueError()
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            dated.append(
                (
                    (
                        stamp.replace(tzinfo=timezone.utc)
                        if stamp.tzinfo is None
                        else stamp
                    ),
                    row,
                )
            )
        except ValueError:
            gaps.append(
                {"scene_id": row["id"], "reason": "Exact acquisition date unavailable"}
            )
    dated.sort(key=lambda x: x[0])
    observations = []
    first = None
    last = None
    if len(dated) >= 2:
        baseline = dated[0][1]
        last = baseline
        for _, row in dated[1:]:
            try:
                result = registered(baseline["id"], row["id"])
                candidate = result["adjusted_changed_pixel_ratio"] >= 0.03
                observations.append(
                    {
                        "scene_id": row["id"],
                        "date": row["date"],
                        "candidate_change": candidate,
                        "changed_fraction": result["adjusted_changed_pixel_ratio"],
                    }
                )
                if candidate and first is None:
                    first = row
                if not candidate and first is None:
                    last = row
            except HTTPException as exc:
                gaps.append({"scene_id": row["id"], "reason": str(exc.detail)})
    year_result = None
    if len(dated) < 2:
        import re

        years = [r for r in rows if re.fullmatch(r"\d{4}", r.get("date") or "")]
        years.sort(key=lambda r: (r["date"], r["id"]))
        year_result = {
            "date_precision": "year",
            "first_supporting_observation": None,
            "last_usable_no_change": None,
            "observations": [],
            "gaps": [],
            "note": "Year-resolution visual screening only. No exact event or acquisition date is inferred.",
        }
        if len(years) >= 2:
            base = years[0]
            previous = base
            for row in years[1:]:
                if row["date"] == base["date"]:
                    year_result["gaps"].append(
                        {
                            "scene_id": row["id"],
                            "reason": "Within-year capture order unknown",
                        }
                    )
                    continue
                try:
                    result = registered(base["id"], row["id"])
                    changed = result["adjusted_changed_pixel_ratio"] >= 0.03
                    item = {"scene_id": row["id"], "year": row["date"]}
                    year_result["observations"].append(
                        dict(item, candidate_change=changed)
                    )
                    if changed and year_result["first_supporting_observation"] is None:
                        year_result["first_supporting_observation"] = item
                        year_result["last_usable_no_change"] = {
                            "scene_id": previous["id"],
                            "year": previous["date"],
                        }
                    elif (
                        not changed
                        and year_result["first_supporting_observation"] is None
                    ):
                        previous = row
                except HTTPException as exc:
                    year_result["gaps"].append(
                        {"scene_id": row["id"], "reason": str(exc.detail)}
                    )
    return {
        "status": (
            "candidate observation interval"
            if first
            else "no supported candidate onset"
        ),
        "date_precision": "day",
        "year_resolution": year_result,
        "first_supporting_observation": (
            {"scene_id": first["id"], "date": first["date"]} if first else None
        ),
        "last_usable_no_change": (
            {"scene_id": last["id"], "date": last["date"]} if last else None
        ),
        "observations": observations,
        "gaps": gaps,
        "note": "Relative to earliest usable baseline; visual candidate onset, not a classified event date. Missing observations leave gaps.",
    }
