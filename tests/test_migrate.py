"""Tests for the legacy guide.zip importer."""

from zipfile import ZipFile

import pytest

from traveller.migrate import maybe_import
from traveller.storage import Storage

METADATA = "name,description,link\nLegacy Trip,old desc,\n"
CATEGORIES = "name,color,icon\nEat,#d00d0d,restaurants\nSee,#00842b,camera\n"


def _make_zip(path, *, metadata=METADATA, categories=CATEGORIES, pois=""):
    with ZipFile(path, "w") as zf:
        zf.writestr("metadata.csv", metadata)
        zf.writestr("categories.csv", categories)
        zf.writestr(
            "POIs.csv",
            "uuid,name,description,latitude,longitude,visited,link,category,timestamp\n"
            + pois,
        )


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "t.db")


def test_maybe_import_no_zip_is_noop(storage, tmp_path):
    assert maybe_import(storage, tmp_path / "missing.zip") is None
    assert storage.list_guides() == []


def test_maybe_import_renames_zip_after_success(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(zp)
    gid = maybe_import(storage, zp)
    assert isinstance(gid, int)
    assert not zp.exists()
    assert (tmp_path / "guide.zip.imported").exists()


def test_imported_guide_has_metadata_and_categories(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    # A novel category ("Hike") plus one that overlaps the seeded defaults.
    _make_zip(
        zp,
        categories="name,color,icon\nEat,#d00d0d,restaurants\nHike,#123456,boot\n",
    )
    gid = maybe_import(storage, zp)
    g = storage.get_guide(gid)
    assert g.name == "Legacy Trip"
    assert g.description == "old desc"
    # Types are global: the import merges into the shared set, adding new
    # names while leaving existing defaults in place.
    cats = [c.name for c in storage.list_categories()]
    assert "Hike" in cats
    assert "Eat" in cats and "See" in cats


def test_zero_zero_sentinel_becomes_null(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(
        zp,
        pois="u1,p,,0,0,false,,Eat,\n",
    )
    gid = maybe_import(storage, zp)
    [poi] = storage.list_points(gid)
    assert poi.latitude is None and poi.longitude is None


def test_real_coordinates_preserved(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(
        zp,
        pois="u1,p,,10.5,20.5,false,,Eat,\n",
    )
    gid = maybe_import(storage, zp)
    [poi] = storage.list_points(gid)
    assert poi.latitude == 10.5 and poi.longitude == 20.5


def test_legacy_none_string_link_becomes_null(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(
        zp,
        pois="u1,p,,1,2,false,None,Eat,\n",
    )
    gid = maybe_import(storage, zp)
    [poi] = storage.list_points(gid)
    assert poi.link is None


def test_visited_flag_parsed(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(
        zp,
        pois="u1,a,,1,2,true,,Eat,\nu2,b,,1,2,false,,Eat,\n",
    )
    gid = maybe_import(storage, zp)
    by_name = {p.name: p for p in storage.list_points(gid)}
    assert by_name["a"].visited is True
    assert by_name["b"].visited is False


def test_invalid_timestamp_falls_back_to_none(storage, tmp_path):
    zp = tmp_path / "guide.zip"
    _make_zip(
        zp,
        pois="u1,p,,1,2,false,,Eat,not-a-date\n",
    )
    gid = maybe_import(storage, zp)
    [poi] = storage.list_points(gid)
    assert poi.timestamp is None
