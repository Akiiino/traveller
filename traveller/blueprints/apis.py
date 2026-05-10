from flask import Blueprint, abort, current_app, jsonify

from traveller.gpx import guide_to_gpx
from traveller.storage import Storage

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _storage() -> Storage:
    return current_app.config["storage"]


@api_bp.route("/guide/<int:guide_id>/points_geojson")
def points_geojson(guide_id: int):
    storage = _storage()
    if storage.get_guide(guide_id) is None:
        abort(404)
    features = []
    for poi in storage.list_points(guide_id):
        if not poi.has_coords:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [poi.longitude, poi.latitude],
                },
                "properties": {
                    "id": poi.uuid,
                    "name": poi.name,
                    "description": poi.description,
                    "category": poi.category,
                    "visited": poi.visited,
                    "link": poi.link,
                    "timestamp": (poi.timestamp.isoformat() if poi.timestamp else None),
                },
            }
        )
    return jsonify({"type": "FeatureCollection", "features": features})


@api_bp.route("/guide/<int:guide_id>/categories")
def categories(guide_id: int):
    storage = _storage()
    if storage.get_guide(guide_id) is None:
        abort(404)
    return jsonify(
        {
            c.name: {"color": c.color, "icon": c.icon}
            for c in storage.list_categories(guide_id)
        }
    )


@api_bp.route("/guide/<int:guide_id>/export_gpx")
def export_gpx(guide_id: int):
    storage = _storage()
    guide = storage.get_guide(guide_id)
    if guide is None:
        abort(404)
    xml = guide_to_gpx(
        guide,
        storage.list_categories(guide_id),
        storage.list_points(guide_id),
    )
    filename = "".join(c if c.isalnum() else "_" for c in guide.name) or "guide"
    return current_app.response_class(
        xml,
        mimetype="application/gpx+xml",
        headers={"Content-Disposition": f"attachment; filename={filename}.gpx"},
    )
