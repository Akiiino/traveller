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

from traveller.models import POI
from traveller.storage import ConflictError, Storage

views_bp = Blueprint("views", __name__)

ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}


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


def _category_colors() -> dict[str, str]:
    return {c.name: c.color for c in _storage().list_categories()}


def _render_point(poi: POI, guide_id: int) -> str:
    return render_template(
        "card.j2.html",
        point=poi,
        guide_id=guide_id,
        category_colors=_category_colors(),
    )


def _render_edit(
    poi: POI,
    guide_id: int,
    *,
    conflict: bool = False,
    errors: set[str] | None = None,
    raw: dict[str, str] | None = None,
    status: int = 200,
) -> Response:
    categories = _storage().list_categories()
    body = render_template(
        "mobile_edit.j2.html",
        point=poi,
        guide_id=guide_id,
        categories=categories,
        conflict=conflict,
        errors=errors or set(),
        raw=raw or {},
    )
    return Response(body, status=status)


# --- Guide-level routes -------------------------------------------------------


@views_bp.route("/")
def index():
    guides = _storage().list_guides()
    return render_template("index.j2.html", guides=guides)


# --- Type (global category) routes --------------------------------------------


def _render_type_list(error: str | None = None, status: int = 200) -> Response:
    storage = _storage()
    body = render_template(
        "type_list.j2.html",
        categories=storage.list_categories(),
        usage=storage.category_usage_counts(),
        error=error,
    )
    return Response(body, status=status)


@views_bp.route("/types", methods=["GET"])
def types():
    storage = _storage()
    return render_template(
        "types.j2.html",
        categories=storage.list_categories(),
        usage=storage.category_usage_counts(),
        error=None,
    )


@views_bp.route("/types", methods=["POST"])
def add_type():
    name = request.form.get("name", "").strip()
    color = request.form.get("color", "").strip()
    icon = request.form.get("icon", "").strip()
    if not name:
        return _render_type_list(error="Type name is required.")
    if not _storage().add_category(name, color, icon):
        return _render_type_list(error=f"A type named {name!r} already exists.")
    return _render_type_list()


@views_bp.route("/types/<name>", methods=["PUT"])
def update_type(name: str):
    storage = _storage()
    existing = {c.name for c in storage.list_categories()}
    if name not in existing:
        abort(404)
    new_name = request.form.get("name", "").strip()
    color = request.form.get("color", "").strip()
    icon = request.form.get("icon", "").strip()
    if not new_name:
        return _render_type_list(error="Type name is required.")

    if new_name == name:
        storage.update_category(name, color, icon)
        return _render_type_list()

    if new_name in existing:
        if request.form.get("confirm_merge"):
            storage.merge_category(name, new_name)
            return _render_type_list()
        count = storage.category_usage_counts().get(name, 0)
        body = render_template(
            "type_merge_confirm.j2.html",
            old_name=name,
            new_name=new_name,
            color=color,
            icon=icon,
            count=count,
        )
        return Response(body)

    storage.rename_category(name, new_name)
    return _render_type_list()


@views_bp.route("/types/<name>", methods=["DELETE"])
def delete_type(name: str):
    if not _storage().delete_category(name):
        return _render_type_list(
            error=f"Cannot delete {name!r}: it is still used by some points."
        )
    return _render_type_list()


@views_bp.route("/guide/new", methods=["POST"])
def create_guide():
    name = request.form.get("name", "").strip()
    if not name:
        abort(400, "guide name required")
    guide = _storage().create_guide(name=name)
    return redirect(url_for("views.guide", guide_id=guide.id))


@views_bp.route("/guide/<int:guide_id>/delete", methods=["POST"])
def delete_guide(guide_id: int):
    _storage().delete_guide(guide_id)
    return redirect(url_for("views.index"))


@views_bp.route("/guide/<int:guide_id>/edit_name", methods=["GET"])
def guide_edit_name(guide_id: int):
    g = _storage().get_guide(guide_id)
    if g is None:
        abort(404)
    return render_template("guide_edit_name.j2.html", guide=g)


@views_bp.route("/guide/<int:guide_id>/rename", methods=["PUT"])
def rename_guide(guide_id: int):
    new_name = request.form.get("name", "").strip()
    if not new_name:
        abort(400, "guide name required")
    _storage().rename_guide(guide_id, new_name)
    g = _storage().get_guide(guide_id)
    return render_template("guide_row.j2.html", guide=g)


@views_bp.route("/guide/<int:guide_id>/row", methods=["GET"])
def guide_row(guide_id: int):
    g = _storage().get_guide(guide_id)
    if g is None:
        abort(404)
    return render_template("guide_row.j2.html", guide=g)


@views_bp.route("/guides/reorder", methods=["POST"])
def reorder_guides():
    guide_ids = [int(x) for x in request.form.getlist("guide_id")]
    _storage().reorder_guides(guide_ids)
    return Response(status=204)


@views_bp.route("/guide/<int:guide_id>")
def guide(guide_id: int):
    g = _storage().get_guide(guide_id)
    if g is None:
        abort(404)
    points = _storage().list_points(guide_id)
    return render_template(
        "base.j2.html",
        guide=g,
        points=points,
        category_colors=_category_colors(),
    )


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
        coords_raw = request.form.get("coordinates", "")
        ts_raw = request.form.get("timestamp", "")
        lat, lon = _parse_coords(coords_raw)
        ts = _parse_dt(ts_raw)

        # Validate fields that can be malformed (vs. legitimately empty).
        # Bad input previously got silently coerced to NULL on the on-disk
        # row, hiding typos from the user. Now we 400 and echo the raw text
        # back with a per-field error highlight.
        errors: set[str] = set()
        if coords_raw.strip() and (lat is None or lon is None):
            errors.add("coordinates")
        if ts_raw.strip() and ts is None:
            errors.add("timestamp")

        if errors:
            existing = storage.get_point(guide_id, uuid)
            if existing is None:
                abort(404)
            attempted = POI(
                uuid=uuid,
                name=request.form.get("name", ""),
                description=request.form.get("description", ""),
                latitude=lat,
                longitude=lon,
                visited=existing.visited,
                link=request.form.get("link", "") or None,
                category=request.form.get("category", "").strip(),
                timestamp=ts,
                modified_at=existing.modified_at,
            )
            raw = {"coordinates": coords_raw, "timestamp": ts_raw}
            return _render_edit(attempted, guide_id, errors=errors, raw=raw, status=400)

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
                timestamp=ts,
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
                timestamp=ts,
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
