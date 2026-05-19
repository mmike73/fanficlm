"""
One-time ingestion script for NousResearch/CharacterCodex into a turbovec index.
"""
import json
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets import load_dataset
from sentence_transformers import SentenceTransformer
from turbovec import IdMapIndex
from app.core.config import app_settings

STORE_DIR = Path(app_settings.VECTOR_STORE_PATH)
STORE_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH   = STORE_DIR / "charactercodex.tvim"
DOCSTORE_PATH = STORE_DIR / "charactercodex_docs.json"
BATCH_SIZE   = 512
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def build_text(record: dict) -> str:
    return (
        f"Character: {record['character_name']} "
        f"from {record['media_source']} "
        f"({record['media_type']} / {record['genre']}). "
        f"Description: {record['description']} "
        f"Scenario: {record['scenario']}"
    )


def main():
    print("Loading CharacterCodex from HuggingFace...")
    ds = load_dataset("NousResearch/CharacterCodex", split="train")
    records = list(ds)
    print(f"  {len(records)} records loaded.")

    print(f"Loading embedding model: {app_settings.EMBEDDING_MODEL}")
    model = SentenceTransformer(app_settings.EMBEDDING_MODEL)

    print("Building turbovec index...")
    index = IdMapIndex(dim=EMBEDDING_DIM, bit_width=4)
    doc_store = {}

    for batch_start in range(0, len(records), BATCH_SIZE):
        batch = records[batch_start : batch_start + BATCH_SIZE]
        texts = [build_text(r) for r in batch]

        embeddings = model.encode(texts, show_progress_bar=False, batch_size=64)
        embeddings = np.array(embeddings, dtype=np.float32)

        ids = np.arange(batch_start, batch_start + len(batch), dtype=np.uint64)
        index.add_with_ids(embeddings, ids)

        for j, (r, text) in enumerate(zip(batch, texts)):
            doc_store[str(batch_start + j)] = {
                "document": text,
                "character_name": r["character_name"],
                "media_source":   r["media_source"],
                "media_type":     r["media_type"],
                "genre":          r["genre"],
                "source":         "charactercodex",
            }

        print(f"  Processed {min(batch_start + BATCH_SIZE, len(records))}/{len(records)}")

    print(f"Saving index to {INDEX_PATH}...")
    index.write(str(INDEX_PATH))

    print(f"Saving doc store to {DOCSTORE_PATH}...")
    with open(DOCSTORE_PATH, "w", encoding="utf-8") as f:
        json.dump(doc_store, f, ensure_ascii=False)

    print(f"Done. {len(doc_store)} records ingested.")


if __name__ == "__main__":
    main()