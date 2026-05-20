"""
chat_scraper.py — Agentic scraper that uses LM Studio + Gemma 3 12B.

Unlike the MCP-in-LM-Studio approach (which relies on LM Studio's broken MCP
integration), this script drives the full tool-call loop itself:

  1. Send user message + tool definitions to LM Studio's OpenAI-compatible API
  2. When model returns finish_reason="tool_calls", execute the real tool locally
  3. Feed the tool result back as a tool message
  4. Repeat until the model returns finish_reason="stop"

Usage
-----
    python chat_scraper.py                       # interactive REPL
    python chat_scraper.py "Hermione Granger, Harry Potter"
    python chat_scraper.py --file characters.txt
    python chat_scraper.py --url http://192.168.1.66:1234  # custom LM Studio URL
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from mcp_scraper import database, vector_store, scraper
from mcp_scraper.database import is_cache_fresh

# ── Colours ────────────────────────────────────────────────────────────────

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def err(msg):  print(f"  {RED}✗{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def llm(msg):  print(f"  {BLUE}◆{RESET}  {msg}")

# ── Tool definitions (OpenAI function-call format) ─────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_entity",
            "description": (
                "Check if a character, place, or concept is already in the knowledge base. "
                "Returns cached information without hitting the web. "
                "ALWAYS call this BEFORE scrape_and_store."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string", "description": "Character or topic name, e.g. 'Tony Stark'"},
                    "fandom": {"type": "string", "description": "Fandom/universe, e.g. 'MCU', 'Harry Potter', 'naruto'"},
                },
                "required": ["name", "fandom"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_and_store",
            "description": (
                "Scrape character or topic info from the web (Fandom wiki / Wikipedia) "
                "and store it in the knowledge base. "
                "Use ONLY when lookup_entity says found=false or cache_fresh=false."
            ),
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_entities",
            "description": "List all characters and topics currently stored in the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fandom": {"type": "string", "description": "Filter by fandom (optional)"},
                },
                "required": [],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a Knowledge Base Curator for a fanfiction research system.
Your ONLY job is to call the available tools to populate a vector database with canon information.
You do NOT write stories or generate fictional content.

Rules:
- ALWAYS call lookup_entity first before scraping anything.
- If lookup_entity returns found=true and cache_fresh=true → report "already in DB, skipping".
- If lookup_entity returns found=false OR cache_fresh=false → call scrape_and_store.
- After each scrape_and_store, report the status, chunks_stored, and source_url from the tool response.
- If no fandom is given, ask for it before calling any tool.
- Never answer from training data. Only report what the tools return.
"""

# ── Tool executor (runs locally, not via MCP) ──────────────────────────────

def _truncate_attrs(attrs: dict) -> dict:
    return {k: (v[:300] + "…" if len(v) > 300 else v) for k, v in attrs.items()}


def exec_lookup_entity(name: str, fandom: str) -> dict:
    entity = database.get_entity(name, fandom)
    if entity is None:
        return {
            "found": False,
            "message": f"'{name}' ({fandom}) is not in the knowledge base. Use scrape_and_store to fetch it.",
        }
    is_fresh = is_cache_fresh(entity)
    attrs = database.get_attributes(entity.id)
    return {
        "found": True,
        "cache_fresh": is_fresh,
        "entity": {
            "name": entity.name,
            "fandom": entity.fandom,
            "entity_type": entity.entity_type,
            "source_url": entity.source_url,
            "last_scraped": entity.last_scraped_at.isoformat() if entity.last_scraped_at else None,
        },
        "attributes": _truncate_attrs(attrs),
        "hint": None if is_fresh else "Cache stale — call scrape_and_store with force=true.",
    }


def exec_scrape_and_store(name: str, fandom: str, entity_type: str = "character", force: bool = False) -> dict:
    if not force:
        cached = database.get_entity(name, fandom)
        if cached and is_cache_fresh(cached):
            return {
                "status": "cache_hit",
                "message": f"'{name}' ({fandom}) is already fresh in the knowledge base.",
                "source_url": cached.source_url,
            }

    result = scraper.scrape_entity(name, fandom, entity_type)
    if not result.success:
        return {"status": "error", "message": f"Could not scrape '{name}' ({fandom}): {result.error}"}

    entity_id = database.upsert_entity(result.entity)
    database.upsert_attributes(entity_id, result.attributes)
    vector_store.delete_entity_chunks(name, fandom)
    chunks = scraper.make_chunks(result.entity, entity_id, result.attributes)
    vector_store.upsert_chunks(chunks)

    return {
        "status": "success",
        "name": result.entity.name,
        "fandom": result.entity.fandom,
        "source_url": result.entity.source_url,
        "chunks_stored": len(chunks),
        "attributes": list(result.attributes.keys()),
    }


def exec_list_entities(fandom: Optional[str] = None) -> dict:
    entities = database.list_entities(fandom=fandom)
    total_chunks = vector_store.count()
    return {
        "entity_count": len(entities),
        "total_vector_chunks": total_chunks,
        "entities": [
            {
                "name": e.name,
                "fandom": e.fandom,
                "entity_type": e.entity_type,
                "last_scraped": e.last_scraped_at.isoformat() if e.last_scraped_at else None,
            }
            for e in entities
        ],
    }


def execute_tool(tool_name: str, arguments: dict) -> str:
    info(f"Executing tool: {tool_name}({', '.join(f'{k}={v!r}' for k, v in arguments.items())})")
    try:
        if tool_name == "lookup_entity":
            result = exec_lookup_entity(arguments["name"], arguments["fandom"])
        elif tool_name == "scrape_and_store":
            result = exec_scrape_and_store(
                arguments["name"],
                arguments["fandom"],
                arguments.get("entity_type", "character"),
                arguments.get("force", False),
            )
        elif tool_name == "list_entities":
            result = exec_list_entities(arguments.get("fandom"))
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"error": str(e)}

    as_json = json.dumps(result, indent=2, ensure_ascii=False)
    # Print a brief summary
    if tool_name == "lookup_entity":
        found = result.get("found", False)
        fresh = result.get("cache_fresh", False)
        ok(f"lookup: found={found}, cache_fresh={fresh}")
    elif tool_name == "scrape_and_store":
        status = result.get("status", "?")
        chunks = result.get("chunks_stored", 0)
        url = result.get("source_url", "")
        if status == "success":
            ok(f"scraped: {chunks} chunks stored — {url}")
        elif status == "cache_hit":
            ok(f"cache hit — {url}")
        else:
            err(f"scrape failed: {result.get('message', '?')}")
    elif tool_name == "list_entities":
        ok(f"list: {result.get('entity_count', 0)} entities, {result.get('total_vector_chunks', 0)} chunks")
    return as_json


# ── LM Studio API client ───────────────────────────────────────────────────

class LMStudioClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _post_with_retry(self, payload: dict, retries: int = 2) -> dict:
        """POST to LM Studio with retry on 400/500 (model crash recovery)."""
        import time as _time
        for attempt in range(retries + 1):
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                )
            if resp.is_success:
                return resp.json()
            if attempt < retries and resp.status_code in (400, 500):
                warn(f"LM Studio error ({resp.status_code}), retrying in 3s… (attempt {attempt+1}/{retries})")
                _time.sleep(3)
                continue
            raise RuntimeError(
                f"LM Studio returned {resp.status_code}: {resp.text[:300]}"
            )
        raise RuntimeError("All retries exhausted")

    @staticmethod
    def _trim_messages(messages: list[dict], max_chars: int = 24_000) -> list[dict]:
        """Drop middle tool-result messages if the payload exceeds max_chars."""
        total = sum(len(json.dumps(m)) for m in messages)
        if total <= max_chars:
            return messages

        # Keep system + user (first 2) and the last 4 messages; drop middle rounds
        if len(messages) <= 6:
            return messages
        trimmed = messages[:2] + messages[-4:]
        return trimmed

    def chat(self, messages: list[dict], max_iterations: int = 8) -> str:
        """Run a full tool-call loop. Returns the final assistant text."""
        iteration = 0
        error_streak = 0   # consecutive tool errors
        while iteration < max_iterations:
            iteration += 1
            send = self._trim_messages(messages)
            payload = {
                "model": self.model,
                "messages": send,
                "tools": TOOLS,
                "tool_choice": "auto",
                "max_tokens": 1024,
                "temperature": 0.1,
            }

            data = self._post_with_retry(payload)

            choice = data["choices"][0]
            message = choice["message"]
            finish = choice["finish_reason"]

            # LM Studio adds 'reasoning_content' which it rejects when echoed back
            clean_msg = {k: v for k, v in message.items() if k != "reasoning_content"}
            messages.append(clean_msg)

            if finish == "stop" or finish == "end_turn":
                return message.get("content", "").strip()

            if finish == "tool_calls":
                tool_calls = message.get("tool_calls", [])
                if not tool_calls:
                    return message.get("content", "").strip()

                # Execute each tool call and collect results
                round_has_error = False
                for tc in tool_calls:
                    fn = tc["function"]
                    try:
                        args = json.loads(fn["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result_text = execute_tool(fn["name"], args)
                    result_data = json.loads(result_text)
                    if result_data.get("status") == "error" or "error" in result_data:
                        round_has_error = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_text,
                    })

                error_streak = (error_streak + 1) if round_has_error else 0
                if error_streak >= 2:
                    # Stop after 2 consecutive error rounds to prevent Gemma from crashing
                    last_result = json.loads(messages[-1]["content"])
                    reason = last_result.get("message", last_result.get("error", "unknown error"))
                    return f"Could not scrape entity: {reason}"
                continue  # next iteration with tool results in context

            # Unknown finish reason — return whatever content we have
            return message.get("content", "").strip()

        return "[Max iterations reached]"


# ── Session ────────────────────────────────────────────────────────────────

class ScraperSession:
    def __init__(self, lm: LMStudioClient):
        self.lm = lm

    def run(self, user_message: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        return self.lm.chat(messages)


# ── Modes ──────────────────────────────────────────────────────────────────

def run_once(session: ScraperSession, message: str):
    print(f"\n{DIM}{'─'*60}{RESET}")
    print(f"  {CYAN}User:{RESET} {message}")
    print()
    try:
        reply = session.run(message)
        print()
        llm(reply)
    except RuntimeError as e:
        print()
        err(f"LM Studio error: {e}")
    print()


def run_file(session: ScraperSession, path: str):
    lines = Path(path).read_text().splitlines()
    names = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            warn(f"Skipping malformed line: {raw!r}  (expected: Name | Fandom [| type])")
            continue
        name   = parts[0]
        fandom = parts[1]
        etype  = parts[2] if len(parts) > 2 else "character"
        names.append(f"- {name}, {fandom}" + (f", {etype}" if etype != "character" else ""))

    if not names:
        err("No valid entries in file.")
        return

    message = "Check and store these entities:\n" + "\n".join(names)
    run_once(session, message)


def run_interactive(session: ScraperSession):
    print(f"\n  {CYAN}Fanfic Knowledge Base — LM Studio Chat Scraper{RESET}")
    print(f"  {DIM}Talking to: {session.lm.base_url}  model: {session.lm.model}{RESET}")
    print(f"  {DIM}Type character names (e.g. 'Hermione Granger, Harry Potter'){RESET}")
    print(f"  {DIM}or ask anything — the model will call the real tools.{RESET}")
    print(f"  {DIM}Type 'quit' or Ctrl-C to exit.{RESET}\n")

    while True:
        try:
            raw = input(f"  {CYAN}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye.")
            break
        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            print("  Bye.")
            break
        print()
        try:
            reply = session.run(raw)
            print()
            llm(reply)
        except RuntimeError as e:
            print()
            err(f"LM Studio error: {e}")
        print()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agentic scraper: LM Studio + real tool execution (no MCP required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("message", nargs="?",
                        help="User message, e.g. 'Hermione Granger, Harry Potter'")
    parser.add_argument("--url", default="http://192.168.1.66:1234",
                        help="LM Studio base URL (default: http://192.168.1.66:1234)")
    parser.add_argument("--model", default="google/gemma-3-12b",
                        help="Model ID to use (default: google/gemma-3-12b)")
    parser.add_argument("--file", metavar="PATH",
                        help="Batch file: one 'Name | Fandom [| type]' per line")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Start interactive chat REPL")

    args = parser.parse_args()
    database.init_db()

    # Verify LM Studio is reachable
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{args.url.rstrip('/')}/v1/models")
            r.raise_for_status()
        info(f"Connected to LM Studio at {args.url}")
    except Exception as e:
        err(f"Cannot reach LM Studio at {args.url}: {e}")
        sys.exit(1)

    lm = LMStudioClient(base_url=args.url, model=args.model)
    session = ScraperSession(lm)

    if args.interactive or (not args.message and not args.file):
        run_interactive(session)
    elif args.file:
        run_file(session, args.file)
    else:
        run_once(session, args.message)


if __name__ == "__main__":
    main()
