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
    FANDOM_BASE_URL,
    FANDOM_MEDIAWIKI_API,
    WIKIPEDIA_SUMMARY_URL,
    WIKIPEDIA_SEARCH_URL,
    ANILIST_API_URL,
    JIKAN_API_URL,
    WIKIDATA_API_URL,
    WATTPAD_API_URL,
    SOURCE_PRIORITY,
)

try:
    from curl_cffi import requests as _cf_requests
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False
    logger.warning("curl_cffi not installed — Fandom will be blocked by Cloudflare. Run: pip install curl_cffi")
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


def _get_fandom(url: str, params: Optional[dict] = None):
    """
    GET with Chrome TLS fingerprint impersonation (curl_cffi) to bypass
    Cloudflare bot detection on Fandom wikis. Falls back to plain httpx
    if curl_cffi is not installed, though that will likely be blocked.
    """
    time.sleep(REQUEST_DELAY_SECONDS)
    if not _CURL_CFFI_AVAILABLE:
        return _get(url, params)
    try:
        resp = _cf_requests.get(
            url,
            params=params,
            impersonate="chrome120",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.warning(f"Fandom request failed {url}: {e}")
        return None


def _post(url: str, **kwargs) -> Optional[httpx.Response]:
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.post(url, **kwargs)
            resp.raise_for_status()
            return resp
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error posting {url}: {e}")
        return None


def scrape_entity(name: str, fandom: str, entity_type: str = "character") -> ScrapeResult:
    entity = Entity(name=name, fandom=fandom, entity_type=entity_type)
    last_error = "No source returned data"

    for source in SOURCE_PRIORITY:
        if source == "fandom":
            result = _scrape_fandom(entity)
        elif source == "anilist":
            result = _scrape_anilist(entity)
        elif source == "jikan":
            result = _scrape_jikan(entity)
        elif source == "wikidata":
            result = _scrape_wikidata(entity)
        elif source == "wikipedia":
            result = _scrape_wikipedia(entity)
        elif source == "wattpad":
            result = _scrape_wattpad(entity)
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
    base_url    = FANDOM_BASE_URL.format(fandom=fandom_slug)
    api_url     = FANDOM_MEDIAWIKI_API.format(fandom=fandom_slug)

    # Use MediaWiki search API — more reliable than the Fandom v1 Search endpoint
    search_resp = _get_fandom(api_url, params={
        "action": "query", "list": "search",
        "srsearch": entity.name, "srlimit": 3, "format": "json",
    })
    if search_resp is None:
        return ScrapeResult(entity=entity, success=False, error="Fandom search failed")

    try:
        hits = search_resp.json()["query"]["search"]
        if not hits:
            return ScrapeResult(entity=entity, success=False, error="No Fandom results")
        page_title = hits[0]["title"]
    except (KeyError, IndexError, Exception) as e:
        return ScrapeResult(entity=entity, success=False, error=f"Fandom search parse error: {e}")

    article_url = f"{base_url}/wiki/{quote(page_title.replace(' ', '_'))}"
    page_resp = _get_fandom(article_url)
    if page_resp is None:
        return ScrapeResult(entity=entity, success=False, error="Could not fetch Fandom article")

    attributes = _parse_fandom_html(page_resp.text)
    if not attributes:
        return ScrapeResult(entity=entity, success=False, error="Fandom parse returned empty attributes")

    entity.source_url  = article_url
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


_ANILIST_CHARACTER_QUERY = """
query ($search: String) {
  Character(search: $search) {
    name { full native alternative }
    description(asHtml: false)
    gender
    age
    siteUrl
    media(perPage: 5) { nodes { title { romaji english } type } }
  }
}
"""


def _scrape_anilist(entity: Entity) -> ScrapeResult:
    char = None
    for name_part in _name_parts(entity.name):
        resp = _post(
            ANILIST_API_URL,
            json={"query": _ANILIST_CHARACTER_QUERY, "variables": {"search": name_part}},
        )
        if resp is None:
            continue
        try:
            candidate = resp.json().get("data", {}).get("Character")
        except Exception:
            continue
        if not candidate:
            continue
        # Verify the returned character's name actually matches our query —
        # AniList returns its best fuzzy match which can be a completely different character.
        char_names = [
            (candidate.get("name") or {}).get("full", ""),
        ] + ((candidate.get("name") or {}).get("alternative") or [])
        if any(_title_matches_name(n, entity.name) for n in char_names if n):
            char = candidate
            break

    if not char:
        return ScrapeResult(entity=entity, success=False, error="Character not found on AniList")

    description = char.get("description") or ""
    description = re.sub(r"~!.+?!~", "", description, flags=re.DOTALL)  # strip spoiler tags
    description = re.sub(r"\*+", "", description).strip()

    media_titles = [
        (n.get("title", {}).get("english") or n.get("title", {}).get("romaji", "")).strip()
        for n in (char.get("media", {}).get("nodes") or [])
    ]

    attributes: dict = {}
    if description:
        attributes["description"] = description
        attributes["backstory"] = description

    infobox_parts = []
    if char.get("gender"):
        infobox_parts.append(f"Gender: {char['gender']}")
    if char.get("age"):
        infobox_parts.append(f"Age: {char['age']}")
    if infobox_parts:
        attributes["infobox"] = "\n".join(infobox_parts)
    if media_titles:
        attributes["appearances"] = "Appears in: " + ", ".join(t for t in media_titles if t)

    if not attributes:
        return ScrapeResult(entity=entity, success=False, error="AniList returned no content")

    entity.source_url = char.get("siteUrl", ANILIST_API_URL)
    entity.source_type = "anilist"
    entity.description = description[:500]
    return ScrapeResult(entity=entity, attributes=attributes, success=True)


def _scrape_jikan(entity: Entity) -> ScrapeResult:
    """MyAnimeList character data via the Jikan REST API (no API key required)."""
    char_data = None
    for name_part in _name_parts(entity.name):
        resp = _get(
            f"{JIKAN_API_URL}/characters",
            params={"q": name_part, "limit": 5, "order_by": "favorites", "sort": "desc"},
        )
        if resp is None:
            continue
        try:
            results = resp.json().get("data", [])
        except Exception:
            continue
        for r in results:
            if _title_matches_name(r.get("name", ""), entity.name):
                char_data = r
                break
        # No blind fallback — a name mismatch means this source has no match for us.
        if char_data:
            break

    if not char_data:
        return ScrapeResult(entity=entity, success=False, error="Character not found on MyAnimeList")

    char_id = char_data.get("mal_id")
    detail = char_data
    if char_id:
        detail_resp = _get(f"{JIKAN_API_URL}/characters/{char_id}/full")
        if detail_resp:
            try:
                detail = detail_resp.json().get("data", char_data)
            except Exception:
                pass

    about = (detail.get("about") or "").strip()
    nicknames = detail.get("nicknames") or []

    attributes: dict = {}
    if about:
        attributes["description"] = about[:MAX_RAW_TEXT_CHARS]
        attributes["backstory"] = about[:MAX_RAW_TEXT_CHARS]
    if nicknames:
        attributes["infobox"] = "Also known as: " + ", ".join(nicknames)

    if not attributes:
        return ScrapeResult(entity=entity, success=False, error="Jikan returned no content")

    entity.source_url = char_data.get("url", f"https://myanimelist.net/character/{char_id}")
    entity.source_type = "jikan"
    entity.description = about[:500]
    return ScrapeResult(entity=entity, attributes=attributes, success=True)


def _scrape_wikidata(entity: Entity) -> ScrapeResult:
    """
    Search Wikidata to find the canonical Wikipedia article title for any entity —
    real people (vloggers, athletes, actors) or fictional characters that have a
    dedicated Wikipedia page. Delegates content fetching to _fetch_wikipedia_article.
    """
    wikidata_id = None
    wikidata_desc = ""

    fandom_lower = entity.fandom.lower()
    for name_part in _name_parts(entity.name):
        resp = _get(WIKIDATA_API_URL, params={
            "action": "wbsearchentities",
            "search": name_part,
            "language": "en",
            "type": "item",
            "limit": 10,
            "format": "json",
        })
        if resp is None:
            continue
        try:
            results = resp.json().get("search", [])
        except Exception:
            continue

        # Prefer a result whose description mentions the fandom (e.g. "Romanian YouTuber")
        for r in results:
            label = r.get("label", "")
            desc  = r.get("description", "").lower()
            if _title_matches_name(label, entity.name) and fandom_lower in desc:
                wikidata_id  = r["id"]
                wikidata_desc = r.get("description", "")
                break

        # Fall back to any label match
        if not wikidata_id:
            for r in results:
                if _title_matches_name(r.get("label", ""), entity.name):
                    wikidata_id  = r["id"]
                    wikidata_desc = r.get("description", "")
                    break

        if wikidata_id:
            break

    if not wikidata_id:
        return ScrapeResult(entity=entity, success=False, error="Not found on Wikidata")

    # Resolve the English Wikipedia title via sitelinks
    links_resp = _get(WIKIDATA_API_URL, params={
        "action": "wbgetentities",
        "ids": wikidata_id,
        "props": "sitelinks",
        "format": "json",
    })
    enwiki_title = None
    if links_resp:
        try:
            enwiki_title = (
                links_resp.json()
                .get("entities", {})
                .get(wikidata_id, {})
                .get("sitelinks", {})
                .get("enwiki", {})
                .get("title")
            )
        except Exception:
            pass

    if enwiki_title:
        result = _fetch_wikipedia_article(entity, enwiki_title)
        if result.success:
            return result

    if not wikidata_desc:
        return ScrapeResult(entity=entity, success=False, error="Wikidata entity has no usable content")

    entity.source_url = f"https://www.wikidata.org/wiki/{wikidata_id}"
    entity.source_type = "wikidata"
    entity.description = wikidata_desc[:500]
    return ScrapeResult(entity=entity, attributes={"description": wikidata_desc}, success=True)


def _scrape_wattpad(entity: Entity) -> ScrapeResult:
    """
    Search Wattpad for stories featuring this character/person.
    Wattpad has no character profiles — we extract story descriptions as
    supplementary context showing how fanfic writers portray the entity.
    This source runs last and only fires if all authoritative sources fail.
    """
    query = f"{entity.name} {entity.fandom}".strip()
    resp = _get(WATTPAD_API_URL, params={
        "query": query,
        "limit": 5,
        "fields": "id,title,description,tags,mainCategory",
    })
    if resp is None:
        return ScrapeResult(entity=entity, success=False, error="Wattpad request failed")

    try:
        stories = resp.json().get("stories", [])
    except Exception as e:
        return ScrapeResult(entity=entity, success=False, error=f"Wattpad parse error: {e}")

    if not stories:
        return ScrapeResult(entity=entity, success=False, error="No Wattpad stories found")

    name_parts_lower = [p.lower() for p in _name_parts(entity.name)]
    relevant = [
        (s.get("title", ""), s.get("description", ""))
        for s in stories
        if any(p in (s.get("title", "") + " " + s.get("description", "")).lower()
               for p in name_parts_lower)
    ]
    if not relevant:
        relevant = [(s.get("title", ""), s.get("description", "")) for s in stories[:3]]

    tags: set[str] = set()
    for s in stories:
        tags.update(s.get("tags") or [])

    snippets = [f"Story: {t}\n{d}" for t, d in relevant if d]
    if not snippets:
        return ScrapeResult(entity=entity, success=False, error="Wattpad stories have no descriptions")

    combined = "\n\n---\n\n".join(snippets)
    attributes: dict = {
        "fanfic_context": combined[:MAX_RAW_TEXT_CHARS],
        "description": snippets[0][:1000],
    }
    if tags:
        attributes["infobox"] = "Common Wattpad tags: " + ", ".join(sorted(tags)[:20])

    entity.source_url = f"https://www.wattpad.com/search/{quote(query)}"
    entity.source_type = "wattpad"
    entity.description = snippets[0][:500]
    return ScrapeResult(entity=entity, attributes=attributes, success=True)


def _name_parts(name: str) -> list[str]:
    """Split alias-style names like 'Selly or Andrei Selaru' into ['Selly', 'Andrei Selaru']."""
    parts = [p.strip() for p in re.split(r'\s+or\s+', name, flags=re.IGNORECASE)]
    return [p for p in parts if p]


def _title_matches_name(title: str, name: str) -> bool:
    """True if the title contains any part of a possibly alias-joined name."""
    title_lower = title.lower()
    return any(part.lower() in title_lower for part in _name_parts(name))


def _scrape_wikipedia(entity: Entity) -> ScrapeResult:
    # For characters, only accept a dedicated article if it is actually about this
    # character in this fandom — not a real person who happens to share the name.
    if entity.entity_type == "character":
        title = _wikipedia_search_character(entity.name, entity.fandom)
    else:
        title = _wikipedia_search(entity.name, fandom=entity.fandom)

    if title:
        result = _fetch_wikipedia_article(entity, title)
        if result.success:
            return result

    if entity.entity_type == "character":
        # Try a broader name search before resorting to the franchise page —
        # catches real people (vloggers, athletes) whose fandom slug has no wiki.
        broad_title = _wikipedia_search(entity.name)
        if broad_title:
            result = _fetch_wikipedia_article(entity, broad_title)
            if result.success:
                return result
        return _scrape_wikipedia_franchise_page(entity)

    return ScrapeResult(entity=entity, success=False, error=f"No Wikipedia article found for '{entity.name}'")


def _fetch_wikipedia_article(entity: Entity, title: str) -> ScrapeResult:
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


def _scrape_wikipedia_franchise_page(entity: Entity) -> ScrapeResult:
    """
    No dedicated Wikipedia article for this character. Find the franchise/show page
    and extract every paragraph that mentions the character by name.
    """
    franchise_title = _wikipedia_search(entity.fandom)
    if not franchise_title:
        return ScrapeResult(entity=entity, success=False,
                            error=f"No Wikipedia page found for '{entity.name}' or '{entity.fandom}'")

    page_resp = _get(f"https://en.wikipedia.org/wiki/{quote(franchise_title, safe='')}")
    if not page_resp:
        return ScrapeResult(entity=entity, success=False, error="Could not fetch franchise Wikipedia page")

    soup = BeautifulSoup(page_resp.text, "lxml")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return ScrapeResult(entity=entity, success=False, error="Could not parse franchise Wikipedia page")

    search_parts = [p.lower() for p in _name_parts(entity.name)]
    mentions: list[str] = []
    for tag in content.find_all(["p", "li"]):
        text = _clean_text(tag.get_text(separator=" "))
        text_lower = text.lower()
        if any(part in text_lower for part in search_parts) and len(text) > 40:
            mentions.append(text)

    if not mentions:
        return ScrapeResult(entity=entity, success=False,
                            error=f"No mention of '{entity.name}' found in the '{franchise_title}' Wikipedia article")

    page_url = f"https://en.wikipedia.org/wiki/{quote(franchise_title, safe='')}"
    entity.source_url  = page_url
    entity.source_type = "wikipedia"
    entity.description = mentions[0][:500]

    return ScrapeResult(entity=entity, success=True, attributes={
        "description": mentions[0],
        "backstory":   "\n\n".join(mentions),
    })


def _wiki_search(q: str) -> list[dict]:
    resp = _get(
        WIKIPEDIA_SEARCH_URL,
        params={"action": "query", "list": "search", "srsearch": q,
                "srlimit": 5, "format": "json", "utf8": 1},
    )
    if resp is None:
        return []
    try:
        return resp.json()["query"]["search"]
    except (KeyError, IndexError):
        return []


def _wikipedia_search(query: str, fandom: str = "") -> Optional[str]:
    if fandom:
        hits = _wiki_search(f"{query} {fandom} character")
        for h in hits:
            if _title_matches_name(h["title"], query):
                return h["title"]

    hits = _wiki_search(query)
    if not hits:
        return None
    for h in hits:
        if _title_matches_name(h["title"], query):
            return h["title"]
    return hits[0]["title"]


def _wikipedia_search_character(name: str, fandom: str) -> Optional[str]:
    """
    Like _wikipedia_search but only returns a title when the article is clearly
    about this character in this fandom — not a real person who shares the name.
    Checks that the fandom appears in the search result snippet.
    """
    fandom_lower = fandom.lower()

    # Fandom-qualified search first
    hits = _wiki_search(f"{name} {fandom} character")
    for h in hits:
        if _title_matches_name(h["title"], name):
            return h["title"]

    # Plain name search — only accept if the snippet mentions the fandom
    hits = _wiki_search(name)
    for h in hits:
        if _title_matches_name(h["title"], name):
            if fandom_lower in h.get("snippet", "").lower():
                return h["title"]

    return None


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
    # Strip all non-alphanumeric chars so "Mr. Robot" → "mrrobot", not "mr.robot"
    return aliases.get(slug, re.sub(r"[^a-z0-9]", "", slug))
