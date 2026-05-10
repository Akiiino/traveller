"""GPX serialization for a guide's POIs (OsmAnd-flavoured)."""

from __future__ import annotations

from datetime import datetime

import gpxpy
import gpxpy.gpx

from traveller.models import POI, Category, Guide
from traveller.utils import make_element


def _poi_to_waypoint(
    poi: POI, categories: dict[str, Category]
) -> gpxpy.gpx.GPXWaypoint:
    cat = categories.get(poi.category)
    waypoint = gpxpy.gpx.GPXWaypoint(
        latitude=poi.latitude,
        longitude=poi.longitude,
        name=poi.name,
        description=poi.description,
        type=poi.category,
    )
    if poi.link:
        waypoint.link = poi.link.replace("&", "&amp;")
    waypoint.extensions = [
        make_element("osmand:color", cat.color if cat else ""),
        make_element("osmand:icon", cat.icon if cat else ""),
    ]
    return waypoint


def guide_to_gpx(guide: Guide, categories: list[Category], points: list[POI]) -> str:
    gpx = gpxpy.gpx.GPX()
    gpx.nsmap = {"osmand": "https://osmand.net", "traveler": "https://akiiino.me"}
    gpx.name = guide.name
    gpx.link = guide.link
    gpx.time = datetime.utcnow()
    gpx.metadata_extensions = [
        make_element("osmand:desc", guide.description),
        make_element("osmand:article_lang", "en"),
        make_element(
            "osmand:article_title",
            "".join(c if c.isalnum() else "_" for c in guide.name),
        ),
    ]

    cat_lookup = {c.name: c for c in categories}
    gpx.waypoints = [_poi_to_waypoint(p, cat_lookup) for p in points if p.has_coords]
    if categories:
        gpx.extensions = [make_element("osmand:points_groups")]
        gpx.extensions[0].extend(
            [
                make_element("group", name=c.name, color=c.color, icon=c.icon)
                for c in categories
            ]
        )
    return gpx.to_xml()
