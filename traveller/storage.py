"""SQLite-backed storage for guides, categories, and POIs.

Concurrency model: WAL journaling, one connection per request. Multiple
gunicorn workers can share the database safely; SQLite serializes writes
internally. Conflict detection on POI updates is handled at the row level
via the modified_at column.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from traveller.models import POI, Category, Guide

SCHEMA_VERSION = 3

# The global set of POI types. Seeded into a brand-new database only.
DEFAULT_CATEGORIES = [
    Category(name="See", color="#00842b", icon="special_photo_camera"),
    Category(name="Sleep", color="#1010a0", icon="tourism_hotel"),
    Category(name="Do", color="#00842b", icon="special_photo_camera"),
    Category(name="Drink", color="#d00d0d", icon="restaurants"),
    Category(name="Go", color="#1010a0", icon="public_transport_stop_position"),
    Category(name="Eat", color="#d00d0d", icon="restaurants"),
    Category(name="Buy", color="#a71de1", icon="shop_department_store"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    rowid INTEGER PRIMARY KEY CHECK (rowid = 1),
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS guides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    color TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS points (
    uuid TEXT PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    latitude REAL,
    longitude REAL,
    visited INTEGER NOT NULL DEFAULT 0,
    link TEXT,
    category TEXT NOT NULL DEFAULT '',
    timestamp TEXT,
    modified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS points_guide_idx ON points(guide_id);
"""


class ConflictError(Exception):
    """Raised when a POI update is rejected because the row was modified
    by someone else since the client last read it."""

    def __init__(self, current: POI):
        super().__init__("POI was modified concurrently")
        self.current = current


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _row_to_poi(row: sqlite3.Row) -> POI:
    return POI(
        uuid=row["uuid"],
        name=row["name"],
        description=row["description"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        visited=bool(row["visited"]),
        link=row["link"],
        category=row["category"],
        timestamp=_parse_dt(row["timestamp"]),
        modified_at=_parse_dt(row["modified_at"]),
    )


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cur = conn.execute("SELECT version FROM schema_version WHERE rowid = 1")
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (rowid, version) VALUES (1, ?)",
                    (SCHEMA_VERSION,),
                )
                # Fresh database: seed the global type set so the POI edit form
                # has something to pick from.
                conn.executemany(
                    "INSERT INTO categories (name, color, icon, sort_order) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        (c.name, c.color, c.icon, i)
                        for i, c in enumerate(DEFAULT_CATEGORIES)
                    ],
                )
            else:
                version = row["version"]
                if version < 2:
                    conn.execute(
                        "ALTER TABLE guides "
                        "ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
                    )
                    guide_rows = conn.execute(
                        "SELECT id FROM guides ORDER BY name"
                    ).fetchall()
                    for i, r in enumerate(guide_rows):
                        conn.execute(
                            "UPDATE guides SET sort_order = ? WHERE id = ?",
                            (i, r["id"]),
                        )
                    conn.execute(
                        "UPDATE schema_version SET version = 2 WHERE rowid = 1"
                    )
                if version < 3:
                    # Collapse the per-guide (guide_id, name) categories table
                    # into a single global table keyed by name. Duplicate names
                    # across guides (the default set is identical per guide) are
                    # deduplicated; points.category is a plain string, so no
                    # point rows need rewriting.
                    conn.executescript(
                        """
                        CREATE TABLE categories_global (
                            name TEXT PRIMARY KEY,
                            color TEXT NOT NULL DEFAULT '',
                            icon TEXT NOT NULL DEFAULT '',
                            sort_order INTEGER NOT NULL DEFAULT 0
                        );
                        INSERT INTO categories_global (name, color, icon, sort_order)
                            SELECT name, color, icon, MIN(sort_order)
                            FROM categories GROUP BY name;
                        DROP TABLE categories;
                        ALTER TABLE categories_global RENAME TO categories;
                        """
                    )
                    conn.execute(
                        "UPDATE schema_version SET version = 3 WHERE rowid = 1"
                    )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    # --- Guides -----------------------------------------------------------

    def list_guides(self) -> list[Guide]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, description, link, sort_order "
                "FROM guides ORDER BY sort_order, name"
            ).fetchall()
        return [Guide(**dict(r)) for r in rows]

    def get_guide(self, guide_id: int) -> Guide | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, name, description, link, sort_order "
                "FROM guides WHERE id = ?",
                (guide_id,),
            ).fetchone()
        return Guide(**dict(row)) if row else None

    def create_guide(self, name: str, description: str = "", link: str = "") -> Guide:
        with self.connect() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM guides"
            ).fetchone()[0]
            sort_order = max_order + 1
            cur = conn.execute(
                "INSERT INTO guides (name, description, link, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, description, link, sort_order, datetime.utcnow().isoformat()),
            )
            gid = cur.lastrowid
        return Guide(
            id=gid, name=name, description=description, link=link, sort_order=sort_order
        )

    def rename_guide(self, guide_id: int, new_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE guides SET name = ? WHERE id = ?",
                (new_name, guide_id),
            )

    def reorder_guides(self, guide_ids: list[int]) -> None:
        """Set sort_order for each guide based on position in guide_ids."""
        with self.connect() as conn:
            conn.execute("BEGIN")
            for i, gid in enumerate(guide_ids):
                conn.execute("UPDATE guides SET sort_order = ? WHERE id = ?", (i, gid))
            conn.execute("COMMIT")

    def delete_guide(self, guide_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM guides WHERE id = ?", (guide_id,))

    # --- Categories (global POI types) ------------------------------------

    def list_categories(self) -> list[Category]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name, color, icon FROM categories ORDER BY sort_order, name"
            ).fetchall()
        return [Category(**dict(r)) for r in rows]

    def category_usage_counts(self) -> dict[str, int]:
        """Map of category name -> number of POIs using it, across all guides."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS n FROM points GROUP BY category"
            ).fetchall()
        return {r["category"]: r["n"] for r in rows}

    def add_category(self, name: str, color: str = "", icon: str = "") -> bool:
        """Append a new type. Returns False if the name already exists."""
        with self.connect() as conn:
            next_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories"
            ).fetchone()[0]
            cur = conn.execute(
                "INSERT OR IGNORE INTO categories (name, color, icon, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (name, color, icon, next_order),
            )
            return cur.rowcount > 0

    def update_category(self, name: str, color: str, icon: str) -> None:
        """Update color/icon of an existing type (no rename)."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE categories SET color = ?, icon = ? WHERE name = ?",
                (color, icon, name),
            )

    def rename_category(self, old: str, new: str) -> None:
        """Rename a type and rewrite every POI that used it. Precondition: the
        target name does not already exist (callers use merge_category for that
        case)."""
        with self.connect() as conn:
            conn.execute("BEGIN")
            conn.execute("UPDATE categories SET name = ? WHERE name = ?", (new, old))
            conn.execute(
                "UPDATE points SET category = ? WHERE category = ?", (new, old)
            )
            conn.execute("COMMIT")

    def merge_category(self, old: str, into: str) -> None:
        """Reassign every POI from `old` to the existing type `into`, then drop
        `old`. Merged POIs adopt `into`'s color/icon."""
        with self.connect() as conn:
            conn.execute("BEGIN")
            conn.execute(
                "UPDATE points SET category = ? WHERE category = ?", (into, old)
            )
            conn.execute("DELETE FROM categories WHERE name = ?", (old,))
            conn.execute("COMMIT")

    def delete_category(self, name: str) -> bool:
        """Delete a type, refusing if any POI in any guide still uses it.
        Returns True on success, False if the type is in use."""
        with self.connect() as conn:
            in_use = conn.execute(
                "SELECT 1 FROM points WHERE category = ? LIMIT 1", (name,)
            ).fetchone()
            if in_use is not None:
                return False
            conn.execute("DELETE FROM categories WHERE name = ?", (name,))
            return True

    # --- Points -----------------------------------------------------------

    def list_points(self, guide_id: int) -> list[POI]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM points WHERE guide_id = ? "
                "ORDER BY visited, timestamp IS NULL, timestamp",
                (guide_id,),
            ).fetchall()
        return [_row_to_poi(r) for r in rows]

    def get_point(self, guide_id: int, uuid: str) -> POI | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM points WHERE guide_id = ? AND uuid = ?",
                (guide_id, uuid),
            ).fetchone()
        return _row_to_poi(row) if row else None

    def create_point(self, guide_id: int, poi: POI | None = None) -> POI:
        if poi is None:
            poi = POI()
        poi.modified_at = datetime.utcnow()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO points (uuid, guide_id, name, description, latitude, "
                "longitude, visited, link, category, timestamp, modified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    poi.uuid,
                    guide_id,
                    poi.name,
                    poi.description,
                    poi.latitude,
                    poi.longitude,
                    int(poi.visited),
                    poi.link,
                    poi.category,
                    _iso(poi.timestamp),
                    _iso(poi.modified_at),
                ),
            )
        return poi

    def update_point(
        self,
        guide_id: int,
        uuid: str,
        *,
        expected_modified_at: datetime | None,
        name: str,
        description: str,
        latitude: float | None,
        longitude: float | None,
        link: str | None,
        category: str,
        timestamp: datetime | None,
    ) -> POI:
        """Update a POI with optimistic concurrency. If expected_modified_at
        does not match the row's current value, raise ConflictError carrying
        the on-disk POI."""
        new_modified_at = datetime.utcnow()
        with self.connect() as conn:
            current = conn.execute(
                "SELECT * FROM points WHERE guide_id = ? AND uuid = ?",
                (guide_id, uuid),
            ).fetchone()
            if current is None:
                raise KeyError(uuid)
            if (
                expected_modified_at is not None
                and _parse_dt(current["modified_at"]) != expected_modified_at
            ):
                raise ConflictError(_row_to_poi(current))
            conn.execute(
                "UPDATE points SET name = ?, description = ?, latitude = ?, "
                "longitude = ?, link = ?, category = ?, timestamp = ?, "
                "modified_at = ? WHERE guide_id = ? AND uuid = ?",
                (
                    name,
                    description,
                    latitude,
                    longitude,
                    link,
                    category,
                    _iso(timestamp),
                    _iso(new_modified_at),
                    guide_id,
                    uuid,
                ),
            )
        return POI(
            uuid=uuid,
            name=name,
            description=description,
            latitude=latitude,
            longitude=longitude,
            visited=bool(current["visited"]),
            link=link,
            category=category,
            timestamp=timestamp,
            modified_at=new_modified_at,
        )

    def set_visited(self, guide_id: int, uuid: str, visited: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE points SET visited = ?, modified_at = ? "
                "WHERE guide_id = ? AND uuid = ?",
                (int(visited), datetime.utcnow().isoformat(), guide_id, uuid),
            )

    def delete_point(self, guide_id: int, uuid: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM points WHERE guide_id = ? AND uuid = ?",
                (guide_id, uuid),
            )
