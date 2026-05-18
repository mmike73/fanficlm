# Fanfic Knowledge Base — Quick Start

A local knowledge base for fanfiction characters and lore, powered by ChromaDB + sentence-transformers, integrated into LM Studio via MCP.

---

## Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai) 0.3.5 or later (MCP support required)
- Internet access for first-time scraping

---

## 1. Install dependencies

```bash
# from the project root
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r mcp_scraper/requirements.txt
```

The embedding model (`all-MiniLM-L6-v2`, ~90 MB) downloads automatically on first run and is then cached locally.

---

## 2. Configure LM Studio

### Linux

Open or create the LM Studio MCP config file:

```
~/.config/lmstudio/mcp_servers.json
```

Add the following block (adjust the path to match your project location):

```json
{
  "fanfic-knowledge-base": {
    "command": "/path/to/fanficlm/.venv/bin/python",
    "args": ["-m", "mcp_scraper.server"],
    "cwd": "/path/to/fanficlm",
    "env": {
      "LOG_LEVEL": "INFO"
    }
  }
}
```

### Windows

Open or create the LM Studio MCP config file:

```
%APPDATA%\LM Studio\mcp_servers.json
```

Add the following block (use forward slashes or escaped backslashes):

```json
{
  "fanfic-knowledge-base": {
    "command": "C:/path/to/fanficlm/.venv/Scripts/python.exe",
    "args": ["-m", "mcp_scraper.server"],
    "cwd": "C:/path/to/fanficlm",
    "env": {
      "LOG_LEVEL": "INFO"
    }
  }
}
```

### Apply the config

In LM Studio: **Settings → Model Context Protocol → Reload servers**

You should see `fanfic-knowledge-base` listed with a green status indicator.
If it stays red, check the MCP console for errors (usually a wrong path or missing venv).

---

## 3. Load the system prompt

In LM Studio, open a chat and set the system prompt from:

```
backend/prompts/system_scraper.txt
```

This tells the model when and how to call each tool.

---

## 4. Verify the connection

Before doing anything else, run this prompt:

```
Call list_entities with no arguments and paste the raw JSON response here.
Do not summarise or reformat it — paste the exact JSON the tool returned.
```

**Expected:** a tool-call spinner appears (1–3 s), then raw JSON like:
```json
{ "entity_count": 5, "total_vector_chunks": 128, "entities": [...] }
```

**If the model answers instantly with no spinner:** MCP is not connected.
Go back to step 2 and verify the server is green in LM Studio settings.

---

## 5. Use cases

### Single character lookup

```
Hermione Granger, Harry Potter
```

The model will call `lookup_entity` first. If not found it calls `scrape_and_store`, which fetches the Fandom wiki and embeds the result into ChromaDB.

---

### Repeat lookup (cache hit)

Run the same prompt again immediately. The model should report `cache_hit` and skip scraping — no network requests.

---

### Multiple characters, same fandom

```
Check and store the following characters from Naruto:
- Naruto Uzumaki
- Sasuke Uchiha
- Sakura Haruno
- Kakashi Hatake
```

Expect four sequential check-then-scrape cycles, one per character.

---

### Multiple characters, mixed fandoms

```
Check and store these:
- Tony Stark, MCU
- Zuko, Avatar: The Last Airbender
- Levi Ackerman, Attack on Titan
- Draco Malfoy, Harry Potter
```

---

### Non-character entities

```
Hogwarts, Harry Potter, place
```

```
The One Ring, Lord of the Rings, concept
```

Pass the entity type explicitly so the scraper and DB tag it correctly.

---

### Force re-scrape (refresh stale data)

```
Force re-scrape Tony Stark from MCU — I want the latest data.
```

The model calls `scrape_and_store` with `force: true`, bypassing the 30-day cache.

---

### Semantic search

```
Search the knowledge base for "brightest witch of her age"
```

The model calls `search_knowledge` and returns the top matching chunks. Run this after storing at least one character to verify embeddings are working.

---

### What's in the database

```
List everything currently stored in the knowledge base.
```

Returns entity count, total vector chunks, and a list of all stored entities.

---

### Fandom not specified — model should ask

```
Tell me about Sherlock Holmes.
```

The model should ask for clarification (BBC Sherlock vs. ACD canon vs. Elementary) before calling any tool. If it hallucinates directly, your system prompt is not loaded.

---

### Full cast bulk ingest

```
Store the main cast of Attack on Titan:
Eren Yeager, Mikasa Ackerman, Armin Arlert, Levi Ackerman, Erwin Smith, Historia Reiss.
```

Six sequential check+scrape cycles. Expect a summary table at the end.

---

### Obscure or missing entity

```
Store: Xandrelox the Forgotten, some obscure fandom
```

Expected: scrape fails (no wiki page), model reports the error clearly without guessing.

---

## 6. DB Explorer (standalone tool)

The DB Explorer is a separate web UI for browsing the knowledge base outside of LM Studio.

```bash
# from the project root
python tools/db_explorer.py             # opens on http://localhost:7860
python tools/db_explorer.py --port 8000
```

Features:
- **Entities tab** — browse all stored characters/places/concepts, filter by fandom or type
- **Search tab** — semantic search with cosine similarity scores
- **Detail panel** — click any entity to see its full attributes and stored vector chunks

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Model answers instantly, no spinner | MCP not connected | Verify server is green in LM Studio → Settings → MCP |
| `sentence_transformers not installed` error | Missing dependency | `pip install sentence_transformers` |
| First tool call times out | Embedding model cold start | Server pre-warms on startup — wait for "Embedding model ready." in MCP logs |
| Scrape fails for a character | Wiki page not found or rate-limited | Try again, or check `scraper_data/knowledge.db` for error details |
| Duplicate fandom spellings (e.g. `naruto` vs `Naruto`) | Case mismatch on initial scrape | Add alias to `_fandom_slug()` in `mcp_scraper/scraper.py` |
| DB Explorer shows no data | Wrong working directory | Run from the project root, not from `tools/` |
