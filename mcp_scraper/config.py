import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR.parent / "scraper_data"
DB_PATH  = DATA_DIR / "knowledge.db"
CHROMA_DIR = DATA_DIR / "chroma_store"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# ~90 MB, downloads once then cached by sentence-transformers
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

CHROMA_COLLECTION = "entities"

CACHE_TTL_DAYS = 30
REQUEST_DELAY_SECONDS = 1.5
HTTP_TIMEOUT_SECONDS = 15
MAX_RAW_TEXT_CHARS = 50_000

# "fandom" tried first — better for fictional characters; "wikipedia" as fallback
SOURCE_PRIORITY = ["fandom", "wikipedia"]

FANDOM_SEARCH_URL = "https://{fandom}.fandom.com/wiki/{character}"
FANDOM_SEARCH_API = "https://{fandom}.fandom.com/api/v1/Search/List?query={query}&limit=5"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_SEARCH_URL  = "https://en.wikipedia.org/w/api.php"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
