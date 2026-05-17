"""
database.py — SQLite layer for entity cache and structured attributes.

Responsibilities:
  - Store/retrieve Entity records (cache check, TTL, deduplication)
  - Store/retrieve EntityAttribute records (structured metadata)
  - Track scrape provenance (source URL, source type, timestamp)
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

from .config import DB_PATH, CACHE_TTL_DAYS
from .models import Entity, EntityAttribute

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    fandom          TEXT NOT NULL,
    entity_type     TEXT NOT NULL DEFAULT 'character',
    canonical_name  TEXT NOT NULL UNIQUE,
    description     TEXT,
    source_url      TEXT,
    source_type     TEXT,
    last_scraped_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entity_attributes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    attribute_key   TEXT NOT NULL,
    attribute_value TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 1.0,
    UNIQUE(entity_id, attribute_key)
);

CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_attributes_entity  ON entity_attributes(entity_id);
"""


# ── Connection helper ──────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # safer for concurrent reads
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _get_conn() as conn:
        conn.executescript(_SCHEMA)
    logger.info(f"Database initialised at {DB_PATH}")


# ── Entity CRUD ────────────────────────────────────────────────────────────

def get_entity(name: str, fandom: str) -> Optional[Entity]:
    """
    Look up an entity by (name, fandom). Returns None if not found.
    Uses the canonical_name index for fast lookup.
    """
    canonical = f"{name.lower().strip()}::{fandom.lower().strip()}"
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE canonical_name = ?", (canonical,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_entity(row)


def is_cache_fresh(entity: Entity) -> bool:
    """
    Returns True if the entity was scraped within CACHE_TTL_DAYS.
    Entities with no last_scraped_at are always considered stale.
    """
    if entity.last_scraped_at is None:
        return False
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
    return entity.last_scraped_at > cutoff


def upsert_entity(entity: Entity) -> int:
    """
    Insert or update an entity. Returns the entity's database ID.
    On conflict (same canonical_name) the row is updated in place.
    """
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO entities
                (name, fandom, entity_type, canonical_name, description,
                 source_url, source_type, last_scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_name) DO UPDATE SET
                description     = excluded.description,
                source_url      = excluded.source_url,
                source_type     = excluded.source_type,
                last_scraped_at = excluded.last_scraped_at
            """,
            (
                entity.name, entity.fandom, entity.entity_type,
                entity.canonical_name, entity.description,
                entity.source_url, entity.source_type, now,
            ),
        )
        # Retrieve the actual rowid (works for both insert and update)
        row = conn.execute(
            "SELECT id FROM entities WHERE canonical_name = ?",
            (entity.canonical_name,),
        ).fetchone()
    entity_id = row["id"]
    logger.debug(f"Upserted entity id={entity_id}  canonical={entity.canonical_name}")
    return entity_id


def list_entities(fandom: Optional[str] = None, entity_type: Optional[str] = None) -> list[Entity]:
    """Return all stored entities, optionally filtered by fandom and/or type."""
    query = "SELECT * FROM entities WHERE 1=1"
    params: list = []
    if fandom:
        query += " AND LOWER(fandom) = LOWER(?)"
        params.append(fandom)
    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY name"
    with _get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_entity(r) for r in rows]


# ── Attribute CRUD ─────────────────────────────────────────────────────────

def upsert_attributes(entity_id: int, attributes: dict[str, str]) -> None:
    """
    Store structured attributes for an entity (personality, backstory, etc.).
    Each (entity_id, attribute_key) pair is unique — conflicts replace the value.
    """
    with _get_conn() as conn:
        for key, value in attributes.items():
            if not value or not value.strip():
                continue
            conn.execute(
                """
                INSERT INTO entity_attributes (entity_id, attribute_key, attribute_value)
                VALUES (?, ?, ?)
                ON CONFLICT(entity_id, attribute_key) DO UPDATE SET
                    attribute_value = excluded.attribute_value
                """,
                (entity_id, key, value.strip()),
            )
    logger.debug(f"Upserted {len(attributes)} attributes for entity_id={entity_id}")


def get_attributes(entity_id: int) -> dict[str, str]:
    """Return all attributes for an entity as a plain dict."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT attribute_key, attribute_value FROM entity_attributes WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
    return {r["attribute_key"]: r["attribute_value"] for r in rows}


# ── Internal helpers ───────────────────────────────────────────────────────

def _row_to_entity(row: sqlite3.Row) -> Entity:
    scraped_at = None
    if row["last_scraped_at"]:
        try:
            scraped_at = datetime.fromisoformat(row["last_scraped_at"])
        except ValueError:
            pass
    return Entity(
        id=row["id"],
        name=row["name"],
        fandom=row["fandom"],
        entity_type=row["entity_type"],
        canonical_name=row["canonical_name"],
        description=row["description"],
        source_url=row["source_url"],
        source_type=row["source_type"],
        last_scraped_at=scraped_at,
    )
