from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Entity:
    name: str
    fandom: str
    entity_type: str = "character"
    canonical_name: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    last_scraped_at: Optional[datetime] = None
    id: Optional[int] = None

    def __post_init__(self):
        if self.canonical_name is None:
            # e.g. "Tony Stark" + "MCU" → "tony stark::mcu"
            self.canonical_name = f"{self.name.lower().strip()}::{self.fandom.lower().strip()}"


@dataclass
class EntityAttribute:
    entity_id: int
    attribute_key: str
    attribute_value: str
    confidence: float = 1.0
    id: Optional[int] = None


@dataclass
class Chunk:
    chunk_id: str
    text: str
    entity_name: str
    fandom: str
    chunk_type: str
    source_url: str = ""
    entity_type: str = "character"

    def to_metadata(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "fandom": self.fandom,
            "chunk_type": self.chunk_type,
            "source_url": self.source_url,
            "entity_type": self.entity_type,
        }


@dataclass
class ScrapeResult:
    entity: Entity
    attributes: dict = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
