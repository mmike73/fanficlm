"""
Unified RAG service combining:
  - Tier 1: scraper ChromaDB (deep, wiki-scraped character data)
  - Tier 2: CharacterCodex turbovec index (broad, ~16K characters)

At query time, retrieves from both and applies scraper-priority merge:
if a character exists in Tier 1, its result replaces the Tier 2 result.
"""
import json
import logging
import numpy as np
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from turbovec import IdMapIndex
from sentence_transformers import SentenceTransformer

from app.core.config import app_settings

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_SCRAPER_CHROMA_DIR = Path(__file__).resolve().parents[3] / "scraper_data" / "chroma_store"

try:
    _CODEX_INDEX_PATH = Path(app_settings.VECTOR_STORE_PATH) / "charactercodex.tvim"
    _CODEX_DOCS_PATH  = Path(app_settings.VECTOR_STORE_PATH) / "charactercodex_docs.json"
    print("Paths OK:", _CODEX_INDEX_PATH)
except Exception as e:
    import traceback
    traceback.print_exc()
    print("PATH ERROR:", e)

# ── Singletons (lazy-loaded on first call) ────────────────────────────────────
_model: Optional[SentenceTransformer] = None
_scraper_collection = None
_codex_index: Optional[IdMapIndex] = None
_codex_docs: Optional[dict] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {app_settings.EMBEDDING_MODEL}")
        _model = SentenceTransformer(app_settings.EMBEDDING_MODEL)
    return _model


def _get_scraper_collection():
    global _scraper_collection
    if _scraper_collection is None:
        if not _SCRAPER_CHROMA_DIR.exists():
            logger.warning(f"Scraper chroma store not found at {_SCRAPER_CHROMA_DIR}")
            return None
        embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=app_settings.EMBEDDING_MODEL,
            device="cpu",
        )
        client = chromadb.PersistentClient(path=str(_SCRAPER_CHROMA_DIR))
        try:
            _scraper_collection = client.get_collection(
                name="entities",
                embedding_function=embedding_fn,
            )
            logger.info(f"Scraper collection ready ({_scraper_collection.count()} docs)")
        except Exception as e:
            logger.warning(f"Could not load scraper collection: {e}")
            return None
    return _scraper_collection


def _get_codex_index():
    global _codex_index, _codex_docs
    if _codex_index is None:
        if not _CODEX_INDEX_PATH.exists():
            logger.warning(f"CharacterCodex index not found at {_CODEX_INDEX_PATH}. Run scripts/ingest_charactercodex.py first.")
            return None, None
        logger.info("Loading CharacterCodex turbovec index...")
        _codex_index = IdMapIndex.load(str(_CODEX_INDEX_PATH))
        with open(_CODEX_DOCS_PATH, encoding="utf-8") as f:
            _codex_docs = json.load(f)
        logger.info(f"CharacterCodex index ready ({len(_codex_index)} vectors)")
    return _codex_index, _codex_docs


def retrieve(query: str, n_results: int = 3) -> list[dict]:
    """
    Query both tiers and return a priority-merged list of results.
    Scraper results always beat CharacterCodex results for the same character.
    Returns list of dicts with keys: document, character_name, media_source, source, score.
    """
    logger.info(f"RAG retrieve: query='{query[:80]}' n_results={n_results}")
    model = _get_model()
    query_embedding = model.encode(query, normalize_embeddings=True)

    tier1_results = _query_scraper(query_embedding, n_results)
    tier2_results = _query_codex(query_embedding, n_results)

    logger.info(f"RAG tier1 (scraper): {len(tier1_results)} hits, tier2 (codex): {len(tier2_results)} hits")

    merged = _priority_merge(tier1_results, tier2_results, n_results)
    for r in merged:
        logger.info(f"  [{r['source']}] {r['character_name']} ({r['media_source']}) score={r['score']}")
    return merged


def _query_scraper(query_embedding: np.ndarray, n_results: int) -> list[dict]:
    collection = _get_scraper_collection()
    if collection is None or collection.count() == 0:
        return []
    try:
        raw = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(n_results * 2, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        results = []
        for doc, meta, dist in zip(
            raw["documents"][0], raw["metadatas"][0], raw["distances"][0]
        ):
            results.append({
                "document":       doc,
                "character_name": meta.get("entity_name", ""),
                "media_source":   meta.get("fandom", ""),
                "chunk_type":     meta.get("chunk_type", ""),
                "source":         "scraper",
                "score":          round(1 - dist, 4),
            })
        return results
    except Exception as e:
        logger.warning(f"Scraper query failed: {e}")
        return []


def _query_codex(query_embedding: np.ndarray, n_results: int) -> list[dict]:
    index, docs = _get_codex_index()
    if index is None:
        return []
    try:
        query_arr = query_embedding.astype(np.float32).reshape(1, -1)
        scores, ids = index.search(query_arr, k=n_results * 2)
        results = []
        for score, doc_id in zip(scores[0], ids[0]):
            entry = docs.get(str(doc_id))
            if entry:
                results.append({**entry, "score": round(float(score), 4)})
        return results
    except Exception as e:
        logger.warning(f"CharacterCodex query failed: {e}")
        return []


def _priority_merge(tier1: list[dict], tier2: list[dict], n_results: int) -> list[dict]:
    """
    Merge tier1 (scraper) and tier2 (CharacterCodex).
    For any character name present in tier1, drop the tier2 entry.
    Cap the final result at n_results.
    """
    tier1_names = {r["character_name"].lower() for r in tier1}

    merged = list(tier1)
    for r in tier2:
        if r["character_name"].lower() not in tier1_names:
            merged.append(r)

    # Sort by score descending, cap to n_results
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged[:n_results]


def build_context_block(results: list[dict]) -> str:
    """
    Format retrieved results into a context string for prompt injection.
    Groups scraper results by character and shows their structured attributes.
    """
    if not results:
        return ""

    lines = ["## Retrieved Character Knowledge\n"]
    for r in results:
        source_label = "wiki (scraped)" if r["source"] == "scraper" else "CharacterCodex"
        chunk_info = f" [{r.get('chunk_type', '')}]" if r.get("chunk_type") else ""
        lines.append(
            f"### {r['character_name']} ({r['media_source']}) "
            f"— {source_label}{chunk_info}\n{r['document']}\n"
        )

    return "\n".join(lines)