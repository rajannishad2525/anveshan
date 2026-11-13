import numpy as np
from PIL import Image
import cv2
from app.place_matching import local_features, verify_place, group_places, period_info
from app.semantic_clusters import compatible_footprints


def textured(seed):
    rng = np.random.default_rng(seed)
    image = np.full((320, 320), 40, dtype="uint8")
    for _ in range(160):
        x, y = rng.integers(10, 290, 2)
        w, h = rng.integers(5, 25, 2)
        cv2.rectangle(
            image,
            (int(x), int(y)),
            (int(x + w), int(y + h)),
            int(rng.integers(60, 255)),
            -1,
        )
    return image


def test_structure_survives_rotation_brightness_and_partial_change():
    a = textured(21)
    matrix = cv2.getRotationMatrix2D((160, 160), 4, 1.01)
    b = cv2.warpAffine(a, matrix, (320, 320))
    b = np.clip(b.astype("float32") * 0.65 + 30, 0, 255).astype("uint8")
    b[130:180, 130:180] = 120
    proof = verify_place(
        local_features(Image.fromarray(a)), local_features(Image.fromarray(b))
    )
    assert proof["matched"], proof
    assert proof["inliers"] >= 12


def test_different_structures_do_not_match():
    assert not verify_place(
        local_features(Image.fromarray(textured(1))),
        local_features(Image.fromarray(textured(2))),
    )["matched"]


def test_seasonal_visual_score_does_not_split_known_same_area():
    scenes = [
        {"geometry": {"crs": "EPSG:3857", "bounds": [0, 0, 100, 100]}} for _ in range(3)
    ]
    groups, singles, proof = group_places(
        scenes, np.eye(3, dtype="float32"), [None] * 3, compatible_footprints
    )
    assert groups == [[0, 1, 2]] and singles == []
    assert all(e["method"] == "embedded footprint agreement" for a, b, e in proof)


def test_same_filename_cannot_create_a_location_match():
    scenes = [{"name": "same.png"}, {"name": "same.png"}]
    features = [local_features(Image.fromarray(textured(seed))) for seed in (3, 4)]
    groups, singles, _ = group_places(
        scenes,
        np.array([[1, 0], [1, 0]], dtype="float32"),
        features,
        compatible_footprints,
    )
    assert groups == [] and singles == [0, 1]


def test_compact_folder_years_are_ranges_not_capture_dates():
    assert period_info("archive/2024-22/tile.png")["period_label"] == "2022–2024"
    assert period_info("archive/2019-18_2017/tile.png")["period_label"] == "2017–2019"
    assert (
        period_info("uuid2026abcd/unknown/tile.png")["period_label"]
        == "date unavailable"
    )
