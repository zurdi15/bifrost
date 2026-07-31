def test_bookmark_crud_and_ordering(client):
    first = client.post(
        "/api/v1/bookmarks",
        json={"name": "RomM", "url": "https://romm.example", "group": "media"},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/bookmarks", json={"name": "Grafana", "url": "https://grafana.example"}
    ).json()

    rows = client.get("/api/v1/bookmarks").json()
    assert [b["name"] for b in rows] == ["RomM", "Grafana"]  # insertion order
    assert rows[0]["group"] == "media"
    assert rows[1]["icon"] is None

    patched = client.patch(
        f"/api/v1/bookmarks/{second['id']}",
        json={"icon": "📈", "position": 0},
    ).json()
    assert patched["icon"] == "📈"
    rows = client.get("/api/v1/bookmarks").json()
    assert rows[0]["name"] == "Grafana"  # position override reorders

    assert client.post("/api/v1/bookmarks", json={"name": "", "url": "x"}).status_code == 422
    assert client.delete(f"/api/v1/bookmarks/{second['id']}").status_code == 204
    assert client.delete("/api/v1/bookmarks/9999").status_code == 404
    assert len(client.get("/api/v1/bookmarks").json()) == 1
