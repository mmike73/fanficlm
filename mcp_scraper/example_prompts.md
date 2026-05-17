# Example prompts — Fanfic Knowledge Base MCP

Paste any of these into LM Studio to trigger the scraping tools.
Prompts are ordered from most to least likely to cause the LLM to call `scrape_and_store`.

---

## Universal wrapper — paste this around any request

Replace `{YOUR REQUEST}` with whatever you actually want.

```
Follow these steps exactly before answering:

STEP 1 — Identify every character, place, and concept mentioned in the request below.
STEP 2 — For each one, call lookup_entity. Note what is cached and what is missing.
STEP 3 — For anything missing or marked stale, call scrape_and_store immediately. Do not skip this.
STEP 4 — Call search_knowledge with a query that captures the core of the request, to pull the most relevant canon details.
STEP 5 — Only now write your answer, using exclusively what the tools returned. Do not supplement with training-data guesses. If the tools returned nothing, say so.

Format your answer as:
• Sources checked: [list of entities you looked up and whether they were cached or freshly scraped]
• Canon facts used: [bullet list of the key details the tools returned]
• Answer: [your actual response to the request]

Request: {YOUR REQUEST}
```

---

---

## Direct scrape requests (highest confidence)

These leave the LLM no choice but to call the tool.

- "Scrape and store everything you can find about Hermione Granger from Harry Potter."
- "Fetch the Fandom wiki page for Naruto Uzumaki and save it to the knowledge base."
- "Use scrape_and_store to get information about Tony Stark from the MCU."
- "Add Zuko from Avatar: The Last Airbender to the knowledge base, including his backstory and relationships."
- "Force re-scrape Severus Snape from Harry Potter — I want fresh data."

---

## "I need accurate detail" requests (high confidence)

Framing the request around accuracy signals the LLM should not rely on its weights.

- "I'm writing a fanfic. Before answering, look up the canon personality traits of Levi Ackerman from Attack on Titan."
- "What are Daenerys Targaryen's exact powers and relationships in canon? Check the knowledge base first, and scrape if nothing is there."
- "Give me a character sheet for Kakashi Hatake from Naruto. Use the MCP tools to get accurate information."
- "What does the wiki say about Draco Malfoy's backstory? Scrape it if you don't have it."
- "I need canon-accurate details about Wednesday Addams. Fetch them from the web."

---

## Knowledge-base-first requests (medium confidence)

These prompt a `lookup_entity` first; if the cache is empty the LLM should fall through to `scrape_and_store`.

- "Do you have anything on Sherlock Holmes from BBC Sherlock? If not, go get it."
- "Check the knowledge base for information about Edward Elric from Fullmetal Alchemist. Scrape if missing."
- "Is there anything stored about the Hogwarts houses? If not, scrape it."
- "Look up Ciri from The Witcher in the knowledge base and fill any gaps from the web."

---

## Semantic search + scrape combo (triggers search_knowledge then scrape_and_store)

- "Find all characters described as 'brooding antihero' in the knowledge base. If the base is empty, scrape a few to start."
- "Search for characters with fire-based powers. If nothing comes up, scrape Natsu Dragneel from Fairy Tail."
- "List everything in the knowledge base. If it's empty, scrape the three main characters from Attack on Titan."

---

## Bulk / world-building requests (triggers multiple scrape calls)

- "Scrape and store the four main characters from Stranger Things: Eleven, Mike, Dustin, and Lucas."
- "Build me a knowledge base entry for the entire main cast of Naruto — start with Naruto, Sasuke, and Sakura."
- "I'm writing a crossover fic. Scrape Tony Stark from MCU and L Lawliet from Death Note so I can compare their personalities."
