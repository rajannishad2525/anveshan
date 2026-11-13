"""PS 2.2: semantic search must keep working WITH the conventional filters.

Every combination of spatial, temporal and sensor filters is exercised here,
because a filter that quietly drops rows looks identical to "no imagery".
"""
import itertools
import json

import pytest

from app.spatial import filter_rows

# Two AOIs far apart, two sensors, three dates.
DELHI = json.dumps({"crs": "EPSG:4326", "bounds": [77.0, 28.0, 77.2, 28.2]})
GUJARAT = json.dumps({"crs": "EPSG:4326", "bounds": [72.0, 22.0, 72.2, 22.2]})

ROWS = [
    {"id": 1, "date": "2023-01-01", "sensor": "Sentinel-2 MSI", "footprint": DELHI},
    {"id": 2, "date": "2023-06-01", "sensor": "Sentinel-2 MSI", "footprint": DELHI},
    {"id": 3, "date": "2024-01-01", "sensor": "LISS-4", "footprint": DELHI},
    {"id": 4, "date": "2023-06-01", "sensor": "LISS-4", "footprint": GUJARAT},
    {"id": 5, "date": "2024-06-01", "sensor": "Sentinel-2 MSI", "footprint": GUJARAT},
]
DELHI_BBOX = "76.9,27.9,77.3,28.3"
IDS = lambda rows: sorted(r["id"] for r in rows)


class TestEachFilterAlone:
    def test_no_filter_keeps_everything(self):
        assert IDS(filter_rows(ROWS)) == [1, 2, 3, 4, 5]

    def test_date_from(self):
        assert IDS(filter_rows(ROWS, date_from="2024-01-01")) == [3, 5]

    def test_date_to(self):
        assert IDS(filter_rows(ROWS, date_to="2023-06-01")) == [1, 2, 4]

    def test_sensor(self):
        assert IDS(filter_rows(ROWS, sensor="LISS-4")) == [3, 4]

    def test_sensor_is_case_insensitive(self):
        assert IDS(filter_rows(ROWS, sensor="liss-4")) == [3, 4]

    def test_bbox(self):
        assert IDS(filter_rows(ROWS, bbox=DELHI_BBOX)) == [1, 2, 3]


class TestFiltersCombine:
    def test_date_range_and_sensor(self):
        kept = filter_rows(ROWS, sensor="Sentinel-2 MSI",
                           date_from="2023-01-01", date_to="2023-12-31")
        assert IDS(kept) == [1, 2]

    def test_bbox_and_sensor(self):
        assert IDS(filter_rows(ROWS, sensor="LISS-4", bbox=DELHI_BBOX)) == [3]

    def test_bbox_and_date(self):
        assert IDS(filter_rows(ROWS, bbox=DELHI_BBOX, date_from="2023-06-01")) == [2, 3]

    def test_all_three_together(self):
        kept = filter_rows(ROWS, sensor="Sentinel-2 MSI", bbox=DELHI_BBOX,
                           date_from="2023-01-01", date_to="2023-12-31")
        assert IDS(kept) == [1, 2]

    def test_a_combination_that_matches_nothing_returns_empty_not_everything(self):
        # The dangerous failure is a filter being ignored, which shows the whole
        # archive and reads as a successful search.
        assert filter_rows(ROWS, sensor="LISS-4", bbox=DELHI_BBOX,
                           date_from="2024-06-01") == []


class TestCombiningNeverAddsRows:
    @pytest.mark.parametrize("sensor,bbox,date_from,date_to", list(itertools.product(
        ["", "LISS-4"], ["", DELHI_BBOX], ["", "2023-06-01"], ["", "2024-01-01"])))
    def test_every_combination_is_a_subset_of_each_filter_alone(
            self, sensor, bbox, date_from, date_to):
        combined = set(IDS(filter_rows(ROWS, sensor, bbox, date_from, date_to)))
        for single in (
            set(IDS(filter_rows(ROWS, sensor=sensor))),
            set(IDS(filter_rows(ROWS, bbox=bbox))),
            set(IDS(filter_rows(ROWS, date_from=date_from, date_to=date_to))),
        ):
            assert combined <= single
