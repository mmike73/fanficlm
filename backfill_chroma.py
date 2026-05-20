"""
One-shot script: finds every SQLite entity with no ChromaDB chunks and backfills it.
Run from the project root:  .venv/bin/python backfill_chroma.py

Do NOT run with an arbitrary system python3 — sentence-transformers requires the
same venv the MCP server uses (.venv).  Python 3.14+ may crash PyTorch.
"""
import os, sys

# Warn if we are not inside the project .venv
_venv = os.environ.get("VIRTUAL_ENV", "")
if not _venv or not _venv.endswith(".venv"):
    print(
        f"WARNING: active venv is '{_venv or 'none'}', expected the project .venv.\n"
        f"         Run with:  .venv/bin/python backfill_chroma.py\n"
        f"         Continuing anyway — if the process is killed, that is why.\n",
        flush=True,
    )
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from mcp_scraper import database, vector_store, scraper

database.init_db()

entities = database.list_entities()
print(f"SQLite entities: {len(entities)}")

missing = [e for e in entities if not vector_store.has_entity_chunks(e.name, e.fandom)]
print(f"Missing from ChromaDB: {len(missing)}")

if not missing:
    print("Nothing to backfill.")
    sys.exit(0)

for e in missing:
    attrs = database.get_attributes(e.id)
    total_chars = sum(len(v) for v in attrs.values())
    chunks = scraper.make_chunks(e, e.id, attrs)
    print(f"  {e.name} ({e.fandom})  —  {len(attrs)} attrs, {total_chars:,} chars → {len(chunks)} chunks", flush=True)
    if not chunks:
        print(f"    [skip] no chunks generated")
        continue
    vector_store.upsert_chunks(chunks)
    print(f"    stored.", flush=True)

print("Backfill complete.")
