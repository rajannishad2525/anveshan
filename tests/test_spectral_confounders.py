"""PS 2.2.3 confounders read from the SCL band that used to be ignored."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.spectral import (SCL_CLASSES, scl_band_index, scl_summary,
                          seasonality_signal, sidecar_scl)


def _write(path, scl_codes, descriptions=("B02", "B03", "B04", "B08", "SCL")):
    """A 5-band L2A-shaped raster whose SCL band holds the given codes."""
    h = w = scl_codes.shape[0]
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=5,
                       dtype="uint16", crs="EPSG:32643",
                       transform=from_origin(700000, 3000000, 10, 10)) as dst:
        for band in range(1, 5):
            dst.write(np.zeros((h, w), "uint16"), band)
        dst.write(scl_codes.astype("uint16"), 5)
        dst.descriptions = descriptions
    return str(path)


def _codes(fill, patch_code=None, patch_fraction=0.0):
    a = np.full((64, 64), fill, dtype="uint16")
    if patch_code is not None:
        rows = int(64 * patch_fraction)
        a[:rows, :] = patch_code
    return a


def test_finds_the_scl_band_by_name(tmp_path):
    path = _write(tmp_path / "s.tif", _codes(5))
    with rasterio.open(path) as src:
        assert scl_band_index(src) == 5


def test_no_scl_band_is_reported_not_guessed(tmp_path):
    path = _write(tmp_path / "n.tif", _codes(5),
                  descriptions=("B02", "B03", "B04", "B08", "B11"))
    assert scl_summary(path)["available"] is False


def test_snow_is_flagged(tmp_path):
    # Snow was confounder 8/9 with nothing behind it; SCL class 11 is the source.
    path = _write(tmp_path / "snow.tif", _codes(5, 11, 0.25))
    out = scl_summary(path)
    assert out["snow_fraction"] == pytest.approx(0.25, abs=0.02)
    assert any("snow" in f for f in out["flags"])


def test_cloud_and_shadow_are_flagged_separately(tmp_path):
    cloudy = scl_summary(_write(tmp_path / "c.tif", _codes(5, 9, 0.40)))
    shady = scl_summary(_write(tmp_path / "s2.tif", _codes(5, 3, 0.30)))
    assert any("cloud" in f for f in cloudy["flags"])
    assert not any("shadow" in f for f in cloudy["flags"])
    assert any("shadow" in f for f in shady["flags"])


def test_speckle_below_five_percent_is_not_flagged(tmp_path):
    path = _write(tmp_path / "tiny.tif", _codes(5, 11, 0.02))
    assert scl_summary(path)["flags"] == []


def test_seasonal_vegetation_swing_is_suspect(tmp_path):
    winter = scl_summary(_write(tmp_path / "w.tif", _codes(5, 4, 0.40)))
    summer = scl_summary(_write(tmp_path / "su.tif", _codes(5, 4, 0.05)))
    season = seasonality_signal(winter, summer)
    assert season["seasonal_suspect"] is True
    assert season["vegetation_swing"] == pytest.approx(0.35, abs=0.02)


def test_same_vegetation_is_not_seasonal(tmp_path):
    a = scl_summary(_write(tmp_path / "a.tif", _codes(5, 4, 0.30)))
    b = scl_summary(_write(tmp_path / "b.tif", _codes(5, 4, 0.28)))
    assert seasonality_signal(a, b)["seasonal_suspect"] is False


def test_sidecar_scl_file_is_used(tmp_path):
    # The demo export ships SCL as a separate *_scl.tif next to *_visual.tif.
    visual = tmp_path / "site_visual.tif"
    with rasterio.open(visual, "w", driver="GTiff", height=32, width=32, count=3,
                       dtype="uint8", crs="EPSG:32643",
                       transform=from_origin(700000, 3000000, 10, 10)) as dst:
        dst.write(np.zeros((3, 32, 32), "uint8"))
    with rasterio.open(tmp_path / "site_scl.tif", "w", driver="GTiff", height=32,
                       width=32, count=1, dtype="uint8", crs="EPSG:32643",
                       transform=from_origin(700000, 3000000, 10, 10)) as dst:
        dst.write(np.full((32, 32), 11, "uint8"), 1)

    assert sidecar_scl(visual) is not None
    out = scl_summary(visual)
    assert out["available"] is True
    assert out["snow_fraction"] == pytest.approx(1.0, abs=0.01)


def test_class_codes_match_the_esa_definition():
    assert SCL_CLASSES[3] == "cloud shadow"
    assert SCL_CLASSES[6] == "water"
    assert SCL_CLASSES[11] == "snow or ice"
