import pytest

from app.bookmarks_file import load_bookmarks_file, parse_bookmarks_yaml

YAML = """
- group: media
  items:
    - name: RomM
      url: https://romm.example
    - name: Jellyfin
      url: https://jellyfin.example
      icon: "🎬"
- name: Router
  url: http://192.168.1.1
"""


def test_parse_grouped_and_flat():
    entries = parse_bookmarks_yaml(YAML)
    assert [e["name"] for e in entries] == ["RomM", "Jellyfin", "Router"]
    assert entries[0]["group"] == "media"
    assert entries[1]["icon"] == "🎬"
    assert entries[2]["group"] is None
    assert parse_bookmarks_yaml("") == []

    with pytest.raises(ValueError):
        parse_bookmarks_yaml("just a string")
    with pytest.raises(ValueError):
        parse_bookmarks_yaml("- name: no-url-here")


def test_file_sync_mirrors_file_and_leaves_ui_rows(client, tmp_path):
    # A UI bookmark exists first.
    ui_bookmark = client.post(
        "/api/v1/bookmarks", json={"name": "Mine", "url": "https://mine.example"}
    ).json()

    path = tmp_path / "bookmarks.yml"
    path.write_text(YAML)
    assert load_bookmarks_file(path) is True

    rows = client.get("/api/v1/bookmarks").json()
    by_name = {b["name"]: b for b in rows}
    assert set(by_name) == {"Mine", "RomM", "Jellyfin", "Router"}
    assert by_name["RomM"]["source"] == "file"
    assert by_name["Mine"]["source"] == "ui"

    # File rows are read-only through the API.
    file_id = by_name["RomM"]["id"]
    assert client.patch(f"/api/v1/bookmarks/{file_id}", json={"name": "x"}).status_code == 409
    assert client.delete(f"/api/v1/bookmarks/{file_id}").status_code == 409
    assert client.delete(f"/api/v1/bookmarks/{ui_bookmark['id']}").status_code == 204

    # Shrinking the file removes its rows — and only its rows.
    path.write_text("- name: Router\n  url: http://192.168.1.1\n")
    assert load_bookmarks_file(path) is True
    assert [b["name"] for b in client.get("/api/v1/bookmarks").json()] == ["Router"]

    # No change → no resync signal.
    assert load_bookmarks_file(path) is False

    # A broken file keeps the previous state.
    path.write_text("::: not yaml :::")
    assert load_bookmarks_file(path) is False
    assert [b["name"] for b in client.get("/api/v1/bookmarks").json()] == ["Router"]
