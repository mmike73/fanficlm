# Scraper Test Prompts — LM Studio

## How to tell if MCP tools are actually being called

If the model responds with formatted output instantly (no tool-call spinner, no latency),
it is hallucinating. Real tool calls take 1–3 seconds each and show a tool-call indicator in LM Studio.

Run **Prompt 0** first every session to verify the connection before anything else.

---

## 0. MCP connectivity check (run this first, every time)

```
Call list_entities with no arguments and paste the raw JSON response here.
Do not summarise or reformat it — paste the exact JSON the tool returned.
```

Expected: you see a tool-call indicator appear, then raw JSON like:
`{"entity_count": 5, "total_vector_chunks": 128, "entities": [...]}`

If the model responds instantly with formatted prose and no spinner → MCP is not connected.
Fix: in LM Studio, go to Settings → MCP Servers → verify the fanfic-knowledge-base server is listed and green.

---

Load `system_scraper.txt` as the system prompt in LM Studio before running any of these.
The MCP server must be running (see `lmstudio_mcp_config.json`).

Each prompt exercises the core loop: **check DB → scrape if missing → store in vector DB**.

---

## 1. Single character — unknown

```
Hermione Granger, Harry Potter
```

Expected tool calls: `lookup_entity` → not found → `scrape_and_store` → confirm chunks stored.

---

## 2. Single character — repeat (cache hit)

Run prompt 1 first, then run this immediately after:

```
Hermione Granger, Harry Potter
```

Expected: `lookup_entity` returns `found: true, cache_fresh: true` → scrape skipped.

---

## 3. List of names — same fandom

```
Check and store the following characters from Naruto:
- Naruto Uzumaki
- Sasuke Uchiha
- Sakura Haruno
- Kakashi Hatake
```

Expected: four sequential `lookup_entity` + `scrape_and_store` calls, one per character. Summary table at the end.

---

## 4. List of names — mixed fandoms

```
Check and store these:
- Tony Stark, MCU
- Zuko, Avatar: The Last Airbender
- Levi Ackerman, Attack on Titan
- Draco Malfoy, Harry Potter
```

Expected: four pairs of `lookup_entity` + `scrape_and_store`. Each should report attribute keys like backstory, personality, powers.

---

## 5. Non-character entity — place

```
Hogwarts, Harry Potter, place
```

Expected: `lookup_entity` → not found → `scrape_and_store` with `entity_type: place`.

---

## 6. Non-character entity — concept

```
The One Ring, Lord of the Rings, concept
```

Expected: `scrape_and_store` with `entity_type: concept`, chunks stored under backstory/description.

---

## 7. Force re-scrape (stale data refresh)

```
Force re-scrape Tony Stark from MCU — I want the latest data.
```

Expected: `scrape_and_store` called with `force: true`, bypassing cache check.

---

## 8. Fandom not specified — should ask

```
Tell me about Sherlock Holmes.
```

Expected: model asks for fandom clarification before calling any tool (BBC Sherlock vs. ACD canon vs. Elementary).

---

## 9. Bulk — full cast of a show

```
Store the main cast of Attack on Titan: Eren Yeager, Mikasa Ackerman, Armin Arlert, Levi Ackerman, Erwin Smith, Historia Reiss.
```

Expected: six sequential check+scrape cycles. Final summary table with all six rows.

---

## 10. What's in the database

```
List everything currently stored in the knowledge base.
```

Expected: calls `list_entities` with no filters, returns entity count and vector chunk count.

---

## 11. Verify storage with semantic search

Run after any scrape, e.g. after prompt 1:

```
Search the knowledge base for "brightest witch of her age"
```

Expected: `search_knowledge` returns chunks from Hermione's entry. Model reports results only — no added commentary.

---

## 12. Failed scrape — obscure name

```
Store: Xandrelox the Forgotten, some obscure fandom
```

Expected: `scrape_and_store` fails (no wiki page found), model reports the error clearly without guessing.

---

---

## Wattpad-popular characters (confirmed Fandom wiki pages)

These are characters from the fandoms most commonly written about on Wattpad.
Use them to verify the scraper returns rich attribute data (personality, backstory, appearance).

### 13. Twilight — main cast

```
Store these characters from Twilight:
- Edward Cullen
- Bella Swan
- Jacob Black
- Alice Cullen
```

Expected: fandom slug resolves to `twilight`, four scrape+store cycles with backstory and personality chunks.

---

### 14. The Vampire Diaries / The Originals

```
Check and store:
- Damon Salvatore, The Vampire Diaries
- Elena Gilbert, The Vampire Diaries
- Klaus Mikaelson, The Originals
- Caroline Forbes, The Vampire Diaries
```

Expected: fandom slugs `vampirediaries` and `theoriginals`, rich personality sections from the respective wikis.

---

### 15. Shadowhunters / The Mortal Instruments

```
Store these Shadowhunters characters:
- Jace Herondale
- Clary Fray
- Magnus Bane
- Alec Lightwood
```

Expected: fandom slug `shadowhunters`, chunks with powers/abilities sections (runes, warlock magic).

---

### 16. Supernatural

```
Store these characters from Supernatural:
- Dean Winchester
- Sam Winchester
- Castiel
```

Expected: fandom slug `supernatural`, detailed backstory and relationship chunks.

---

### 17. Percy Jackson

```
Store these Percy Jackson characters:
- Percy Jackson
- Annabeth Chase
- Nico di Angelo
- Luke Castellan
```

Expected: fandom slug `percyjackson`, powers sections with godly abilities.

---

### 18. Teen Wolf

```
Store the main cast of Teen Wolf:
- Scott McCall
- Stiles Stilinski
- Derek Hale
- Lydia Martin
```

Expected: fandom slug `teenwolf`, personality and backstory chunks.

---

### 19. The Hunger Games

```
Store these Hunger Games characters:
- Katniss Everdeen
- Peeta Mellark
- Finnick Odair
- Haymitch Abernathy
```

Expected: fandom slug `thehungergames`, backstory chunks with district context.

---

### 20. Maze Runner

```
Store these Maze Runner characters:
- Thomas, Maze Runner
- Newt, Maze Runner
- Teresa Agnes, Maze Runner
- Minho, Maze Runner
```

Expected: fandom slug `mazerunner`, backstory and personality data.

---

### 21. Mixed Wattpad fandoms — stress test

```
Store these characters (mixed fandoms):
- Draco Malfoy, Harry Potter
- Edward Cullen, Twilight
- Damon Salvatore, The Vampire Diaries
- Jace Herondale, Shadowhunters
- Dean Winchester, Supernatural
- Percy Jackson, Percy Jackson
```

Expected: six sequential check+scrape cycles across six different fandom wikis.
Final summary table should show entity name, fandom, chunks stored, and attribute keys.

---

## Tips

- If LM Studio calls `get_entity` instead of `lookup_entity` + `scrape_and_store`, that is also correct — `get_entity` combines both steps.
- Check `scraper_data/knowledge.db` and `scraper_data/chroma_store/` after runs to verify data was actually written.
- Set `LOG_LEVEL=DEBUG` in `lmstudio_mcp_config.json` to see per-request scraper logs in LM Studio's MCP console.
