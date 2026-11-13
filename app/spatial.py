"""Explicit WGS84 search bounds; unknown georeferencing never matches an AOI."""

import json
import re
from datetime import date
import math


def parse_bbox(value):
    if not value:
        return None
    try:
        bounds = [float(v) for v in value.split(",")]
        west, south, east, north = bounds
        if not all(math.isfinite(v) for v in bounds):
            raise ValueError()
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError()
        return bounds
    except (ValueError, TypeError):
        raise ValueError(
            "AOI must be west,south,east,north in WGS84 degrees; split antimeridian AOIs"
        )


def parse_date_filter(value, label):
    """YYYY-MM-DD or nothing. A malformed date used to be compared as a plain
    string, so it silently matched no scenes and read as "no results"."""
    if not value:
        return ""
    text = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"{label} must be a date as YYYY-MM-DD, got {text!r}")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label} is not a real calendar date: {text!r}")
    return text


def date_span(value):
    """First and last day a stored date can mean: '2024-01-04', '2017' or the
    period '2019-2021'. None when it is not one of those shapes."""
    text = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            date.fromisoformat(text)
            return text, text
        if re.fullmatch(r"\d{4}", text):
            return f"{text}-01-01", f"{text}-12-31"
        m = re.fullmatch(r"(\d{4})-(\d{4})", text)
        if m and m[1] <= m[2]:
            return f"{m[1]}-01-01", f"{m[2]}-12-31"
    except ValueError:
        pass
    return None


def filter_rows(rows, sensor="", bbox="", date_from="", date_to=""):
    bounds = parse_bbox(bbox)
    date_from = parse_date_filter(date_from, "date_from")
    date_to = parse_date_filter(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from is after date_to")
    result = []
    for row in rows:
        if date_from or date_to:
            # Undated imagery cannot be claimed to fall inside a date window,
            # and neither can a period that only partly overlaps it.
            span = date_span(row.get("date"))
            if not span:
                continue
            if date_from and span[0] < date_from:
                continue
            if date_to and span[1] > date_to:
                continue
        if sensor and (row.get("sensor") or "").casefold() != sensor.strip().casefold():
            continue
        if bounds:
            try:
                fp = row.get("footprint")
                fp = json.loads(fp) if isinstance(fp, str) else fp
                if (
                    not isinstance(fp, dict)
                    or not fp.get("crs")
                    or not fp.get("bounds")
                ):
                    continue
                from rasterio.warp import transform_bounds

                w, s, e, n = transform_bounds(
                    fp["crs"], "EPSG:4326", *fp["bounds"], densify_pts=21
                )
                if e <= bounds[0] or w >= bounds[2] or n <= bounds[1] or s >= bounds[3]:
                    continue
            except (ValueError, TypeError, KeyError):
                continue
        result.append(row)
    return result
