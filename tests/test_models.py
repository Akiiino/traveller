from datetime import datetime

from traveller.models import POI, Category, Guide


def test_poi_defaults_have_no_coords():
    poi = POI()
    assert poi.uuid
    assert poi.latitude is None and poi.longitude is None
    assert poi.has_coords is False
    assert poi.visited is False
    assert poi.link is None
    assert poi.timestamp is None


def test_poi_has_coords_requires_both():
    assert POI(latitude=1.0, longitude=2.0).has_coords
    assert not POI(latitude=1.0).has_coords
    assert not POI(longitude=2.0).has_coords
    # 0,0 is now a valid coordinate (not a sentinel).
    assert POI(latitude=0.0, longitude=0.0).has_coords


def test_poi_uuids_are_unique():
    assert POI().uuid != POI().uuid


def test_dataclass_smoke():
    Guide(id=1, name="x")
    Category(name="Eat")
    POI(name="x", timestamp=datetime(2020, 1, 1))
