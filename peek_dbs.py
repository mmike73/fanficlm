"""
peek_dbs.py — terminal snapshot of knowledge.db (SQLite) and ChromaDB.

Run with any Python — auto-bootstraps from the project .venv:
    python peek_dbs.py
"""

import sys
import sqlite3
import textwrap
from pathlib import Path

# ── Bootstrap: inject the project .venv so chromadb is always findable ────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_VENV_DIR   = _SCRIPT_DIR / ".venv"

def _inject_venv(venv: Path):
    """Add venv site-packages to sys.path (idempotent)."""
    import platform
    tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        venv / "lib" / tag / "site-packages",          # Unix/macOS
        venv / "Lib" / "site-packages",                 # Windows
    ]
    for sp in candidates:
        if sp.is_dir() and str(sp) not in sys.path:
            sys.path.insert(0, str(sp))
            return True
    return False

if _VENV_DIR.is_dir():
    _inject_venv(_VENV_DIR)

# ── Paths (mirror config.py) ───────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
DATA_DIR   = BASE_DIR / "scraper_data"
DB_PATH    = DATA_DIR / "knowledge.db"
CHROMA_DIR = DATA_DIR / "chroma_store"

CHROMA_COLLECTION = "entities"
EMBEDDING_MODEL   = "all-MiniLM-L6-v2"

# ── Formatting helpers ─────────────────────────────────────────────────────
W = 80

def hr(char="─"):
    print(char * W)

def header(title: str, char="═"):
    print()
    print(char * W)
    print(f"  {title}")
    print(char * W)

def subheader(title: str):
    print(f"\n{'─' * 4}  {title}")

def trunc(s: str, n: int = 80) -> str:
    if s is None:
        return "—"
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n - 3] + "..."


# ══════════════════════════════════════════════════════════════════════════════
#  1. SQLite — knowledge.db
# ══════════════════════════════════════════════════════════════════════════════

def peek_sqlite():
    header("SQLite  ·  knowledge.db")

    if not DB_PATH.exists():
        print(f"  [!] Not found at {DB_PATH}")
        return

    print(f"  Path : {DB_PATH}")
    print(f"  Size : {DB_PATH.stat().st_size / 1024:.1f} KB")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ── entities table ─────────────────────────────────────────────────────
    entities = conn.execute("SELECT * FROM entities ORDER BY name").fetchall()
    attr_count_row = conn.execute("SELECT COUNT(*) AS n FROM entity_attributes").fetchone()
    total_attrs = attr_count_row["n"]

    subheader(f"entities  ({len(entities)} rows)")
    if not entities:
        print("    (empty)")
    else:
        col_w = [4, 22, 14, 11, 12, 11]
        fmt   = "{:<{}} {:<{}} {:<{}} {:<{}} {:<{}} {:<{}}"
        heads = ("id", "name", "fandom", "type", "source", "scraped_at")
        print("    " + fmt.format(*[v for pair in zip(heads, col_w) for v in pair]))
        print("    " + "  ".join("─" * w for w in col_w))
        for e in entities:
            scraped = (e["last_scraped_at"] or "")[:10]
            print("    " + fmt.format(
                str(e["id"]),      col_w[0],
                trunc(e["name"], col_w[1]),  col_w[1],
                trunc(e["fandom"], col_w[2]), col_w[2],
                e["entity_type"][:col_w[3]], col_w[3],
                (e["source_type"] or "")[:col_w[4]], col_w[4],
                scraped[:col_w[5]], col_w[5],
            ))

    # ── entity_attributes table ────────────────────────────────────────────
    subheader(f"entity_attributes  ({total_attrs} rows total)")
    for e in entities:
        attrs = conn.execute(
            "SELECT attribute_key, attribute_value FROM entity_attributes "
            "WHERE entity_id = ? ORDER BY attribute_key",
            (e["id"],),
        ).fetchall()
        if not attrs:
            continue
        print(f"\n    [{e['name']}  /  {e['fandom']}]  (id={e['id']})")
        for a in attrs:
            val = trunc(a["attribute_value"], 60)
            print(f"      {a['attribute_key']:<20}  {val}")

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  2. ChromaDB — chroma_store
# ══════════════════════════════════════════════════════════════════════════════

def peek_chroma():
    header("ChromaDB  ·  chroma_store")

    if not CHROMA_DIR.exists():
        print(f"  [!] Not found at {CHROMA_DIR}")
        return

    # Size of the whole store directory
    total_bytes = sum(f.stat().st_size for f in CHROMA_DIR.rglob("*") if f.is_file())
    print(f"  Path : {CHROMA_DIR}")
    print(f"  Size : {total_bytes / 1024:.1f} KB")

    try:
        import os, warnings
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        warnings.filterwarnings("ignore", category=UserWarning)
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        print("  [!] chromadb not installed — run: pip install chromadb sentence-transformers")
        return

    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    except Exception as exc:
        print(f"  [!] Could not open ChromaDB: {exc}")
        return

    # ── collections overview ───────────────────────────────────────────────
    collections = client.list_collections()
    subheader(f"Collections  ({len(collections)} found)")
    for col_meta in collections:
        try:
            col = client.get_collection(col_meta.name)
            print(f"    • {col.name:<30}  {col.count()} documents")
        except Exception as exc:
            print(f"    • {col_meta.name}  [error: {exc}]")

    # ── main 'entities' collection detail ─────────────────────────────────
    try:
        emb_fn = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL, device="cpu"
        )
        col = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            embedding_function=emb_fn,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as exc:
        print(f"\n  [!] Could not load '{CHROMA_COLLECTION}' collection: {exc}")
        return

    total = col.count()
    subheader(f"Collection: '{CHROMA_COLLECTION}'  —  {total} chunks total")

    if total == 0:
        print("    (empty)")
        return

    # Fetch up to 200 records (no query, just get)
    peek_n = min(total, 200)
    result = col.get(limit=peek_n, include=["documents", "metadatas"])

    ids       = result["ids"]
    docs      = result["documents"]
    metas     = result["metadatas"]

    # Aggregate by (entity_name, fandom)
    groups: dict[tuple, list] = {}
    for doc_id, doc, meta in zip(ids, docs, metas):
        key = (meta.get("entity_name", "?"), meta.get("fandom", "?"))
        groups.setdefault(key, []).append((doc_id, doc, meta))

    subheader(f"Breakdown by entity  ({len(groups)} entities, showing ≤5 chunks each)")
    for (ename, fandom), chunks in sorted(groups.items()):
        print(f"\n    [{ename}  /  {fandom}]  —  {len(chunks)} chunk(s)")
        # Show chunk_type distribution
        types: dict[str, int] = {}
        for _, _, m in chunks:
            t = m.get("chunk_type", "?")
            types[t] = types.get(t, 0) + 1
        type_str = "  ".join(f"{t}×{n}" for t, n in sorted(types.items()))
        print(f"      types: {type_str}")
        # Print first 5 chunks
        for doc_id, doc, meta in chunks[:5]:
            preview = trunc(doc, 70)
            ctype   = meta.get("chunk_type", "?")
            print(f"      [{ctype}]  {preview}")
        if len(chunks) > 5:
            print(f"      … and {len(chunks) - 5} more chunk(s)")


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    peek_sqlite()
    peek_chroma()
    print()
    hr("═")
    print("  Done.")
    hr("═")
