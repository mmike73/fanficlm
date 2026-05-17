"""
models.py — dataclasses shared across all modules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Entity:
    """
    A character, place, concept, or fandom scraped from the web.
    Maps 1-to-1 with a row in the SQL `entities` table.
    """
    name: str
    fandom: str                          # e.g. "MCU", "avatar", "harrypotter"
    entity_type: str = "character"       # character | place | concept | event
    canonical_name: Optional[str] = None # normalised lookup key
    description: Optional[str] = None   # short blurb / lead paragraph
    source_url: Optional[str] = None
    source_type: Optional[str] = None   # "wikipedia" | "fandom" | "manual"
    last_scraped_at: Optional[datetime] = None
    id: Optional[int] = None

    def __post_init__(self):
        if self.canonical_name is None:
            # e.g. "Tony Stark" + "MCU" → "tony stark::mcu"
            self.canonical_name = f"{self.name.lower().strip()}::{self.fandom.lower().strip()}"


@dataclass
class EntityAttribute:
    """
    A single structured attribute for an entity (personality, backstory, etc.).
    Maps to a row in the SQL `entity_attributes` table.
    """
    entity_id: int
    attribute_key: str    # e.g. "personality", "backstory", "powers", "relationships"
    attribute_value: str
    confidence: float = 1.0
    id: Optional[int] = None


@dataclass
class Chunk:
    """
    A text chunk ready to be embedded and stored in ChromaDB.
    The `chunk_id` is used as the ChromaDB document ID (must be unique).
    """
    chunk_id: str          # e.g. "tony_stark::mcu::personality::0"
    text: str
    entity_name: str
    fandom: str
    chunk_type: str        # attribute_key this chunk came from
    source_url: str = ""
    entity_type: str = "character"

    def to_metadata(self) -> dict:
        """Returns the metadata dict stored alongside the vector in ChromaDB."""
        return {
            "entity_name": self.entity_name,
            "fandom": self.fandom,
            "chunk_type": self.chunk_type,
            "source_url": self.source_url,
            "entity_type": self.entity_type,
        }


@dataclass
class ScrapeResult:
    """
    What the scraper returns after fetching a page.
    Contains both structured attributes and raw text for chunking.
    """
    entity: Entity
    attributes: dict = field(default_factory=dict)
    # attributes keys: personality, backstory, appearance, powers,
    #                  relationships, history, trivia, full_text
    success: bool = True
    error: Optional[str] = None
