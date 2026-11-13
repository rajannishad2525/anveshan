"""The archive is Sentinel-2 GeoTIFFs, which PIL alone cannot decode."""
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.main import _visual_fingerprint


@pytest.fixture
def sentinel_like_tif(tmp_path):
    """5 bands, uint16 - the shape that silently failed to index."""
    path = tmp_path / "AOI_2023-01-14_s2.tif"
    data = (np.random.default_rng(0).random((5, 64, 64)) * 3000).astype("uint16")
    with rasterio.open(
        path, "w", driver="GTiff", height=64, width=64, count=5,
        dtype="uint16", crs="EPSG:32643", transform=from_origin(700000, 3000000, 10, 10),
    ) as dst:
        dst.write(data)
    return str(path)


def test_pil_alone_cannot_open_it(sentinel_like_tif):
    from PIL import Image, UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        Image.open(sentinel_like_tif).load()


def test_fingerprint_still_works(sentinel_like_tif):
    bins = json.loads(_visual_fingerprint(sentinel_like_tif))
    assert len(bins) == 48
    for channel in range(3):
        assert sum(bins[channel * 16:(channel + 1) * 16]) == pytest.approx(1.0, abs=1e-3)


def _fp(crs, bounds):
    return json.dumps({"crs": crs, "bounds": bounds})


def test_footprint_relation_does_not_claim_unverified_matches():
    from app.main import _footprint_relation

    here = _fp("EPSG:32643", [745370, 3108003, 755610, 3118243])
    far = _fp("EPSG:32643", [600000, 2900000, 610240, 2910240])

    assert _footprint_relation(here, here) == "verified by matching footprint"
    # Two Gujarat AOIs ~150 km apart used to come back "verified".
    assert _footprint_relation(here, far) == "different ground area"
    assert _footprint_relation(here, _fp("EPSG:32644", [745370, 3108003, 755610, 3118243])) \
        == "different ground area"
    assert _footprint_relation(None, here).startswith("unverified")
    assert _footprint_relation("not json", here).startswith("unverified")
