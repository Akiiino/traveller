from traveller.models import POI


def test_points_geojson_skips_coordless(client, storage):
    g = storage.create_guide(name="X")
    storage.create_point(g.id, POI(name="with-coords", latitude=10.0, longitude=20.0))
    storage.create_point(g.id, POI(name="no-coords"))
    r = client.get(f"/api/guide/{g.id}/points_geojson")
    assert r.status_code == 200
    data = r.get_json()
    assert data["type"] == "FeatureCollection"
    [feat] = data["features"]
    assert feat["properties"]["name"] == "with-coords"
    # GeoJSON is [lon, lat], not [lat, lon].
    assert feat["geometry"]["coordinates"] == [20.0, 10.0]


def test_points_geojson_404s_for_missing_guide(client):
    assert client.get("/api/guide/9999/points_geojson").status_code == 404


def test_categories_endpoint(client, storage):
    g = storage.create_guide(name="X")
    storage.add_category("Hike", "#fff", "ic")
    r = client.get(f"/api/guide/{g.id}/categories")
    assert r.status_code == 200
    body = r.get_json()
    # Endpoint exposes the global type set (defaults + the one we added).
    assert body["Hike"] == {"color": "#fff", "icon": "ic"}
    assert "Eat" in body


def test_categories_404s_for_missing_guide(client):
    assert client.get("/api/guide/9999/categories").status_code == 404


def test_export_gpx_returns_xml_with_attachment_header(client, storage):
    g = storage.create_guide(name="My Trip")
    storage.create_point(g.id, POI(name="p", latitude=1.0, longitude=2.0))
    r = client.get(f"/api/guide/{g.id}/export_gpx")
    assert r.status_code == 200
    assert r.mimetype == "application/gpx+xml"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "My_Trip.gpx" in r.headers["Content-Disposition"]
    assert b"<gpx" in r.data


def test_export_gpx_404s_for_missing_guide(client):
    assert client.get("/api/guide/9999/export_gpx").status_code == 404
