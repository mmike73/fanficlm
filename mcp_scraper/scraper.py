"""
Intentionally synchronous — called via asyncio.to_thread() from the async MCP handlers.
"""

import re
import time
import logging
from typing import Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from .config import (
    REQUEST_DELAY_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    MAX_RAW_TEXT_CHARS,
    FANDOM_SEARCH_API,
    WIKIPEDIA_SUMMARY_URL,
    WIKIPEDIA_SEARCH_URL,
    SOURCE_PRIORITY,
)
from .models import Entity, ScrapeResult, Chunk

logger = logging.getLogger(__name__)

_SECTION_MAP = {
    "personality":    "personality",
    "character":      "personality",
    "traits":         "personality",
    "background":     "backstory",
    "history":        "backstory",
    "backstory":      "backstory",
    "biography":      "backstory",
    "early life":     "backstory",
    "appearance":     "appearance",
    "abilities":      "powers",
    "powers":         "powers",
    "skills":         "powers",
    "magic":          "powers",
    "equipment":      "powers",
    "relationship":   "relationships",
    "family":         "relationships",
    "allies":         "relationships",
    "enemies":        "relationships",
    "trivia":         "trivia",
    "notes":          "trivia",
}

_SKIP_SECTIONS = {
    "see also", "references", "external links", "navigation",
    "gallery", "videos", "merchandise", "quotes", "media",
    "cast", "crew", "navigation menu", "contents",
}

_HEADERS = {
    "User-Agent": (
        "FanficLLM-Scraper/1.0 (educational research project; "
        "contact: moldovanmihai312@gmail.com)"
    )
}


def _get(url: str, params: Optional[dict] = None) -> Optional[httpx.Response]:
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
        return None


def scrape_entity(name: str, fandom: str, entity_type: str = "character") -> ScrapeResult:
    entity = Entity(name=name, fandom=fandom, entity_type=entity_type)
    last_error = "No source returned data"

    for source in SOURCE_PRIORITY:
        if source == "fandom":
            result = _scrape_fandom(entity)
        elif source == "wikipedia":
            result = _scrape_wikipedia(entity)
        else:
            continue

        if result.success:
            logger.info(f"Scraped '{name}' ({fandom}) from {source}")
            return result
        if result.error:
            last_error = result.error

    logger.warning(f"All sources failed for '{name}' ({fandom}): {last_error}")
    return ScrapeResult(entity=entity, success=False, error=last_error)


def _scrape_fandom(entity: Entity) -> ScrapeResult:
    fandom_slug = _fandom_slug(entity.fandom)
    search_url = FANDOM_SEARCH_API.format(fandom=fandom_slug, query=quote(entity.name))

    resp = _get(search_url)
    if resp is None:
        return ScrapeResult(entity=entity, success=False, error="Fandom search API failed")

    try:
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return ScrapeResult(entity=entity, success=False, error="No Fandom results")
        article_url = items[0].get("url", "")
    except Exception as e:
        return ScrapeResult(entity=entity, success=False, error=f"Fandom JSON parse error: {e}")

    if not article_url:
        return ScrapeResult(entity=entity, success=False, error="Empty article URL from Fandom")

    page_resp = _get(article_url)
    if page_resp is None:
        return ScrapeResult(entity=entity, success=False, error="Could not fetch Fandom article")

    attributes = _parse_fandom_html(page_resp.text)
    if not attributes:
        return ScrapeResult(entity=entity, success=False, error="Fandom parse returned empty attributes")

    entity.source_url = article_url
    entity.source_type = "fandom"
    entity.description = attributes.get("description", "")[:500]

    return ScrapeResult(entity=entity, attributes=attributes, success=True)


def _parse_fandom_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    attributes: dict[str, list[str]] = {}

    infobox = soup.find("aside", class_=re.compile(r"portable-infobox|infobox", re.I))
    if infobox:
        infobox_text = _clean_text(infobox.get_text(separator=" "))
        if infobox_text:
            attributes.setdefault("infobox", []).append(infobox_text)

    content_div = soup.find("div", class_=re.compile(r"mw-parser-output|page__main", re.I))
    if content_div:
        first_p = content_div.find("p")
        if first_p:
            lead = _clean_text(first_p.get_text())
            if lead:
                attributes["description"] = [lead]

    current_key = "backstory"
    current_text: list[str] = []

    for tag in (content_div or soup).find_all(["h2", "h3", "p", "ul", "ol"]):
        if tag.name in ("h2", "h3"):
            if current_text:
                attributes.setdefault(current_key, []).extend(current_text)
                current_text = []
            heading = _clean_text(tag.get_text()).lower()
            if any(skip in heading for skip in _SKIP_SECTIONS):
                current_key = "__skip__"
            else:
                current_key = _map_section(heading)
        elif current_key != "__skip__":
            text = _clean_text(tag.get_text(separator=" "))
            if text and len(text) > 30:
                current_text.append(text)

    if current_text and current_key != "__skip__":
        attributes.setdefault(current_key, []).extend(current_text)

    return {k: "\n\n".join(v) for k, v in attributes.items() if v}


def _scrape_wikipedia(entity: Entity) -> ScrapeResult:
    title = _wikipedia_search(entity.name, fandom=entity.fandom)
    if not title:
        return ScrapeResult(entity=entity, success=False, error="Wikipedia search returned nothing")

    name_words = entity.name.lower().split()
    title_lower = title.lower()
    if entity.entity_type == "character" and not any(w in title_lower for w in name_words if len(w) > 3):
        return ScrapeResult(
            entity=entity,
            success=False,
            error=f"No dedicated Wikipedia article found for '{entity.name}' — best match was '{title}'. Try a Fandom wiki.",
        )

    summary_url = WIKIPEDIA_SUMMARY_URL.format(title=quote(title, safe=""))
    resp = _get(summary_url)
    if resp is None:
        return ScrapeResult(entity=entity, success=False, error="Wikipedia summary fetch failed")

    try:
        data = resp.json()
    except Exception as e:
        return ScrapeResult(entity=entity, success=False, error=f"Wikipedia JSON error: {e}")

    description = data.get("extract", "")
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

    attributes: dict = {}
    if description:
        attributes["description"] = description[:MAX_RAW_TEXT_CHARS]

    page_html_resp = _get(f"https://en.wikipedia.org/wiki/{quote(title, safe='')}")
    if page_html_resp:
        attributes.update(_parse_wikipedia_html(page_html_resp.text))

    if not attributes:
        return ScrapeResult(entity=entity, success=False, error="Wikipedia returned no content")

    entity.source_url  = page_url or f"https://en.wikipedia.org/wiki/{quote(title, safe='')}"
    entity.source_type = "wikipedia"
    entity.description = description[:500]

    return ScrapeResult(entity=entity, attributes=attributes, success=True)


def _wikipedia_search(query: str, fandom: str = "") -> Optional[str]:
    def _search(q: str) -> list[dict]:
        resp = _get(
            WIKIPEDIA_SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "srlimit": 5,
                "format": "json",
                "utf8": 1,
            },
        )
        if resp is None:
            return []
        try:
            return resp.json()["query"]["search"]
        except (KeyError, IndexError):
            return []

    name_lower = query.lower()

    if fandom:
        hits = _search(f"{query} {fandom} character")
        for h in hits:
            if name_lower in h["title"].lower():
                return h["title"]

    hits = _search(query)
    if not hits:
        return None
    for h in hits:
        if name_lower in h["title"].lower():
            return h["title"]
    return hits[0]["title"]


def _parse_wikipedia_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return {}

    attributes: dict[str, list[str]] = {}
    current_key = "backstory"
    current_text: list[str] = []

    for tag in content.find_all(["h2", "h3", "p", "ul"]):
        if tag.name in ("h2", "h3"):
            if current_text:
                attributes.setdefault(current_key, []).extend(current_text)
                current_text = []
            heading = _clean_text(tag.get_text()).lower()
            if any(skip in heading for skip in _SKIP_SECTIONS):
                current_key = "__skip__"
            else:
                current_key = _map_section(heading)
        elif current_key != "__skip__":
            text = _clean_text(tag.get_text(separator=" "))
            if text and len(text) > 40:
                current_text.append(text)

    if current_text and current_key != "__skip__":
        attributes.setdefault(current_key, []).extend(current_text)

    return {k: "\n\n".join(v)[:MAX_RAW_TEXT_CHARS] for k, v in attributes.items() if v}


def make_chunks(entity: Entity, entity_id: int, attributes: dict) -> list[Chunk]:
    chunks = []
    slug = entity.canonical_name.replace("::", "_").replace(" ", "_")

    for attr_key, text in attributes.items():
        if not text or not text.strip():
            continue
        for i, segment in enumerate(_split_text(text, max_chars=800, overlap=100)):
            chunks.append(
                Chunk(
                    chunk_id=f"{slug}__{attr_key}__{i:03d}",
                    text=segment,
                    entity_name=entity.name,
                    fandom=entity.fandom,
                    chunk_type=attr_key,
                    source_url=entity.source_url or "",
                    entity_type=entity.entity_type,
                )
            )
    return chunks


def _split_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    segments = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            segments.append(text[start:].strip())
            break
        boundary = text.rfind(". ", start, end)
        if boundary == -1 or boundary <= start:
            boundary = end
        else:
            boundary += 1
        segments.append(text[start:boundary].strip())
        start = boundary - overlap
    return [s for s in segments if s]


def _clean_text(text: str) -> str:
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _map_section(heading: str) -> str:
    for keyword, key in _SECTION_MAP.items():
        if keyword in heading:
            return key
    return "backstory"


def _fandom_slug(fandom: str) -> str:
    aliases = {
        "mcu":                       "marvelcinematicuniverse",
        "marvel":                    "marvelcinematicuniverse",
        "dc":                        "dc",
        "star wars":                 "starwars",
        "starwars":                  "starwars",
        "harry potter":              "harrypotter",
        "avatar":                    "avatar",
        "lotr":                      "lotr",
        "lord of the rings":         "lotr",
        "game of thrones":           "gameofthrones",
        "got":                       "gameofthrones",
        "naruto":                    "naruto",
        "one piece":                 "onepiece",
        "attack on titan":           "attackontitan",
        "aot":                       "attackontitan",
        "bartimaeus sequence":       "bartimaeus",
        "the bartimaeus sequence":   "bartimaeus",
        "bartimaeus trilogy":        "bartimaeus",
    }
    slug = fandom.lower().strip()
    return aliases.get(slug, slug.replace(" ", ""))
