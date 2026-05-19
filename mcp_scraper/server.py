import asyncio
import json
import logging
import sys
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import database, vector_store, scraper
from .config import LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

app = Server("fanfic-knowledge-base")


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_entity",
            description=(
                "Get full information about a character, place, or concept. "
                "Checks the knowledge base cache first; if not found or stale, "
                "automatically scrapes the web and stores the result. "
                "Use this as your single entry point for any entity lookup."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "description": "Character or topic name, e.g. 'Tony Stark'"},
                    "fandom":      {"type": "string", "description": "Fandom/universe, e.g. 'MCU', 'harrypotter', 'naruto'"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["character", "place", "concept", "event"],
                        "description": "Type of entity (default: character)",
                    },
                },
                "required": ["name", "fandom"],
            },
        ),
        types.Tool(
            name="lookup_entity",
            description=(
                "Check if a character, place, or concept is already in the "
                "knowledge base. Returns cached information without hitting the web. "
                "Use this BEFORE scrape_and_store to avoid unnecessary requests."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":   {"type": "string", "description": "Character or topic name"},
                    "fandom": {"type": "string", "description": "Fandom/universe"},
                },
                "required": ["name", "fandom"],
            },
        ),
        types.Tool(
            name="scrape_and_store",
            description=(
                "Scrape character or topic information from the web (Fandom wiki or Wikipedia) "
                "and store it in the knowledge base. "
                "Use this when lookup_entity returns nothing or stale data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name":        {"type": "string",  "description": "Character or topic name"},
                    "fandom":      {"type": "string",  "description": "Fandom/universe name"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["character", "place", "concept", "event"],
                        "description": "Type of entity (default: character)",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force re-scrape even if cached data is fresh (default: false)",
                    },
                },
                "required": ["name", "fandom"],
            },
        ),
        types.Tool(
            name="search_knowledge",
            description=(
                "Semantic search over the knowledge base. "
                "Use this to retrieve relevant character traits, backstory, or relationships "
                "to enrich fanfiction generation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Natural language query"},
                    "fandom":      {"type": "string",  "description": "Limit results to this fandom (optional)"},
                    "entity_name": {"type": "string",  "description": "Limit results to this character (optional)"},
                    "chunk_type":  {
                        "type": "string",
                        "enum": ["personality", "backstory", "appearance", "powers", "relationships", "trivia", "description"],
                        "description": "Limit to a specific type of information (optional)",
                    },
                    "n_results": {"type": "integer", "description": "Number of results to return (default: 5, max: 20)"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="list_entities",
            description="List all characters and topics currently stored in the knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "fandom":      {"type": "string", "description": "Filter by fandom (optional)"},
                    "entity_type": {"type": "string", "description": "Filter by type: character, place, concept, event (optional)"},
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    logger.info(f"Tool called: {name}  args={arguments}")

    try:
        if name == "get_entity":
            result = await _tool_get_entity(arguments)
        elif name == "lookup_entity":
            result = await _tool_lookup_entity(arguments)
        elif name == "scrape_and_store":
            result = await _tool_scrape_and_store(arguments)
        elif name == "search_knowledge":
            result = await _tool_search_knowledge(arguments)
        elif name == "list_entities":
            result = await _tool_list_entities(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception(f"Tool '{name}' raised an unhandled exception")
        result = {"error": str(e)}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


_ATTR_PREVIEW_CHARS = 300


def _truncate_attrs(attrs: dict) -> dict:
    return {k: v[:_ATTR_PREVIEW_CHARS] + "…" if len(v) > _ATTR_PREVIEW_CHARS else v
            for k, v in attrs.items()}


async def _tool_get_entity(args: dict) -> dict:
    name        = args["name"].strip()
    fandom      = args["fandom"].strip()
    entity_type = args.get("entity_type", "character")

    entity = await asyncio.to_thread(database.get_entity, name, fandom)
    if entity and database.is_cache_fresh(entity):
        top_chunks = await asyncio.to_thread(vector_store.search, name, 8, fandom, None, None)
        return {
            "source": "cache",
            "entity": {
                "name":         entity.name,
                "fandom":       entity.fandom,
                "entity_type":  entity.entity_type,
                "description":  entity.description,
                "source_url":   entity.source_url,
                "last_scraped": entity.last_scraped_at.isoformat() if entity.last_scraped_at else None,
            },
            "canon_details": [{"type": c["chunk_type"], "text": c["text"]} for c in top_chunks],
        }

    result = await asyncio.to_thread(scraper.scrape_entity, name, fandom, entity_type)
    if not result.success:
        return {"error": f"Could not find '{name}' ({fandom}): {result.error}"}

    entity_id = await asyncio.to_thread(database.upsert_entity, result.entity)
    await asyncio.to_thread(database.upsert_attributes, entity_id, result.attributes)
    await asyncio.to_thread(vector_store.delete_entity_chunks, name, fandom)
    chunks = scraper.make_chunks(result.entity, entity_id, result.attributes)
    await asyncio.to_thread(vector_store.upsert_chunks, chunks)
    top_chunks = await asyncio.to_thread(vector_store.search, name, 8, fandom, None, None)

    return {
        "source":       result.entity.source_type,
        "source_url":   result.entity.source_url,
        "entity": {
            "name":        result.entity.name,
            "fandom":      result.entity.fandom,
            "entity_type": result.entity.entity_type,
            "description": result.entity.description,
        },
        "chunks_stored": len(chunks),
        "canon_details": [{"type": c["chunk_type"], "text": c["text"]} for c in top_chunks],
    }


async def _tool_lookup_entity(args: dict) -> dict:
    name   = args["name"].strip()
    fandom = args["fandom"].strip()

    entity = await asyncio.to_thread(database.get_entity, name, fandom)
    if entity is None:
        return {
            "found": False,
            "message": f"'{name}' ({fandom}) is not in the knowledge base. Use scrape_and_store to fetch it.",
        }

    is_fresh = database.is_cache_fresh(entity)
    attrs    = await asyncio.to_thread(database.get_attributes, entity.id)

    return {
        "found":       True,
        "cache_fresh": is_fresh,
        "entity": {
            "name":         entity.name,
            "fandom":       entity.fandom,
            "entity_type":  entity.entity_type,
            "description":  entity.description,
            "source_url":   entity.source_url,
            "last_scraped": entity.last_scraped_at.isoformat() if entity.last_scraped_at else None,
        },
        "attributes": _truncate_attrs(attrs),
        "hint": None if is_fresh else "Cache is stale. Consider calling scrape_and_store with force=true.",
    }


async def _tool_scrape_and_store(args: dict) -> dict:
    name        = args["name"].strip()
    fandom      = args["fandom"].strip()
    entity_type = args.get("entity_type", "character")
    force       = args.get("force", False)

    if not force:
        cached = await asyncio.to_thread(database.get_entity, name, fandom)
        if cached and database.is_cache_fresh(cached):
            # Guard: ChromaDB may be missing chunks even though SQLite is fresh
            # (e.g. after a vector store reset, or if the initial write failed).
            chroma_ok = await asyncio.to_thread(vector_store.has_entity_chunks, name, fandom)
            if not chroma_ok:
                attrs = await asyncio.to_thread(database.get_attributes, cached.id)
                if attrs:
                    chunks = scraper.make_chunks(cached, cached.id, attrs)
                    await asyncio.to_thread(vector_store.upsert_chunks, chunks)
                    logger.info(
                        f"Backfilled {len(chunks)} ChromaDB chunks for '{name}' ({fandom}) from SQLite cache"
                    )
            return {
                "status":      "cache_hit",
                "message":     f"'{name}' ({fandom}) is already fresh in the knowledge base.",
                "source_url":  cached.source_url,
                "description": cached.description,
            }

    result = await asyncio.to_thread(scraper.scrape_entity, name, fandom, entity_type)
    if not result.success:
        return {"status": "error", "message": f"Could not scrape '{name}' ({fandom}): {result.error}"}

    entity_id = await asyncio.to_thread(database.upsert_entity, result.entity)
    await asyncio.to_thread(database.upsert_attributes, entity_id, result.attributes)
    await asyncio.to_thread(vector_store.delete_entity_chunks, name, fandom)
    chunks = scraper.make_chunks(result.entity, entity_id, result.attributes)
    await asyncio.to_thread(vector_store.upsert_chunks, chunks)

    return {
        "status":        "success",
        "name":          result.entity.name,
        "fandom":        result.entity.fandom,
        "source":        result.entity.source_type,
        "source_url":    result.entity.source_url,
        "description":   result.entity.description,
        "chunks_stored": len(chunks),
        "attributes":    list(result.attributes.keys()),
    }


async def _tool_search_knowledge(args: dict) -> dict:
    query       = args["query"].strip()
    fandom      = args.get("fandom")
    entity_name = args.get("entity_name")
    chunk_type  = args.get("chunk_type")
    n_results   = min(int(args.get("n_results", 5)), 20)

    hits = await asyncio.to_thread(
        vector_store.search, query, n_results, fandom, entity_name, chunk_type
    )

    if not hits:
        return {"results": [], "message": "No matching knowledge found. Try scrape_and_store first."}

    return {"query": query, "results": hits, "count": len(hits)}


async def _tool_list_entities(args: dict) -> dict:
    fandom      = args.get("fandom")
    entity_type = args.get("entity_type")

    entities     = await asyncio.to_thread(database.list_entities, fandom, entity_type)
    total_chunks = await asyncio.to_thread(vector_store.count)

    return {
        "entity_count":        len(entities),
        "total_vector_chunks": total_chunks,
        "entities": [
            {
                "name":         e.name,
                "fandom":       e.fandom,
                "entity_type":  e.entity_type,
                "description":  (e.description or "")[:150],
                "last_scraped": e.last_scraped_at.isoformat() if e.last_scraped_at else None,
                "source":       e.source_type,
            }
            for e in entities
        ],
    }


async def main():
    database.init_db()
    logger.info("Fanfic Knowledge Base MCP server starting (stdio transport)...")

    # Pre-warm the embedding model so the first tool call doesn't time out.
    # Cold load takes ~8 s (HuggingFace cache checks + model weights).
    logger.info("Pre-warming ChromaDB embedding model...")
    await asyncio.to_thread(vector_store._get_collection)
    logger.info("Embedding model ready.")

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="fanfic-knowledge-base",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
