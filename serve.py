from flask import Flask, Response, render_template, request
from jinja2 import StrictUndefined
from classes import POI, Guide
from io import StringIO
from datetime import datetime

GUIDE_PATH = "guide.zip"
guide = Guide.from_zip(GUIDE_PATH)
print(guide)

app = Flask(__name__)
app.jinja_env.undefined = StrictUndefined


@app.route("/")
def index():
    return render_template(
        "base.j2.html",
        points=sorted(guide.points.items(), key=lambda x: (x[1].timestamp is not None, x[1].timestamp)),
    )


@app.route("/point/<id>", methods=["DELETE", "PUT", "GET"])
def point(id):
    if request.method == "DELETE":
        del guide.points[id]
        guide.to_zip(GUIDE_PATH)

        return Response(status=200)

    if request.method == "PUT":
        guide.points[id].latitude, guide.points[id].longitude = map(
            float, request.form["coordinates"].replace(",", "").split()
        )

        guide.points[id].name = request.form["name"].strip()
        guide.points[id].description = request.form["description"].strip()
        guide.points[id].category = request.form["category"].strip()

        guide.points[id].link = request.form["link"].strip() or None
        try:
            guide.points[id].timestamp = datetime.strptime(request.form["timestamp"], "%Y-%m-%dT%H:%M")
        except Exception:
            guide.points[id].timestamp = None

    guide.to_zip(GUIDE_PATH)

    return render_template("row.j2.html", point=guide.points[id], id=id)


@app.route("/point/<id>/edit", methods=["GET"])
def point_edit(id):
    return render_template(
        "edit_row.j2.html",
        point=guide.points[id],
        id=id,
        categories=guide.categories,
    )


@app.route("/point/<id>/visited", methods=["PUT"])
def toggle_visited(id):
    guide.points[id].visited = request.form.get("visited") == "on"
    guide.to_zip(GUIDE_PATH)

    return Response(status=200)


@app.route("/new_point", methods=["GET"])
def new_point():
    point = POI()
    guide.points[point.uuid] = point
    guide.to_zip(GUIDE_PATH)
    return point_edit(point.uuid)

@app.route("/export_gpx", methods=["GET"])
def export_gpx():
    try:
        string_out = StringIO()
        string_out.write(guide.to_gpx())

        returnfile = string_out.getvalue()
        return Response(
            returnfile,
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment; filename=guide.gpx'}
        )
    except Exception as e:
        return str(e)
