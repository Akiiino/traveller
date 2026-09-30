from datetime import datetime

import pytest

from traveller.models import POI
from traveller.storage import ConflictError, Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "t.db")


def test_create_and_list_guides(storage):
    assert storage.list_guides() == []
    g1 = storage.create_guide(name="A")
    g2 = storage.create_guide(name="B")
    assert g1.id != g2.id
    names = [g.name for g in storage.list_guides()]
    assert names == ["A", "B"]


def test_get_guide_returns_none_for_missing(storage):
    assert storage.get_guide(999) is None


def test_delete_guide_cascades_points(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p1"))
    storage.create_point(g.id, POI(name="p2"))
    assert len(storage.list_points(g.id)) == 2
    storage.delete_guide(g.id)
    assert storage.get_guide(g.id) is None
    assert storage.list_points(g.id) == []


def test_fresh_db_is_seeded_with_default_types(storage):
    names = [c.name for c in storage.list_categories()]
    assert "See" in names and "Eat" in names


def test_add_category_appends_and_rejects_duplicates(storage):
    assert storage.add_category("Hike", "#123456", "boot") is True
    assert [c.name for c in storage.list_categories()][-1] == "Hike"
    assert storage.add_category("Hike") is False


def test_update_category_changes_color_and_icon(storage):
    storage.add_category("Hike", "#111111", "old")
    storage.update_category("Hike", "#222222", "new")
    [c] = [c for c in storage.list_categories() if c.name == "Hike"]
    assert c.color == "#222222" and c.icon == "new"


def test_rename_category_rewrites_points_across_guides(storage):
    g1 = storage.create_guide(name="A")
    g2 = storage.create_guide(name="B")
    storage.create_point(g1.id, POI(name="p1", category="Eat"))
    storage.create_point(g2.id, POI(name="p2", category="Eat"))
    storage.rename_category("Eat", "Food")
    assert "Food" in [c.name for c in storage.list_categories()]
    assert "Eat" not in [c.name for c in storage.list_categories()]
    assert storage.list_points(g1.id)[0].category == "Food"
    assert storage.list_points(g2.id)[0].category == "Food"


def test_merge_category_reassigns_points_and_drops_old(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p", category="Drink"))
    storage.merge_category("Drink", "Eat")
    assert "Drink" not in [c.name for c in storage.list_categories()]
    assert storage.list_points(g.id)[0].category == "Eat"


def test_delete_category_refuses_when_in_use(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p", category="Eat"))
    assert storage.delete_category("Eat") is False
    assert "Eat" in [c.name for c in storage.list_categories()]


def test_delete_category_succeeds_when_unused(storage):
    storage.add_category("Hike")
    assert storage.delete_category("Hike") is True
    assert "Hike" not in [c.name for c in storage.list_categories()]


def test_category_usage_counts(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="a", category="Eat"))
    storage.create_point(g.id, POI(name="b", category="Eat"))
    storage.create_point(g.id, POI(name="c", category="See"))
    counts = storage.category_usage_counts()
    assert counts.get("Eat") == 2 and counts.get("See") == 1


def test_point_round_trip_preserves_types(storage):
    g = storage.create_guide(name="X")
    poi_in = POI(
        name="p",
        description="d",
        latitude=10.5,
        longitude=20.5,
        visited=True,
        link="https://example.com",
        category="Eat",
        timestamp=datetime(2025, 6, 1, 12, 30),
    )
    storage.create_point(g.id, poi_in)
    poi_out = storage.get_point(g.id, poi_in.uuid)
    assert poi_out.name == "p"
    assert poi_out.latitude == 10.5 and poi_out.longitude == 20.5
    assert poi_out.visited is True
    assert poi_out.link == "https://example.com"
    assert poi_out.timestamp == datetime(2025, 6, 1, 12, 30)


def test_point_with_null_coords(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="p"))
    [poi] = storage.list_points(g.id)
    assert poi.latitude is None and poi.longitude is None
    assert poi.has_coords is False


def test_update_point_bumps_modified_at(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    updated = storage.update_point(
        g.id,
        poi.uuid,
        expected_modified_at=poi.modified_at,
        name="changed",
        description="",
        latitude=None,
        longitude=None,
        link=None,
        category="",
        timestamp=None,
    )
    assert updated.name == "changed"
    assert updated.modified_at >= poi.modified_at


def test_update_point_with_stale_modified_at_raises_conflict(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    # First save advances modified_at.
    storage.update_point(
        g.id,
        poi.uuid,
        expected_modified_at=poi.modified_at,
        name="first",
        description="",
        latitude=None,
        longitude=None,
        link=None,
        category="",
        timestamp=None,
    )
    # Second save with the original (now stale) modified_at should conflict.
    with pytest.raises(ConflictError) as exc_info:
        storage.update_point(
            g.id,
            poi.uuid,
            expected_modified_at=poi.modified_at,
            name="second",
            description="",
            latitude=None,
            longitude=None,
            link=None,
            category="",
            timestamp=None,
        )
    # The exception carries the on-disk POI so the caller can show context.
    assert exc_info.value.current.name == "first"


def test_update_point_missing_uuid_raises_keyerror(storage):
    g = storage.create_guide(name="X")
    with pytest.raises(KeyError):
        storage.update_point(
            g.id,
            "no-such-uuid",
            expected_modified_at=None,
            name="x",
            description="",
            latitude=None,
            longitude=None,
            link=None,
            category="",
            timestamp=None,
        )


def test_set_visited(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    storage.set_visited(g.id, poi.uuid, True)
    assert storage.get_point(g.id, poi.uuid).visited is True
    storage.set_visited(g.id, poi.uuid, False)
    assert storage.get_point(g.id, poi.uuid).visited is False


def test_delete_point(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    storage.delete_point(g.id, poi.uuid)
    assert storage.get_point(g.id, poi.uuid) is None


def test_list_points_orders_unvisited_first(storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="visited", visited=True))
    storage.create_point(g.id, POI(name="unvisited"))
    names = [p.name for p in storage.list_points(g.id)]
    assert names == ["unvisited", "visited"]


# --- Attachments ------------------------------------------------------------


def _pdf(storage, guide_id, uuid, name="ticket.pdf", data=b"%PDF-1.4 fake"):
    return storage.add_attachment(
        guide_id, uuid, filename=name, content_type="application/pdf", data=data
    )


def test_add_and_list_attachments(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    assert storage.get_point(g.id, poi.uuid).attachments == []

    a = _pdf(storage, g.id, poi.uuid)
    assert a.id is not None
    assert a.size == len(b"%PDF-1.4 fake")

    [got] = storage.get_point(g.id, poi.uuid).attachments
    assert (got.id, got.filename, got.content_type, got.size) == (
        a.id,
        "ticket.pdf",
        "application/pdf",
        a.size,
    )
    # list_points carries the same metadata for every point in the guide.
    [listed] = storage.list_points(g.id)
    assert [x.id for x in listed.attachments] == [a.id]


def test_attachments_keep_insertion_order(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    _pdf(storage, g.id, poi.uuid, name="first.pdf")
    _pdf(storage, g.id, poi.uuid, name="second.pdf")
    names = [a.filename for a in storage.get_point(g.id, poi.uuid).attachments]
    assert names == ["first.pdf", "second.pdf"]


def test_get_attachment_returns_metadata_and_bytes(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    a = _pdf(storage, g.id, poi.uuid, data=b"hello")
    meta, data = storage.get_attachment(g.id, poi.uuid, a.id)
    assert data == b"hello"
    assert meta.filename == "ticket.pdf"
    assert storage.get_attachment(g.id, poi.uuid, a.id + 1) is None


def test_attachment_is_scoped_to_guide_and_point(storage):
    g1 = storage.create_guide(name="A")
    g2 = storage.create_guide(name="B")
    p1 = storage.create_point(g1.id, POI(name="p1"))
    p2 = storage.create_point(g2.id, POI(name="p2"))
    a = _pdf(storage, g1.id, p1.uuid)

    assert storage.get_attachment(g2.id, p1.uuid, a.id) is None
    assert storage.get_attachment(g1.id, p2.uuid, a.id) is None
    assert storage.delete_attachment(g2.id, p1.uuid, a.id) is False
    assert storage.get_attachment(g1.id, p1.uuid, a.id) is not None
    assert storage.get_point(g2.id, p2.uuid).attachments == []


def test_add_attachment_to_missing_point_raises_keyerror(storage):
    g = storage.create_guide(name="X")
    with pytest.raises(KeyError):
        storage.add_attachment(
            g.id, "no-such", filename="x.pdf", content_type="", data=b""
        )


def test_delete_attachment(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    a = _pdf(storage, g.id, poi.uuid)
    assert storage.delete_attachment(g.id, poi.uuid, a.id) is True
    assert storage.get_attachment(g.id, poi.uuid, a.id) is None
    assert storage.get_point(g.id, poi.uuid).attachments == []
    assert storage.delete_attachment(g.id, poi.uuid, a.id) is False


def test_deleting_point_cascades_attachments(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    _pdf(storage, g.id, poi.uuid)
    storage.delete_point(g.id, poi.uuid)
    with storage.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    assert n == 0


def test_deleting_guide_cascades_attachments(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    _pdf(storage, g.id, poi.uuid)
    storage.delete_guide(g.id)
    with storage.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    assert n == 0


def test_update_point_result_carries_attachments(storage):
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    a = _pdf(storage, g.id, poi.uuid)
    updated = storage.update_point(
        g.id,
        poi.uuid,
        expected_modified_at=poi.modified_at,
        name="renamed",
        description="",
        latitude=None,
        longitude=None,
        link=None,
        category="",
        timestamp=None,
    )
    assert [x.id for x in updated.attachments] == [a.id]


def test_attachments_do_not_bump_modified_at(storage):
    # Attachments are outside the edit form, so adding or removing one
    # must not make someone's open edit form go stale.
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    before = storage.get_point(g.id, poi.uuid).modified_at
    a = _pdf(storage, g.id, poi.uuid)
    assert storage.get_point(g.id, poi.uuid).modified_at == before
    storage.delete_attachment(g.id, poi.uuid, a.id)
    assert storage.get_point(g.id, poi.uuid).modified_at == before


def test_schema_upgrade_from_v3_adds_attachments(tmp_path):
    # Simulate a pre-attachments database: open once (v4), then roll the
    # version marker back and drop the table, as a v3 file would look.
    path = tmp_path / "old.db"
    Storage(path)
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE attachments")
    conn.execute("UPDATE schema_version SET version = 3 WHERE rowid = 1")
    conn.commit()
    conn.close()

    storage = Storage(path)
    with storage.connect() as conn:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert version == 4
    assert "attachments" in tables
    g = storage.create_guide(name="X")
    poi = storage.create_point(g.id, POI(name="p"))
    _pdf(storage, g.id, poi.uuid)
    assert len(storage.get_point(g.id, poi.uuid).attachments) == 1
