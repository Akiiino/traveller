from traveller.models import POI


def test_index_lists_guides(client, storage):
    storage.create_guide(name="Trip A")
    storage.create_guide(name="Trip B")
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Trip A" in body and "Trip B" in body


def test_create_guide_redirects_to_guide_page(client, storage):
    r = client.post("/guide/new", data={"name": "New Trip"})
    assert r.status_code == 302
    [g] = storage.list_guides()
    assert g.name == "New Trip"
    assert r.headers["Location"].endswith(f"/guide/{g.id}")
    # Default categories were seeded for the edit form.
    cats = [c.name for c in storage.list_categories(g.id)]
    assert "Eat" in cats and "See" in cats


def test_create_guide_rejects_blank_name(client):
    assert client.post("/guide/new", data={"name": "  "}).status_code == 400


def test_delete_guide_redirects_home(client, storage):
    g = storage.create_guide(name="X")
    r = client.post(f"/guide/{g.id}/delete")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")
    assert storage.list_guides() == []


def test_guide_page_404s_for_missing(client):
    assert client.get("/guide/9999").status_code == 404


def test_guide_page_renders(client, storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="Eiffel"))
    r = client.get(f"/guide/{g.id}")
    assert r.status_code == 200
    assert "Eiffel" in r.get_data(as_text=True)


def test_new_point_returns_edit_form(client, storage):
    g = storage.create_guide(name="X")
    r = client.post(f"/guide/{g.id}/new_point")
    assert r.status_code == 200
    [poi] = storage.list_points(g.id)
    assert poi.uuid in r.get_data(as_text=True)


def test_new_point_404s_for_missing_guide(client):
    assert client.post("/guide/9999/new_point").status_code == 404


def test_new_point_must_be_post(client, storage):
    g = storage.create_guide(name="X")
    # GET should not create a point.
    assert client.get(f"/guide/{g.id}/new_point").status_code == 405
    assert storage.list_points(g.id) == []


def test_get_point_renders_row_by_default(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.get(f"/guide/{g.id}/point/{poi.uuid}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f"row-poi-{poi.uuid}" in body


def test_get_point_renders_card_when_hx_target_is_card(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.get(
        f"/guide/{g.id}/point/{poi.uuid}",
        headers={"HX-Target": f"card-poi-{poi.uuid}"},
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f"card-poi-{poi.uuid}" in body


def test_get_point_404s_for_missing(client, storage):
    g = storage.create_guide(name="X")
    assert client.get(f"/guide/{g.id}/point/no-such").status_code == 404


def test_put_point_updates_and_renders_row(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "renamed",
            "description": "d",
            "coordinates": "10.5, 20.5",
            "link": "https://example.com",
            "category": "Eat",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert r.status_code == 200
    saved = storage.get_point(g.id, poi.uuid)
    assert saved.name == "renamed"
    assert saved.latitude == 10.5 and saved.longitude == 20.5
    assert saved.link == "https://example.com"


def test_put_point_strips_javascript_link(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "",
            "link": "javascript:alert(1)",
            "category": "",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert storage.get_point(g.id, poi.uuid).link is None


def test_put_point_accepts_mailto_link(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "",
            "link": "mailto:hi@example.com",
            "category": "",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert storage.get_point(g.id, poi.uuid).link == "mailto:hi@example.com"


def test_put_point_with_garbage_coords_clears_them(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p", latitude=1.0, longitude=2.0))
    client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "not a coord",
            "link": "",
            "category": "",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    saved = storage.get_point(g.id, poi.uuid)
    assert saved.latitude is None and saved.longitude is None


def test_put_point_conflict_returns_409_with_user_input(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="orig"))
    # First save with the real modified_at: succeeds and bumps modified_at.
    client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "first",
            "description": "",
            "coordinates": "",
            "link": "",
            "category": "",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    # Second save with the now-stale modified_at: 409 + the user's typed values
    # echoed back so they aren't silently lost.
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "user-typed-name",
            "description": "user-typed-desc",
            "coordinates": "1, 2",
            "link": "https://user.example.com",
            "category": "Eat",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert r.status_code == 409
    body = r.get_data(as_text=True)
    assert "user-typed-name" in body
    assert "user-typed-desc" in body
    assert "https://user.example.com" in body
    # On-disk row was NOT overwritten by the rejected save.
    assert storage.get_point(g.id, poi.uuid).name == "first"


def test_main_js_swaps_on_409(client):
    # htmx 1.x ignores 4xx by default, which silently drops the conflict-form
    # response server-side already builds. main.js must opt 409 in to swap.
    # Without this handler the UI gives no feedback on a stale-edit save.
    body = client.get("/static/js/main.js").get_data(as_text=True)
    assert "htmx:beforeSwap" in body
    assert "409" in body
    assert "shouldSwap" in body


def test_put_point_404s_for_missing_uuid(client, storage):
    g = storage.create_guide(name="X")
    r = client.put(
        f"/guide/{g.id}/point/no-such",
        data={
            "name": "x",
            "description": "",
            "coordinates": "",
            "link": "",
            "category": "",
            "timestamp": "",
            "modified_at": "",
        },
    )
    assert r.status_code == 404


def test_delete_point(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.delete(f"/guide/{g.id}/point/{poi.uuid}")
    assert r.status_code == 200
    assert storage.get_point(g.id, poi.uuid) is None


def test_point_edit_renders_form(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.get(f"/guide/{g.id}/point/{poi.uuid}/edit")
    assert r.status_code == 200
    assert poi.uuid in r.get_data(as_text=True)


def test_toggle_visited(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}/visited",
        data={"visited": "on"},
    )
    assert r.status_code == 200
    assert storage.get_point(g.id, poi.uuid).visited is True
    client.put(f"/guide/{g.id}/point/{poi.uuid}/visited", data={})
    assert storage.get_point(g.id, poi.uuid).visited is False
