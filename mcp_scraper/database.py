import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

from .config import DB_PATH, CACHE_TTL_DAYS
from .models import Entity, EntityAttribute

logger = logging.getLogger(__name__)

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


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript(_SCHEMA)
    logger.info(f"Database initialised at {DB_PATH}")


def get_entity(name: str, fandom: str) -> Optional[Entity]:
    canonical = f"{name.lower().strip()}::{fandom.lower().strip()}"
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE canonical_name = ?", (canonical,)
        ).fetchone()
    return _row_to_entity(row) if row else None


def is_cache_fresh(entity: Entity) -> bool:
    if entity.last_scraped_at is None:
        return False
    return entity.last_scraped_at > datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)


def upsert_entity(entity: Entity) -> int:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
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
        row = conn.execute(
            "SELECT id FROM entities WHERE canonical_name = ?",
            (entity.canonical_name,),
        ).fetchone()
    return row["id"]


def list_entities(fandom: Optional[str] = None, entity_type: Optional[str] = None) -> list[Entity]:
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


def upsert_attributes(entity_id: int, attributes: dict[str, str]) -> None:
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


def get_attributes(entity_id: int) -> dict[str, str]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT attribute_key, attribute_value FROM entity_attributes WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
    return {r["attribute_key"]: r["attribute_value"] for r in rows}


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
