from datetime import datetime
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from traveller.models import POI, Category
from traveller.storage import ConflictError, Storage

views_bp = Blueprint("views", __name__)

ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}
DEFAULT_CATEGORIES = [
    Category(name="See", color="#00842b", icon="special_photo_camera"),
    Category(name="Sleep", color="#1010a0", icon="tourism_hotel"),
    Category(name="Do", color="#00842b", icon="special_photo_camera"),
    Category(name="Drink", color="#d00d0d", icon="restaurants"),
    Category(name="Go", color="#1010a0", icon="public_transport_stop_position"),
    Category(name="Eat", color="#d00d0d", icon="restaurants"),
    Category(name="Buy", color="#a71de1", icon="shop_department_store"),
]


def _storage() -> Storage:
    return current_app.config["storage"]


def _sanitize_link(raw: str | None) -> str | None:
    """Return raw if it parses as an http(s)/mailto URL, else None."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        scheme = urlparse(raw).scheme.lower()
    except ValueError:
        return None
    return raw if scheme in ALLOWED_LINK_SCHEMES else None


def _parse_coords(raw: str) -> tuple[float | None, float | None]:
    raw = (raw or "").strip()
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None, None


def _parse_dt(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def _is_card_request() -> bool:
    """True if the htmx request originates from the card/mobile view."""
    return request.headers.get("HX-Target", "").startswith("card-")


def _render_point(poi: POI, guide_id: int) -> str:
    template = "card.j2.html" if _is_card_request() else "row.j2.html"
    return render_template(template, point=poi, guide_id=guide_id)


def _render_edit(
    poi: POI,
    guide_id: int,
    *,
    conflict: bool = False,
    status: int = 200,
) -> Response:
    categories = _storage().list_categories(guide_id)
    template = "mobile_edit.j2.html" if _is_card_request() else "edit_row.j2.html"
    body = render_template(
        template,
        point=poi,
        guide_id=guide_id,
        categories=categories,
        conflict=conflict,
    )
    return Response(body, status=status)


# --- Guide-level routes -------------------------------------------------------


@views_bp.route("/")
def index():
    guides = _storage().list_guides()
    return render_template("index.j2.html", guides=guides)


@views_bp.route("/guide/new", methods=["POST"])
def create_guide():
    name = request.form.get("name", "").strip()
    if not name:
        abort(400, "guide name required")
    guide = _storage().create_guide(name=name)
    # Seed a default category set so the edit form has something to pick from.
    _storage().set_categories(guide.id, list(DEFAULT_CATEGORIES))
    return redirect(url_for("views.guide", guide_id=guide.id))


@views_bp.route("/guide/<int:guide_id>/delete", methods=["POST"])
def delete_guide(guide_id: int):
    _storage().delete_guide(guide_id)
    return redirect(url_for("views.index"))


@views_bp.route("/guide/<int:guide_id>")
def guide(guide_id: int):
    g = _storage().get_guide(guide_id)
    if g is None:
        abort(404)
    points = _storage().list_points(guide_id)
    return render_template("base.j2.html", guide=g, points=points)


# --- POI routes ---------------------------------------------------------------


@views_bp.route("/guide/<int:guide_id>/new_point", methods=["POST"])
def new_point(guide_id: int):
    if _storage().get_guide(guide_id) is None:
        abort(404)
    poi = _storage().create_point(guide_id)
    return _render_edit(poi, guide_id)


@views_bp.route("/guide/<int:guide_id>/point/<uuid>/edit", methods=["GET"])
def point_edit(guide_id: int, uuid: str):
    poi = _storage().get_point(guide_id, uuid)
    if poi is None:
        abort(404)
    return _render_edit(poi, guide_id)


@views_bp.route("/guide/<int:guide_id>/point/<uuid>", methods=["GET", "PUT", "DELETE"])
def point(guide_id: int, uuid: str):
    storage = _storage()

    if request.method == "DELETE":
        storage.delete_point(guide_id, uuid)
        return Response(status=200)

    if request.method == "PUT":
        lat, lon = _parse_coords(request.form.get("coordinates", ""))
        try:
            expected_modified_at = datetime.fromisoformat(
                request.form.get("modified_at", "")
            )
        except ValueError:
            expected_modified_at = None
        try:
            poi = storage.update_point(
                guide_id,
                uuid,
                expected_modified_at=expected_modified_at,
                name=request.form.get("name", "").strip(),
                description=request.form.get("description", "").strip(),
                latitude=lat,
                longitude=lon,
                link=_sanitize_link(request.form.get("link", "")),
                category=request.form.get("category", "").strip(),
                timestamp=_parse_dt(request.form.get("timestamp", "")),
            )
        except KeyError:
            abort(404)
        except ConflictError as exc:
            # Preserve the user's typed values; render edit form populated
            # with what they submitted, not what's on disk. Ship the new
            # modified_at so a second save will overwrite.
            attempted = POI(
                uuid=uuid,
                name=request.form.get("name", ""),
                description=request.form.get("description", ""),
                latitude=lat,
                longitude=lon,
                visited=exc.current.visited,
                link=request.form.get("link", "") or None,
                category=request.form.get("category", "").strip(),
                timestamp=_parse_dt(request.form.get("timestamp", "")),
                modified_at=exc.current.modified_at,
            )
            return _render_edit(attempted, guide_id, conflict=True, status=409)
        return Response(_render_point(poi, guide_id))

    # GET → render the read-only row/card.
    poi = storage.get_point(guide_id, uuid)
    if poi is None:
        abort(404)
    return Response(_render_point(poi, guide_id))


@views_bp.route("/guide/<int:guide_id>/point/<uuid>/visited", methods=["PUT"])
def toggle_visited(guide_id: int, uuid: str):
    visited = request.form.get("visited") == "on"
    _storage().set_visited(guide_id, uuid, visited)
    return Response(status=200)
