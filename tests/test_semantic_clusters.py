import numpy as np
from app.semantic_clusters import conservative_groups


def test_neighbour_chains_do_not_merge_dissimilar_endpoints():
    angles = np.radians([0, 20, 40])
    vectors = np.column_stack((np.cos(angles), np.sin(angles))).astype("float32")
    groups, singles = conservative_groups(vectors, 0.90)
    assert sorted(sum(groups, []) + singles) == [0, 1, 2]
    assert not any(0 in g and 2 in g for g in groups)
    for g in groups:
        assert np.min(vectors[g] @ vectors[g].T) >= 0.90


def test_unrelated_vectors_are_not_forced_into_clusters():
    groups, singles = conservative_groups(np.eye(4, dtype="float32"))
    assert groups == []
    assert singles == [0, 1, 2, 3]


def test_similar_vectors_group_without_filenames():
    groups, singles = conservative_groups(
        np.array([[1, 0], [0.99, 0.01], [0, 1]], dtype="float32")
    )
    assert groups == [[0, 1]]
    assert singles == [2]


def test_empty_archive():
    assert conservative_groups([]) == ([], [])


def test_different_geographic_tiles_veto_even_identical_embeddings():
    scenes = [
        {"geometry": {"crs": "EPSG:3857", "bounds": b}}
        for b in ([0, 0, 1, 1], [2, 0, 3, 1])
    ]
    groups, singles = conservative_groups(
        np.array([[1, 0], [1, 0]], dtype="float32"), scenes=scenes
    )
    assert groups == []
    assert singles == [0, 1]
