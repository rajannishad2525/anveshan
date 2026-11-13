import sqlite3
from fastapi.testclient import TestClient
import app.main as main


def test_reviews_validate_and_scope_provenance(tmp_path, monkeypatch):
    def connect():
        c = sqlite3.connect(tmp_path / "test.sqlite")
        c.row_factory = sqlite3.Row
        return c

    c = connect()
    c.execute("create table scenes(id integer,path text,sha256 text,imported_at text)")
    c.execute("insert into scenes values(1,'first.png','abc','today')")
    c.commit()
    c.close()
    monkeypatch.setattr(main, "conn", connect)
    monkeypatch.setattr(main, "DATA", tmp_path)
    client = TestClient(main.app)
    payload = {
        "scene_ids": [1],
        "decision": "accepted",
        "note": "Reviewed visible evidence",
    }
    assert client.post("/api/evidence-reviews", json=payload).status_code == 200
    data = client.get("/api/evidence-reviews/export").json()
    assert data["reviews"][0]["scenes"][0]["sha256"] == "abc"
    assert (
        client.post(
            "/api/evidence-reviews", json=dict(payload, scene_ids=[2])
        ).status_code
        == 409
    )
    c = connect()
    c.execute("update scenes set path='second.png',sha256='def'")
    c.commit()
    c.close()
    assert client.get("/api/evidence-reviews").json() == []
    assert (tmp_path / "evidence_reviews.jsonl").exists()
