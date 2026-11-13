import threading
from app.semantic_clusters import ClusterEngine


def test_expansion_keeps_filtered_archive_and_direct_evidence(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"fixture")
    engine = ClusterEngine(tmp_path, None)
    engine.status = {"state": "ready"}
    engine.groups = [dict(key="place-a", scenes=[{"id": n} for n in range(1, 8)])]
    engine.similar_sites = [dict(key="sites-other", scenes=[{"id": 1}, {"id": 8}])]
    rows = [dict(id=n, path=str(image), date=str(2010 + n)) for n in range(1, 9)]
    direct = [dict(rows[0], structural_match=True, match_score=0.95)]
    result = engine.expand_temporal_results(direct, rows)
    assert {r["id"] for r in result} == set(range(1, 8))
    assert result[0]["match_score"] == 0.95
    assert all(r["match_score"] is None for r in result[1:])
    assert all(r["matched_via_scene_ids"] == [1] for r in result[1:])
    filtered = engine.expand_temporal_results(direct, rows[:3])
    assert {r["id"] for r in filtered} == {1, 2, 3}
    engine.status = {"state": "loading"}
    assert len(engine.expand_temporal_results(direct, rows)) == 1
