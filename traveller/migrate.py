"""One-shot importer: read a legacy guide.zip into the SQLite database.

Called from app startup if guide.zip exists and hasn't been imported yet.
After a successful import, the zip is renamed to guide.zip.imported so the
next boot is a no-op.
"""

from __future__ import annotations

from csv import DictReader
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

from traveller.models import POI, Category
from traveller.storage import Storage


def _bool(s: str) -> bool:
    return s.strip().lower() == "true"


def _float_or_none(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    # Treat the legacy (0, 0) sentinel as "not set" only if both are zero;
    # caller stitches the pair together.
    return v


def import_zip(storage: Storage, zip_path: Path) -> int:
    """Import a legacy guide.zip into a new guide. Returns the new guide id."""
    with ZipFile(zip_path, "r") as zf:
        with zf.open("metadata.csv") as f:
            meta = next(DictReader(TextIOWrapper(f, "utf-8")))
        with zf.open("categories.csv") as f:
            cat_rows = list(DictReader(TextIOWrapper(f, "utf-8")))
        with zf.open("POIs.csv") as f:
            poi_rows = list(DictReader(TextIOWrapper(f, "utf-8")))

    guide = storage.create_guide(
        name=meta.get("name") or "Imported guide",
        description=meta.get("description") or "",
        link=meta.get("link") or "",
    )
    storage.set_categories(
        guide.id,
        [
            Category(
                name=r["name"],
                color=r.get("color", "") or "",
                icon=r.get("icon", "") or "",
            )
            for r in cat_rows
        ],
    )

    for r in poi_rows:
        lat = _float_or_none(r.get("latitude", ""))
        lon = _float_or_none(r.get("longitude", ""))
        # Drop the (0, 0) sentinel that the legacy format used for "no coords".
        if lat == 0 and lon == 0:
            lat = lon = None
        link = r.get("link") or None
        # The legacy format wrote Python's str(None) for empty links.
        if link in ("None", ""):
            link = None
        ts_str = r.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else None
        except ValueError:
            ts = None
        storage.create_point(
            guide.id,
            POI(
                uuid=r["uuid"],
                name=r.get("name", "") or "",
                description=r.get("description", "") or "",
                latitude=lat,
                longitude=lon,
                visited=_bool(r.get("visited", "")),
                link=link,
                category=r.get("category", "") or "",
                timestamp=ts,
            ),
        )

    return guide.id


def maybe_import(storage: Storage, zip_path: Path) -> int | None:
    """If a legacy zip exists and has not been imported, import it and rename
    it to guide.zip.imported. Returns the new guide id or None."""
    if not zip_path.exists():
        return None
    gid = import_zip(storage, zip_path)
    zip_path.rename(zip_path.with_suffix(zip_path.suffix + ".imported"))
    return gid
