from flask import Blueprint, jsonify, current_app

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/points_geojson")
def points_geojson():
    """Return POIs as GeoJSON for map display"""
    features = []

    for id, point in current_app.config["guide"].points.items():
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [point.longitude, point.latitude],
            },
            "properties": {
                "id": id,
                "name": point.name,
                "description": point.description,
                "category": point.category,
                "visited": point.visited,
                "link": point.link,
                "timestamp": point.timestamp.isoformat() if point.timestamp else None,
            },
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    return jsonify(geojson)


@api_bp.route("/export_gpx", methods=["GET"])
def export_gpx():
    """Export POIs as GPX file"""
    try:
        xml_content = current_app.config["guide"].to_gpx()
        if not xml_content:
            raise ValueError("Failed to generate GPX content")

        return current_app.response_class(
            xml_content,
            mimetype="application/gpx+xml",
            headers={
                "Content-Disposition": f'attachment; filename={current_app.config["guide"].name.replace(" ", "_")}.gpx'
            },
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting GPX: {str(e)}")
        return "Error exporting GPX. Please try again.", 500
