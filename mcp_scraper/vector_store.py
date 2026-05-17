"""
vector_store.py — ChromaDB integration for semantic retrieval.

Uses sentence-transformers locally (no API key) so the whole pipeline
runs offline alongside LM Studio.

Responsibilities:
  - Embed and upsert Chunk objects
  - Semantic search with optional fandom/entity/type filters
  - Delete all chunks for a given entity (used on re-scrape)
"""

import logging
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from .config import CHROMA_DIR, CHROMA_COLLECTION, EMBEDDING_MODEL
from .models import Chunk

logger = logging.getLogger(__name__)

# ── Singleton client & collection ──────────────────────────────────────────

_client: Optional[chromadb.PersistentClient] = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    logger.info(f"Initialising ChromaDB at {CHROMA_DIR}")
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        device="cpu",          # change to "cuda" if you have a GPU
    )

    _collection = _client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},   # cosine similarity for text
    )
    logger.info(
        f"ChromaDB collection '{CHROMA_COLLECTION}' ready  "
        f"({_collection.count()} docs already stored)"
    )
    return _collection


# ── Write ──────────────────────────────────────────────────────────────────

def upsert_chunks(chunks: list[Chunk]) -> None:
    """
    Embed and store a list of Chunk objects.
    Uses upsert so re-scraping safely overwrites old vectors.
    """
    if not chunks:
        return

    collection = _get_collection()
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[c.to_metadata() for c in chunks],
    )
    logger.info(f"Upserted {len(chunks)} chunks into ChromaDB")


def delete_entity_chunks(entity_name: str, fandom: str) -> None:
    """
    Remove all stored chunks for a specific entity.
    Called before re-ingesting a freshly scraped entity.
    """
    collection = _get_collection()
    collection.delete(
        where={"$and": [
            {"entity_name": {"$eq": entity_name}},
            {"fandom": {"$eq": fandom}},
        ]}
    )
    logger.debug(f"Deleted chunks for {entity_name} / {fandom}")


# ── Read ───────────────────────────────────────────────────────────────────

def search(
    query: str,
    n_results: int = 5,
    fandom: Optional[str] = None,
    entity_name: Optional[str] = None,
    chunk_type: Optional[str] = None,
) -> list[dict]:
    """
    Semantic search over stored chunks.

    Returns a list of dicts, each with:
      - text       : the matched chunk text
      - score      : cosine distance (lower = more similar; 0 = identical)
      - entity_name, fandom, chunk_type, source_url : from metadata
    """
    collection = _get_collection()

    # Build optional metadata filter
    filters = _build_filter(fandom=fandom, entity_name=entity_name, chunk_type=chunk_type)

    kwargs: dict = {"query_texts": [query], "n_results": n_results, "include": ["documents", "metadatas", "distances"]}
    if filters:
        kwargs["where"] = filters

    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.warning(f"ChromaDB query failed: {e}")
        return []

    hits = []
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, distances):
        hits.append({
            "text": doc,
            "score": round(dist, 4),
            **meta,
        })
    return hits


def count() -> int:
    """Return total number of stored chunks."""
    return _get_collection().count()


# ── Filter builder ─────────────────────────────────────────────────────────

def _build_filter(
    fandom: Optional[str],
    entity_name: Optional[str],
    chunk_type: Optional[str],
) -> Optional[dict]:
    """
    Build a ChromaDB `where` clause from the supplied filters.
    Returns None if no filters are active.
    """
    conditions = []
    if fandom:
        conditions.append({"fandom": {"$eq": fandom}})
    if entity_name:
        conditions.append({"entity_name": {"$eq": entity_name}})
    if chunk_type:
        conditions.append({"chunk_type": {"$eq": chunk_type}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
