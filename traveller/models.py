from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class Guide:
    id: int
    name: str
    description: str = ""
    link: str = ""
    sort_order: int = 0


@dataclass
class Category:
    name: str
    color: str = ""
    icon: str = ""


@dataclass
class POI:
    uuid: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    latitude: float | None = None
    longitude: float | None = None
    visited: bool = False
    link: str | None = None
    category: str = ""
    timestamp: datetime | None = None
    modified_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_coords(self) -> bool:
        return self.latitude is not None and self.longitude is not None
