"""Tests for the global POI-type editor routes (/types)."""

from traveller.models import POI


def test_types_page_lists_default_types(client):
    r = client.get("/types")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "See" in body and "Eat" in body


def test_add_type(client, storage):
    r = client.post("/types", data={"name": "Hike", "color": "#123456", "icon": "boot"})
    assert r.status_code == 200
    names = [c.name for c in storage.list_categories()]
    assert "Hike" in names


def test_add_duplicate_type_is_rejected(client, storage):
    r = client.post("/types", data={"name": "Eat", "color": "#000000", "icon": ""})
    assert r.status_code == 200
    assert "already exists" in r.get_data(as_text=True)
    assert [c.name for c in storage.list_categories()].count("Eat") == 1


def test_add_blank_type_is_rejected(client, storage):
    before = len(storage.list_categories())
    r = client.post("/types", data={"name": "  ", "color": "#000000", "icon": ""})
    assert r.status_code == 200
    assert "required" in r.get_data(as_text=True)
    assert len(storage.list_categories()) == before


def test_update_color_and_icon(client, storage):
    client.post("/types", data={"name": "Hike", "color": "#111111", "icon": "old"})
    r = client.put(
        "/types/Hike", data={"name": "Hike", "color": "#222222", "icon": "new"}
    )
    assert r.status_code == 200
    [c] = [c for c in storage.list_categories() if c.name == "Hike"]
    assert c.color == "#222222" and c.icon == "new"


def test_rename_type_migrates_points(client, storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p", category="Eat"))
    r = client.put("/types/Eat", data={"name": "Food", "color": "#d00d0d", "icon": ""})
    assert r.status_code == 200
    names = [c.name for c in storage.list_categories()]
    assert "Food" in names and "Eat" not in names
    assert storage.list_points(g.id)[0].category == "Food"


def test_rename_onto_existing_prompts_then_merges(client, storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p", category="Drink"))
    # First PUT renames "Drink" onto existing "Eat" → merge confirmation.
    r = client.put("/types/Drink", data={"name": "Eat", "color": "", "icon": ""})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Merge" in body and "confirm_merge" in body
    # Nothing changed yet.
    assert "Drink" in [c.name for c in storage.list_categories()]
    # Confirm the merge.
    r2 = client.put(
        "/types/Drink",
        data={"name": "Eat", "color": "", "icon": "", "confirm_merge": "1"},
    )
    assert r2.status_code == 200
    assert "Drink" not in [c.name for c in storage.list_categories()]
    assert storage.list_points(g.id)[0].category == "Eat"


def test_delete_unused_type(client, storage):
    client.post("/types", data={"name": "Hike", "color": "#000000", "icon": ""})
    r = client.delete("/types/Hike")
    assert r.status_code == 200
    assert "Hike" not in [c.name for c in storage.list_categories()]


def test_delete_in_use_type_is_blocked(client, storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p", category="Eat"))
    r = client.delete("/types/Eat")
    assert r.status_code == 200
    assert "Cannot delete" in r.get_data(as_text=True)
    assert "Eat" in [c.name for c in storage.list_categories()]


def test_update_missing_type_404s(client):
    assert client.put("/types/Nope", data={"name": "X"}).status_code == 404
