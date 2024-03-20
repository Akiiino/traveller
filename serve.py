from copy import copy, deepcopy
from csv import DictReader, DictWriter
from dataclasses import dataclass
from datetime import datetime

import click
import gpxpy
import gpxpy.gpx
from flask import Flask, Response, render_template, request
from jinja2 import StrictUndefined

with open("base.gpx", "r") as gpx_file:
    BASE_GPX = gpxpy.parse(gpx_file)
    BASE_WAYPOINT = BASE_GPX.waypoints[0]
    BASE_WAYPOINT.name = ""
    BASE_WAYPOINT.description = ""
    BASE_WAYPOINT.type = ""
    BASE_WAYPOINT.link = ""
    BASE_WAYPOINT.latitude = 0.0
    BASE_WAYPOINT.longitude = 0.0

NAME = "Japan"
BANNER_URL = ""
DESCRIPTION = "Japan travel guide"

with open("res.gpx", "r") as gpx_file:
    guide_gpx = gpxpy.parse(gpx_file)


app = Flask(__name__)
app.jinja_env.undefined = StrictUndefined

@app.route("/")
def index():
    return render_template("base.html.j2", waypoints=guide_gpx.waypoints)


@app.route("/waypoint/<int:id>", methods=["DELETE", "PUT", "GET"])
def waypoint(id):
    if request.method == "DELETE":
        del guide_gpx.waypoints[id]
        save_gpx()
        return ("", 200)

    if request.method == "PUT":
        guide_gpx.waypoints[id].name = request.form["name"]
        guide_gpx.waypoints[id].description = request.form["description"]
        guide_gpx.waypoints[id].type = request.form["type"]
        guide_gpx.waypoints[id].link = request.form["link"]
        guide_gpx.waypoints[id].latitude, guide_gpx.waypoints[id].longitude = map(
            float, request.form["coordinates"].replace(",", "").split()
        )
        save_gpx()

    return render_template("row.html.j2", waypoint=guide_gpx.waypoints[id], id=id)


@app.route("/waypoint/<int:id>/edit", methods=["GET"])
def waypoint_edit(id):
    return render_template("edit_row.html.j2", waypoint=guide_gpx.waypoints[id], id=id)


@app.route("/new_waypoint", methods=["GET"])
def new_waypoint():
    guide_gpx.waypoints.append(deepcopy(BASE_WAYPOINT))
    save_gpx()
    return render_template(
        "edit_row.html.j2",
        waypoint=guide_gpx.waypoints[-1],
        id=len(guide_gpx.waypoints) - 1,
    )


def save_gpx():
    with open("res.gpx", "w") as f:
        f.write(guide_gpx.to_xml())


# def build_gpx(fname):
#     gpx = deepcopy(BASE_GPX)
#     gpx.name = "".join(c if c.isalnum() or c == " " else "_" for c in NAME)
#
#     gpx.time = datetime.now()
#     gpx.link = BANNER_URL or None
#
#     gpx.metadata_extensions[0].text = DESCRIPTION
#     gpx.metadata_extensions[2].text = NAME
#
#     waypoints = []
#     with open('waypoints.csv', newline='') as csvfile:
#         reader = DictReader(csvfile)
#
#         for row in reader:
#             waypoint = deepcopy(BASE_WAYPOINT)
#             waypoint.name = row["name"]
#             waypoint.latitude = row["latitude"]
#             waypoint.longitude = row["longitude"]
#             waypoint.description = row["description"]
#             waypoint.link = row["link"]
#             waypoint.type = row["type"]
#             waypoint.extensions[0].text = row.get("color", "")
#             waypoint.extensions[1].text = row.get("icon", "")
#
#             waypoints.append(waypoint)
#
#     gpx.waypoints = waypoints
#
#     gpx.waypoints[0].link = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
#
#     xml = gpx.to_xml()
#
#     with open(fname, "w") as f:
#         f.write(gpx.to_xml())
