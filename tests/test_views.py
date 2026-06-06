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
    # Types are global (seeded at DB init), not per-guide.
    cats = [c.name for c in storage.list_categories()]
    assert "Eat" in cats and "See" in cats


def test_create_guide_rejects_blank_name(client):
    assert client.post("/guide/new", data={"name": "  "}).status_code == 400


def test_delete_guide_redirects_home(client, storage):
    g = storage.create_guide(name="X")
    r = client.post(f"/guide/{g.id}/delete")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")
    assert storage.list_guides() == []


def test_rename_guide_via_put(client, storage):
    g = storage.create_guide(name="Old")
    r = client.put(f"/guide/{g.id}/rename", data={"name": "New"})
    assert r.status_code == 200
    assert "New" in r.get_data(as_text=True)
    assert storage.get_guide(g.id).name == "New"


def test_rename_guide_rejects_blank(client, storage):
    g = storage.create_guide(name="Old")
    r = client.put(f"/guide/{g.id}/rename", data={"name": "  "})
    assert r.status_code == 400


def test_reorder_guides_via_post(client, storage):
    g1 = storage.create_guide(name="A")
    g2 = storage.create_guide(name="B")
    r = client.post("/guides/reorder", data={"guide_id": [str(g2.id), str(g1.id)]})
    assert r.status_code == 204
    guides = storage.list_guides()
    assert guides[0].id == g2.id


def test_guide_edit_name_returns_form(client, storage):
    g = storage.create_guide(name="X")
    r = client.get(f"/guide/{g.id}/edit_name")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'name="name"' in body
    assert g.name in body


def test_guide_row_returns_readonly(client, storage):
    g = storage.create_guide(name="X")
    r = client.get(f"/guide/{g.id}/row")
    assert r.status_code == 200
    assert g.name in r.get_data(as_text=True)


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


def test_get_point_renders_card(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.get(f"/guide/{g.id}/point/{poi.uuid}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f"card-poi-{poi.uuid}" in body


def test_get_point_404s_for_missing(client, storage):
    g = storage.create_guide(name="X")
    assert client.get(f"/guide/{g.id}/point/no-such").status_code == 404


def test_put_point_updates_and_renders_card(client, storage):
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


def test_put_point_with_garbage_coords_returns_400_with_user_input(client, storage):
    # Bad coordinates used to silently coerce to NULL on the on-disk row;
    # now they 400 and echo the typed string back with a field-error
    # highlight so the user can fix the typo. The on-disk row is untouched.
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p", latitude=1.0, longitude=2.0))
    r = client.put(
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
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    assert "not a coord" in body
    assert "field-error" in body
    saved = storage.get_point(g.id, poi.uuid)
    assert saved.latitude == 1.0 and saved.longitude == 2.0
    # modified_at should be unchanged (no write happened).
    assert saved.modified_at == poi.modified_at


def test_put_point_with_garbage_timestamp_returns_400_with_user_input(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "",
            "link": "",
            "category": "",
            "timestamp": "not a date",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    assert "not a date" in body
    assert "field-error" in body
    saved = storage.get_point(g.id, poi.uuid)
    assert saved.timestamp is None
    assert saved.name == "p"  # unchanged — bad request, no write


def test_put_point_with_multiple_bad_fields_marks_each(client, storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "bad",
            "link": "",
            "category": "",
            "timestamp": "also-bad",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    # Both raw values echoed back.
    assert "bad" in body and "also-bad" in body
    # Both inputs flagged: the field-error class appears on each bad field.
    assert body.count("field-error") >= 2


def test_put_point_with_empty_coords_and_timestamp_is_valid(client, storage):
    # Empty fields are legitimate (clearing) — must not trigger validation.
    g = storage.create_guide(name="X")
    poi = storage.create_point(
        g.id,
        POI(name="p", latitude=1.0, longitude=2.0),
    )
    r = client.put(
        f"/guide/{g.id}/point/{poi.uuid}",
        data={
            "name": "n",
            "description": "",
            "coordinates": "",
            "link": "",
            "category": "",
            "timestamp": "",
            "modified_at": poi.modified_at.isoformat(),
        },
    )
    assert r.status_code == 200
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


def test_desktop_css_allows_table_to_shrink(client):
    # A long unbreakable string (e.g. a URL) in a description used to blow
    # the desktop list column out, squeezing the map. Two rules are needed:
    # `min-width: 0` on the flex item so it can shrink below its content,
    # and `overflow-wrap: anywhere` on the description so the long token
    # counts as breakable when computing min-content. `break-word` is not
    # enough.
    body = client.get("/static/css/styles.css").get_data(as_text=True)
    desktop = body.split("@media (min-width: 992px)", 1)[1]
    table_block = desktop.split("#table-container", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in table_block

    desc_block = body.split(".poi-description", 1)[1].split("}", 1)[0]
    assert "overflow-wrap: anywhere" in desc_block


def test_desktop_css_forces_map_container_visible(client):
    # The mobile tab-switch JS writes inline `display: none` onto the
    # inactive container. The desktop layout must `!important`-override
    # that for *both* panes, otherwise resizing a window that was last on
    # "List view" leaves the map permanently hidden.
    body = client.get("/static/css/styles.css").get_data(as_text=True)
    desktop = body.split("@media (min-width: 992px)", 1)[1]
    map_block = desktop.split("#map-container", 1)[1].split("}", 1)[0]
    assert "display: block !important" in map_block


def test_main_js_swaps_on_409_and_400(client):
    # htmx 1.x ignores 4xx by default, which silently drops the edit-form
    # response the server already builds for conflict (409) and per-field
    # validation (400). main.js must opt both in to swap, otherwise the
    # UI gives no feedback on a stale-edit or invalid save.
    body = client.get("/static/js/main.js").get_data(as_text=True)
    assert "htmx:beforeSwap" in body
    assert "409" in body
    assert "400" in body
    assert "shouldSwap" in body


def test_main_js_client_side_validates_edit_form(client):
    # The edit "form" is not wrapped in <form>, so htmx skips HTML5
    # validation. Without an explicit client-side pass, a partially-filled
    # datetime-local input submits "" and silently clears the on-disk
    # timestamp (the server can't tell "cleared" from "partial"). main.js
    # must call checkValidity() on the .editing inputs before letting
    # the request go through. Brittle substring check, but it's what
    # we have without a real JS harness.
    body = client.get("/static/js/main.js").get_data(as_text=True)
    assert "htmx:beforeRequest" in body
    assert ".editing" in body
    assert "checkValidity" in body
    assert "preventDefault" in body


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
