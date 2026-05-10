from datetime import datetime

import pytest

from traveller.models import POI, Category
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


def test_categories_round_trip_preserves_order(storage):
    g = storage.create_guide(name="X")
    cats = [Category(name="Z"), Category(name="A"), Category(name="M")]
    storage.set_categories(g.id, cats)
    out = storage.list_categories(g.id)
    assert [c.name for c in out] == ["Z", "A", "M"]


def test_set_categories_replaces_previous(storage):
    g = storage.create_guide(name="X")
    storage.set_categories(g.id, [Category(name="A")])
    storage.set_categories(g.id, [Category(name="B")])
    assert [c.name for c in storage.list_categories(g.id)] == ["B"]


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
