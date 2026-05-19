import logging
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from .config import CHROMA_DIR, CHROMA_COLLECTION, EMBEDDING_MODEL
from .models import Chunk

logger = logging.getLogger(__name__)

_client: Optional[chromadb.PersistentClient] = None
_collection = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        logger.info(f"Initialising ChromaDB client at {CHROMA_DIR}")
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _get_collection():
    # Split from _get_client so list_entities / count can run without loading
    # sentence-transformers (avoids the 8-second cold-start on non-embedding calls).
    global _collection
    if _collection is not None:
        return _collection

    embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        device="cpu",
    )
    _collection = _get_client().get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(f"ChromaDB collection '{CHROMA_COLLECTION}' ready ({_collection.count()} docs)")
    return _collection


_UPSERT_BATCH = 50


def upsert_chunks(chunks: list[Chunk]) -> None:
    if not chunks:
        return
    collection = _get_collection()
    for start in range(0, len(chunks), _UPSERT_BATCH):
        batch = chunks[start:start + _UPSERT_BATCH]
        collection.upsert(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[c.to_metadata() for c in batch],
        )
    logger.info(f"Upserted {len(chunks)} chunks into ChromaDB")


def has_entity_chunks(entity_name: str, fandom: str) -> bool:
    try:
        col = _get_collection()
        result = col.get(
            where={"$and": [
                {"entity_name": {"$eq": entity_name}},
                {"fandom":      {"$eq": fandom}},
            ]},
            limit=1,
            include=["metadatas"],
        )
        return len(result["ids"]) > 0
    except Exception:
        return False


def delete_entity_chunks(entity_name: str, fandom: str) -> None:
    try:
        collection = _get_collection()
        collection.delete(
            where={"$and": [
                {"entity_name": {"$eq": entity_name}},
                {"fandom":      {"$eq": fandom}},
            ]}
        )
    except Exception as e:
        # Benign when the entity has never been stored — don't block the upsert.
        logger.debug(f"delete_entity_chunks no-op for '{entity_name}' ({fandom}): {e}")


def search(
    query: str,
    n_results: int = 5,
    fandom: Optional[str] = None,
    entity_name: Optional[str] = None,
    chunk_type: Optional[str] = None,
) -> list[dict]:
    collection = _get_collection()
    filters = _build_filter(fandom=fandom, entity_name=entity_name, chunk_type=chunk_type)

    kwargs: dict = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if filters:
        kwargs["where"] = filters

    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.warning(f"ChromaDB query failed: {e}")
        return []

    hits = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        hits.append({"text": doc, "score": round(dist, 4), **meta})
    return hits


def count() -> int:
    try:
        col = _get_client().get_collection(name=CHROMA_COLLECTION)
        return col.count()
    except Exception:
        return 0


def _build_filter(
    fandom: Optional[str],
    entity_name: Optional[str],
    chunk_type: Optional[str],
) -> Optional[dict]:
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
