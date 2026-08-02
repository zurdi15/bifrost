import yaml


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


def test_ui_crud_writes_through_to_yaml(client, tmp_path):
    client.post(
        "/api/v1/bookmarks",
        json={"name": "RomM", "url": "https://romm.example", "group": "media"},
    )
    client.post("/api/v1/bookmarks", json={"name": "Router", "url": "http://192.168.1.1"})

    path = tmp_path / "bookmarks.yml"
    assert yaml.safe_load(path.read_text()) == [
        {"group": "media", "items": [{"name": "RomM", "url": "https://romm.example"}]},
        {"name": "Router", "url": "http://192.168.1.1"},
    ]
    rows = client.get("/api/v1/bookmarks").json()
    assert all(b["source"] == "file" for b in rows)

    # Edits and deletes rewrite the file too.
    client.patch(f"/api/v1/bookmarks/{rows[0]['id']}", json={"icon": "🕹️"})
    assert yaml.safe_load(path.read_text())[0]["items"][0]["icon"] == "🕹️"

    client.delete(f"/api/v1/bookmarks/{rows[1]['id']}")
    assert yaml.safe_load(path.read_text()) == [
        {
            "group": "media",
            "items": [{"name": "RomM", "url": "https://romm.example", "icon": "🕹️"}],
        }
    ]


def test_order_endpoint_reorders_rows_and_file(client, tmp_path):
    ids = [
        client.post(
            "/api/v1/bookmarks", json={"name": name, "url": f"https://{name}.example"}
        ).json()["id"]
        for name in ("alpha", "beta", "gamma")
    ]
    response = client.put(
        "/api/v1/bookmarks/order", json={"ids": [ids[2], ids[0], ids[1]]}
    )
    assert response.status_code == 204
    assert [b["name"] for b in client.get("/api/v1/bookmarks").json()] == [
        "gamma",
        "alpha",
        "beta",
    ]
    data = yaml.safe_load((tmp_path / "bookmarks.yml").read_text())
    assert [entry["name"] for entry in data] == ["gamma", "alpha", "beta"]


def test_create_falls_back_to_db_when_file_unwritable(client, tmp_path):
    # The Docker bind-mount footgun: a directory sits where the file goes.
    (tmp_path / "bookmarks.yml").mkdir()

    row = client.post(
        "/api/v1/bookmarks", json={"name": "Mine", "url": "https://mine.example"}
    ).json()
    assert row["source"] == "ui"

    # DB-only rows stay fully editable.
    patched = client.patch(f"/api/v1/bookmarks/{row['id']}", json={"name": "Mine2"})
    assert patched.status_code == 200
    assert patched.json()["source"] == "ui"
    assert client.delete(f"/api/v1/bookmarks/{row['id']}").status_code == 204
