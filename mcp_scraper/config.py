"""
config.py — centralised settings for the MCP scraper.
All paths and tunables live here so nothing is hardcoded elsewhere.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
# Base directory: the folder this file lives in
BASE_DIR = Path(__file__).parent.resolve()

# Persistent storage sits next to the package, not inside it
DATA_DIR = BASE_DIR.parent / "scraper_data"
DB_PATH  = DATA_DIR / "knowledge.db"        # SQLite file
CHROMA_DIR = DATA_DIR / "chroma_store"       # ChromaDB persistence

# Create storage directories on import
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# ── Embedding model ────────────────────────────────────────────────────────
# Small, fast, fully local — no API key required.
# Downloads ~90 MB on first run, then cached by sentence-transformers.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── ChromaDB ───────────────────────────────────────────────────────────────
CHROMA_COLLECTION = "entities"

# ── Scraping behaviour ─────────────────────────────────────────────────────
# How many days before a cached entity is considered stale and re-scraped
CACHE_TTL_DAYS = 30

# Per-domain request delay in seconds (be polite to wikis)
REQUEST_DELAY_SECONDS = 1.5

# HTTP request timeout
HTTP_TIMEOUT_SECONDS = 15

# Maximum characters of raw text to store per scraped page
MAX_RAW_TEXT_CHARS = 50_000

# ── Source priority ────────────────────────────────────────────────────────
# Sources tried in order; first successful hit wins.
# "wikipedia"  → Wikipedia REST API (clean, structured, good for real-world figures)
# "fandom"     → Fandom/Wikia wikis (best for fictional characters)
SOURCE_PRIORITY = ["fandom", "wikipedia"]

# Fandom wiki subdomain template — {fandom} is replaced at runtime
FANDOM_SEARCH_URL = "https://{fandom}.fandom.com/wiki/{character}"
FANDOM_SEARCH_API = "https://{fandom}.fandom.com/api/v1/Search/List?query={query}&limit=5"

# Wikipedia summary API
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_SEARCH_URL  = "https://en.wikipedia.org/w/api.php"

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
