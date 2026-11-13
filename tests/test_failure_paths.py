"""What the app does with broken input, not with good input.

Every case here was found by feeding the running app real bad files, and
every one of them used to pass silently.
"""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.main import _inspect
from app.spatial import filter_rows, parse_date_filter


def _write_geotiff(path, bands=3, crs="EPSG:32643"):
    data = (np.random.default_rng(0).random((bands, 64, 64)) * 3000).astype("uint16")
    with rasterio.open(path, "w", driver="GTiff", height=64, width=64, count=bands,
                       dtype="uint16", crs=crs,
                       transform=from_origin(700000, 3000000, 10, 10)) as dst:
        dst.write(data)
    return path


class TestIntakeRejectsUnusableFiles:
    def test_a_truncated_geotiff_is_rejected(self, tmp_path):
        # The header of a half-written GeoTIFF still reports size, CRS and band
        # count, so header-only intake marked it ready and the corruption only
        # surfaced later during indexing.
        whole = _write_geotiff(tmp_path / "whole.tif")
        raw = whole.read_bytes()
        cut = tmp_path / "truncated.tif"
        cut.write_bytes(raw[: len(raw) // 2])

        assert _inspect(cut)["error"], "a truncated GeoTIFF must not be accepted"

    def test_an_intact_geotiff_is_accepted(self, tmp_path):
        assert not _inspect(_write_geotiff(tmp_path / "fine.tif"))["error"]

    def test_an_empty_file_is_rejected(self, tmp_path):
        empty = tmp_path / "zero.tif"
        empty.write_bytes(b"")
        assert _inspect(empty)["error"]

    def test_a_text_file_wearing_a_tif_extension_is_rejected(self, tmp_path):
        fake = tmp_path / "notes.tif"
        fake.write_text("this is not imagery")
        assert _inspect(fake)["error"]

    def test_an_unsupported_extension_is_skipped_not_errored(self, tmp_path):
        other = tmp_path / "readme.txt"
        other.write_text("hello")
        assert _inspect(other) is None

    def test_missing_crs_is_recorded_so_the_operator_can_see_it(self, tmp_path):
        out = _inspect(_write_geotiff(tmp_path / "nocrs.tif", crs=None))
        assert out["crs"] is None

    def test_a_fully_transparent_tile_is_rejected(self, tmp_path):
        # Map services answer a missing period with an all-transparent PNG.
        # It decodes fine, so it used to be imported as a ready scene.
        from PIL import Image

        empty = tmp_path / "z16_1_2.png"
        Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(empty)
        assert "transparent" in _inspect(empty)["error"]

    def test_a_partly_transparent_tile_is_accepted(self, tmp_path):
        from PIL import Image

        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        im.paste((90, 120, 60, 255), (0, 0, 32, 64))
        im.save(tmp_path / "edge.png")
        assert not _inspect(tmp_path / "edge.png")["error"]


class TestIntakeDates:
    """Dates come from the file name first, then from the folder name."""

    def _png(self, folder, name="z16_46874_27358.png"):
        from PIL import Image

        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), (40, 90, 20)).save(folder / name)
        return folder / name

    @pytest.mark.parametrize("folder,expected", [
        ("2017", "2017"),
        ("2016-2012", "2012-2016"),
        ("2021-19", "2019-2021"),      # Bhuvan period label "2021-19"
        ("2024-22", "2022-2024"),
        ("2019-18_2017", "2017-2019"),
    ])
    def test_period_folder_labels(self, tmp_path, folder, expected):
        assert _inspect(self._png(tmp_path / folder))["date"] == expected

    def test_iso_date_in_file_name_wins(self, tmp_path):
        p = self._png(tmp_path / "same_location", "2024-01-04_winter_cloud_candidate.png")
        assert _inspect(p)["date"] == "2024-01-04"

    def test_compact_date_in_file_name(self, tmp_path):
        p = self._png(tmp_path / "x", "S2A_20240223_clear.png")
        assert _inspect(p)["date"] == "2024-02-23"

    def test_impossible_date_in_file_name_is_ignored(self, tmp_path):
        p = self._png(tmp_path / "x", "scan_2024-02-30.png")
        assert _inspect(p)["date"] is None

    def test_tile_numbers_are_not_read_as_dates(self, tmp_path):
        p = self._png(tmp_path / "tiles", "z16_20240_20231.png")
        assert _inspect(p)["date"] is None


class TestDateFilterRejectsNonsense:
    @pytest.mark.parametrize("bad", ["13-13-2026", "2023-1-1", "2023-02-30", "yesterday"])
    def test_a_malformed_date_is_refused(self, bad):
        # These used to be compared as plain strings, so they matched nothing
        # and the operator read an empty list as "no imagery exists".
        with pytest.raises(ValueError):
            parse_date_filter(bad, "date_from")

    def test_a_real_date_passes_through(self):
        assert parse_date_filter("2023-01-01", "date_from") == "2023-01-01"

    def test_no_date_means_no_filter(self):
        assert parse_date_filter("", "date_from") == ""

    def test_a_reversed_range_is_refused(self):
        with pytest.raises(ValueError):
            filter_rows([], date_from="2024-01-01", date_to="2023-01-01")

    @pytest.mark.parametrize("scene,window,kept", [
        ("2017", ("2017-01-01", "2017-12-31"), True),       # a year-only date in its own year
        ("2017", ("2017-06-01", "2017-12-31"), False),      # could be before June
        ("2019-2021", ("2019-01-01", "2021-12-31"), True),
        ("2019-2021", ("2020-01-01", "2020-12-31"), False),  # not provably inside 2020
        ("2024-01-04", ("2024-01-01", "2024-01-31"), True),
        ("2024-01-04", ("", "2023-12-31"), False),
        ("2017", ("2016-01-01", ""), True),
        ("garbled", ("2016-01-01", ""), False),
    ])
    def test_periods_must_lie_inside_the_window(self, scene, window, kept):
        rows = [{"date": scene}]
        assert (filter_rows(rows, date_from=window[0], date_to=window[1]) == rows) is kept


class TestDateFilterSelectsTheRightRows:
    ROWS = [{"date": "2023-01-01"}, {"date": "2023-06-01"}, {"date": "2024-01-01"},
            {"date": None}]

    def test_from_is_inclusive(self):
        kept = filter_rows(self.ROWS, date_from="2023-06-01")
        assert [r["date"] for r in kept] == ["2023-06-01", "2024-01-01"]

    def test_to_is_inclusive(self):
        kept = filter_rows(self.ROWS, date_to="2023-06-01")
        assert [r["date"] for r in kept] == ["2023-01-01", "2023-06-01"]

    def test_a_scene_without_a_date_is_excluded_by_a_date_filter(self):
        # Undated imagery cannot be claimed to fall inside a date window.
        assert all(r["date"] for r in filter_rows(self.ROWS, date_from="2023-01-01"))


def test_reversed_range_is_refused_by_the_shared_filter():
    # The SQL search endpoints build their own WHERE clause, so the range check
    # has to run there too, not only inside filter_rows.
    with pytest.raises(ValueError):
        filter_rows([{"date": "2023-05-05"}], date_from="2024-01-01", date_to="2023-01-01")
