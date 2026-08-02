import pytest

from app.bookmarks_file import (
    dump_bookmarks_yaml,
    load_bookmarks_file,
    parse_bookmarks_yaml,
    resolve_bookmarks_path,
)
from app.config import settings

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


def test_dump_roundtrip():
    entries = parse_bookmarks_yaml(YAML)
    assert parse_bookmarks_yaml(dump_bookmarks_yaml(entries)) == entries
    assert parse_bookmarks_yaml(dump_bookmarks_yaml([])) == []


def test_file_sync_mirrors_external_edits(client, tmp_path):
    # A UI-created bookmark writes through, so the file owns it…
    client.post("/api/v1/bookmarks", json={"name": "Mine", "url": "https://mine.example"})

    # …and an external rewrite of the file is authoritative: it replaces the
    # whole set, UI-created entries included.
    path = tmp_path / "bookmarks.yml"
    path.write_text(YAML)
    assert load_bookmarks_file(path) is True

    rows = client.get("/api/v1/bookmarks").json()
    by_name = {b["name"]: b for b in rows}
    assert set(by_name) == {"RomM", "Jellyfin", "Router"}
    assert all(b["source"] == "file" for b in rows)

    # File rows are editable through the API and write back to the file.
    file_id = by_name["RomM"]["id"]
    assert client.patch(f"/api/v1/bookmarks/{file_id}", json={"name": "RomM2"}).status_code == 200
    assert "RomM2" in path.read_text()
    assert client.delete(f"/api/v1/bookmarks/{file_id}").status_code == 204
    assert "RomM2" not in path.read_text()

    # Shrinking the file removes its rows.
    path.write_text("- name: Router\n  url: http://192.168.1.1\n")
    assert load_bookmarks_file(path) is True
    assert [b["name"] for b in client.get("/api/v1/bookmarks").json()] == ["Router"]

    # No change → no resync signal.
    assert load_bookmarks_file(path) is False

    # A broken file keeps the previous state.
    path.write_text("::: not yaml :::")
    assert load_bookmarks_file(path) is False
    assert [b["name"] for b in client.get("/api/v1/bookmarks").json()] == ["Router"]

    # A directory in the file's place (Docker bind-mount of a missing host
    # file) is ignored, not fatal.
    directory = tmp_path / "as-dir"
    directory.mkdir()
    assert load_bookmarks_file(directory) is False


def test_resolve_accepts_both_extensions(client, tmp_path, monkeypatch):
    # client's fixture already points settings.data_dir at its own tmp dir;
    # repoint it here to exercise resolution.
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "bookmarks_file", None)

    assert resolve_bookmarks_path() == tmp_path / "bookmarks.yml"  # default
    (tmp_path / "bookmarks.yaml").write_text("")
    assert resolve_bookmarks_path() == tmp_path / "bookmarks.yaml"
    (tmp_path / "bookmarks.yml").write_text("")
    assert resolve_bookmarks_path() == tmp_path / "bookmarks.yml"  # .yml wins

    monkeypatch.setattr(settings, "bookmarks_file", tmp_path / "custom.yaml")
    assert resolve_bookmarks_path() == tmp_path / "custom.yaml"
