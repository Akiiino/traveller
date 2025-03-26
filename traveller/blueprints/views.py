from flask import Blueprint, render_template, current_app

from flask import request, Response
from datetime import datetime
from traveller.classes import POI

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def index():
    """Render the main page with all points"""
    return render_template(
        "base.j2.html",
        points=sorted(
            current_app.config["guide"].points.items(),
            key=lambda x: (x[1].visited, x[1].timestamp is not None, x[1].timestamp),
        ),
    )


@views_bp.route("/point/<id>/edit_mobile", methods=["GET"])
def point_edit_mobile(id):
    """Render mobile edit form for a point"""
    return render_template(
        "mobile_edit.j2.html",
        point=current_app.config["guide"].points[id],
        id=id,
        categories=current_app.config["guide"].categories,
    )


@views_bp.route("/point/<id>/edit", methods=["GET"])
def point_edit(id):
    """Render edit form for a point, with mobile detection"""
    # Check if request is from mobile device
    user_agent = request.headers.get("User-Agent", "").lower()
    is_mobile = (
        "mobile" in user_agent
        or "android" in user_agent
        or "iphone" in user_agent
        or "ipad" in user_agent
    )

    if is_mobile:
        return point_edit_mobile(id)
    else:
        return render_template(
            "edit_row.j2.html",
            point=current_app.config["guide"].points[id],
            id=id,
            categories=current_app.config["guide"].categories,
        )


@views_bp.route("/point/<id>", methods=["DELETE", "PUT", "GET"])
def point(id):
    """Handle CRUD operations for a single point"""
    if request.method == "DELETE":
        del current_app.config["guide"].points[id]
        current_app.config["guide"].to_zip()
        return Response(status=200)

    if request.method == "PUT":
        try:
            coords = request.form["coordinates"].strip()
            lat_lng = [float(x.strip()) for x in coords.split(",") if x.strip()]
            if len(lat_lng) == 2:
                (
                    current_app.config["guide"].points[id].latitude,
                    current_app.config["guide"].points[id].longitude,
                ) = lat_lng
        except (ValueError, IndexError):
            # Keep existing coordinates on error
            pass

        current_app.config["guide"].points[id].name = request.form["name"].strip()
        current_app.config["guide"].points[id].description = request.form[
            "description"
        ].strip()
        current_app.config["guide"].points[id].category = request.form[
            "category"
        ].strip()

        current_app.config["guide"].points[id].link = (
            request.form["link"].strip() or None
        )
        try:
            current_app.config["guide"].points[id].timestamp = datetime.strptime(
                request.form["timestamp"], "%Y-%m-%dT%H:%M"
            )
        except Exception:
            current_app.config["guide"].points[id].timestamp = None

        current_app.config["guide"].to_zip()

    # Check if mobile or desktop view is requested
    user_agent = request.headers.get("User-Agent", "").lower()
    is_mobile = (
        "mobile" in user_agent
        or "android" in user_agent
        or "iphone" in user_agent
        or "ipad" in user_agent
    )

    # Check for specific HX-Request header that might indicate which view we're updating
    hx_target = request.headers.get("HX-Target", "")

    if is_mobile or "poi-card" in hx_target:
        return render_template(
            "card.j2.html", point=current_app.config["guide"].points[id], id=id
        )
    else:
        return render_template(
            "row.j2.html", point=current_app.config["guide"].points[id], id=id
        )


@views_bp.route("/point/<id>/visited", methods=["PUT"])
def toggle_visited(id):
    """Toggle the visited status of a point"""
    current_app.config["guide"].points[id].visited = request.form.get("visited") == "on"
    current_app.config["guide"].to_zip()
    return Response(status=200)


@views_bp.route("/new_point", methods=["GET"])
def new_point():
    """Create a new point and edit it"""
    point = POI()
    current_app.config["guide"].points[point.uuid] = point
    current_app.config["guide"].to_zip()
    return point_edit(point.uuid)
