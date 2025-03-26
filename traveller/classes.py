from __future__ import annotations

from csv import DictReader, DictWriter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import gpxpy
import gpxpy.gpx

from traveller.utils import make_element


@dataclass
class POI:
    name: str = ""
    description: str = ""
    latitude: float = 0
    longitude: float = 0
    visited: bool = False
    link: str = ""
    category: str = ""
    uuid: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime | None = None

    def __post_init__(self):
        self.latitude = float(self.latitude)
        self.longitude = float(self.longitude)

        self.visited = self.visited == "True"
        if not self.timestamp:
            self.timestamp = None
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)

    def to_gpx(
        self, categories: dict[str, dict[str, str]] | None
    ) -> gpxpy.gpx.GPXWaypoint:
        waypoint = gpxpy.gpx.GPXWaypoint(
            latitude=self.latitude,
            longitude=self.longitude,
            name=self.name,
            description=self.description,
            type=self.category,
        )
        if self.link:
            waypoint.link = self.link.replace("&", "&amp;")

        waypoint.extensions = [
            make_element(
                "osmand:color", categories.get(self.category, {}).get("color")
            ),
            make_element("osmand:icon", categories.get(self.category, {}).get("icon")),
        ]

        return waypoint


@dataclass
class Guide:
    name: str
    path: Path
    description: str = ""
    link: str = ""
    points: dict[str, POI] = field(default_factory=dict)
    categories: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_zip(self, path: str | Path | None = None) -> None:
        path = self.path or Path(path)
        if path is None:
            raise ValueError("No path given")

        with ZipFile(path, "w") as zf:
            with zf.open("metadata.csv", "w") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    metadata = {
                        "name": self.name,
                        "description": self.description,
                        "link": self.link,
                    }

                    writer = DictWriter(wrapper, metadata.keys())
                    writer.writeheader()
                    writer.writerow(metadata)

            with zf.open("categories.csv", "w") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    writer = DictWriter(wrapper, ["name", "color", "icon"])
                    writer.writeheader()

                    for name, info in self.categories.items():
                        writer.writerow({"name": name, **info})

            with zf.open("POIs.csv", "w") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    writer = DictWriter(wrapper, POI.__annotations__.keys())
                    writer.writeheader()

                    for point in self.points.values():
                        writer.writerow(asdict(point))

    @classmethod
    def from_zip(cls, path: str | Path) -> Guide:
        path = Path(path)
        with ZipFile(path, "r") as zf:
            with zf.open("metadata.csv", "r") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    reader = DictReader(wrapper)
                    metadata = next(iter(reader))

            with zf.open("categories.csv", "r") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    reader = DictReader(wrapper)

                    categories = {info.pop("name"): info for info in reader}

            with zf.open("POIs.csv", "r") as infile:
                with TextIOWrapper(infile, "utf-8") as wrapper:
                    reader = DictReader(wrapper)

                    points = {d["uuid"]: POI(**d) for d in reader}

        return Guide(**metadata, categories=categories, points=points, path=path)

    def to_gpx(self, path: str | Path | None = None) -> str | None:
        gpx = gpxpy.gpx.GPX()
        gpx.nsmap = {"osmand": "https://osmand.net", "traveler": "https://akiiino.me"}
        gpx.name = self.name
        gpx.link = self.link
        gpx.time = datetime.now()

        gpx.metadata_extensions = [
            make_element("osmand:desc", self.description),
            make_element("osmand:article_lang", "en"),
            make_element(
                "osmand:article_title",
                "".join(c if c.isalnum() else "_" for c in self.name),
            ),
        ]

        gpx.waypoints = [
            point.to_gpx(self.categories) for point in self.points.values()
        ]

        if self.categories:
            gpx.extensions = [make_element("osmand:points_groups")]
            gpx.extensions[0].extend(
                [
                    make_element("group", name=name, **category)
                    for name, category in self.categories.items()
                ]
            )

        xml = gpx.to_xml()

        if path:
            path = Path(path)
            if path.is_file():
                with path.open("r") as gpx_file:
                    with path.with_suffix(".gpx.bak").open("w") as bak_file:
                        bak_file.write(gpx_file.read())

            with path.open("w") as gpx_file:
                gpx_file.write(xml)
                return

        return xml
