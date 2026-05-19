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

---

## 7. Model stability & two-model setup

### Why models return empty responses

LM Studio shows "This message contains no content" when the model generates zero tokens.
The three most common causes:

| Cause | Symptom | Fix |
|---|---|---|
| `max_tokens` not set | Instant empty reply | Set **Response length** in LM Studio, or add `MAX_TOKENS=2048` to `backend/.env` |
| Context window exceeded | Empty reply after long tool output | Lower context or increase **Context length** slider |
| Wrong chat template | Empty or garbled reply | Confirm the template in LM Studio matches the model family |
| Model not fully loaded | Empty reply with no error | Check GPU/CPU memory — model may have been partially evicted |

---

### LM Studio settings for stable tool calling

Open the model panel (right sidebar) and set the following before starting a scraping session.

#### Context length

Tool responses from this MCP server are verbose — each `scrape_and_store` reply can be 1–3 KB of JSON. For a bulk ingest of 6 characters the conversation can easily reach 20 K tokens.

| Model size | Recommended context |
|---|---|
| 12B (Gemma 3 12B, Mistral 12B) | 32 768 |
| 4B (Gemma 3 4B, Phi-4 mini) | 8 192 |
| 1B–2B | 4 096 |

Enable **Flash Attention** whenever you increase context beyond the model's default — it cuts memory use roughly in half.

#### GPU offload

Set **GPU Layers** to the maximum your VRAM allows (`-1` = auto in LM Studio).
Partial CPU offload causes the model to stall mid-generation, which can look like an empty response.

Minimum VRAM to keep the model fully on GPU:

| Model | VRAM (Q4_K_M) |
|---|---|
| Gemma 3 1B | ~1 GB |
| Gemma 3 4B | ~3 GB |
| Gemma 3 12B | ~8 GB |

#### Temperature and sampling

For reliable tool calling use lower temperature than you would for creative writing:

```
Temperature:   0.2   (not 0.7 — higher values cause the model to improvise tool arguments)
Top-P:         0.9
Repeat penalty: 1.05
```

After scraping is done and you switch to story generation, raise temperature back to 0.7–1.0.

#### Response length (max_tokens)

Always set this explicitly. LM Studio defaults vary by model and some default to 0 (unlimited), which causes Gemma models to emit an EOS token immediately on some prompts.

Recommended values:

| Task | max_tokens |
|---|---|
| Tool calling / scraping | 1 024 |
| Story generation | 2 048–4 096 |

This is also configurable in the backend — add to `backend/.env`:

```
MAX_TOKENS=2048
```

---

### Smaller Gemma models (3 4B, 3 1B)

The 4B and 1B models are less reliable at multi-step tool calling. Two adjustments help significantly.

#### 1. Shorten the system prompt

The full `system_scraper.txt` is ~400 tokens. Smaller models lose track of the instructions
mid-conversation. Use this condensed version instead:

```
You are a tool-calling agent. You have three tools: list_entities, lookup_entity, scrape_and_store.

Rules:
- Always call lookup_entity before scrape_and_store.
- Paste the raw JSON from every tool call verbatim. Do not summarise.
- If a tool returns an error, report it and stop.
- Never invent tool results.
```

Save it as `backend/prompts/system_scraper_small.txt` and point the model at it.

#### 2. One character at a time

Smaller models reliably handle one character per prompt. Bulk lists confuse them.
Instead of:

```
Store: Naruto, Sasuke, Sakura, Kakashi
```

Send four separate prompts:

```
Store Naruto Uzumaki, fandom Naruto.
```
```
Store Sasuke Uchiha, fandom Naruto.
```

#### 3. Confirm the chat template

Gemma 3 uses `<start_of_turn>` / `<end_of_turn>` tokens. LM Studio sets this automatically
when you load a GGUF from the official Gemma 3 release, but if you use a community re-upload,
manually select **Gemma** in the **Chat template** dropdown under the model settings.
A wrong template causes the EOS token to fire immediately, producing an empty reply.

---

### Two-model pattern: scraper + writer

Running a dedicated small model for scraping and a larger model for generation gives you the
best quality output without keeping a large model loaded all the time.

```
┌─────────────────────┐      MCP tools      ┌──────────────────────┐
│  Curator model      │ ──────────────────► │  fanfic-knowledge-   │
│  (Gemma 3 4B)       │  scrape_and_store   │  base MCP server     │
│  LM Studio chat     │  lookup_entity      │  ChromaDB + SQLite   │
└─────────────────────┘                     └──────┬───────────────┘
                                                   │  search_knowledge
                                                   ▼
                                            ┌──────────────────────┐
                                            │  Writer model        │
                                            │  (Gemma 3 12B or     │
                                            │   any larger model)  │
                                            │  backend API / chat  │
                                            └──────────────────────┘
```

#### Step 1 — Load the curator model

In LM Studio, load **Gemma 3 4B** (or any 4B–7B model).
Attach the `fanfic-knowledge-base` MCP server and load `system_scraper_small.txt` as the system prompt.
Use this session only for scraping. Keep temperature at 0.2.

#### Step 2 — Ingest your characters

```
Store Selly (Andrei Selaru), fandom romania vlogger.
```

The model calls `lookup_entity`, gets `found: false`, then calls `scrape_and_store`.
Repeat for every character you need. When you are done, close or switch away from this session.

#### Step 3 — Load the writer model

In LM Studio, open a **new chat** (or load a second LM Studio instance on a different port).
Load your larger model — **Gemma 3 12B**, Mistral, Qwen 2.5, etc.
Keep the MCP server connected so the writer can call `search_knowledge` for RAG lookups.

Use a writer system prompt, for example:

```
You are a creative fanfiction writer. Before writing any scene, call search_knowledge
to retrieve relevant facts about the characters from the knowledge base.
Use only what the tool returns — do not invent biography details.
```

#### Step 4 — Generate

```
Write a short scene where Selly is preparing for a YouTube collaboration video.
Use the knowledge base to get accurate details about him first.
```

The writer model calls `search_knowledge("Selly romania vlogger")`, gets the stored chunks,
then writes the scene grounded in those facts.

#### Running both models from the backend

If you want to automate the pipeline (curator → store → writer → generate) without
manual LM Studio sessions, run two backend instances pointing at different LM Studio ports:

```bash
# Terminal 1 — curator
LM_STUDIO_BASE_URL=http://localhost:1234/v1 \
LM_STUDIO_MODEL=gemma-3-4b \
MAX_TOKENS=1024 \
uvicorn app.main:app --port 8000

# Terminal 2 — writer
LM_STUDIO_BASE_URL=http://localhost:1234/v1 \
LM_STUDIO_MODEL=gemma-3-12b \
MAX_TOKENS=4096 \
uvicorn app.main:app --port 8001
```

Or use a single LM Studio instance and switch models between API calls — LM Studio
reloads the model automatically when you specify a different `model` field in the request.

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
| "This message contains no content" in LM Studio | `max_tokens` not set, or wrong chat template | See section 7 — set Response Length and verify chat template |
| Scraper stores the wrong character (e.g. an anime character instead of a vlogger) | Jikan/AniList fuzzy match returned a false positive | Ensure `force=true` on the next `scrape_and_store`; the fixed scraper no longer takes unverified first results |
