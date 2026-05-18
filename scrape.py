"""
scrape.py — Direct CLI scraper. Bypasses the LLM entirely.

Usage
-----
Single entity:
    python scrape.py "Hermione Granger" "Harry Potter"
    python scrape.py "Naruto Uzumaki" naruto --type character
    python scrape.py "Diagon Alley" "Harry Potter" --type place
    python scrape.py "The One Ring" lotr --type concept
    python scrape.py "Naruto Uzumaki" naruto --force   # re-scrape even if fresh

Batch from file (one "Name | Fandom" or "Name | Fandom | type" per line, # = comment):
    python scrape.py --file characters.txt

List what is already stored:
    python scrape.py --list
    python scrape.py --list --fandom naruto
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mcp_scraper import database, vector_store, scraper
from mcp_scraper.database import is_cache_fresh


# ── Formatting helpers ─────────────────────────────────────────────────────

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✓{RESET}  {msg}")
def warn(msg):print(f"  {YELLOW}⚠{RESET}  {msg}")
def err(msg): print(f"  {RED}✗{RESET}  {msg}")
def info(msg):print(f"  {CYAN}→{RESET}  {msg}")


# ── Core scrape logic ──────────────────────────────────────────────────────

def scrape_one(name: str, fandom: str, entity_type: str = "character", force: bool = False) -> bool:
    """Scrape a single entity. Returns True on success."""
    print(f"\n{DIM}{'─'*55}{RESET}")
    print(f"  {name}  {DIM}({fandom}){RESET}")

    # Cache check
    entity = database.get_entity(name, fandom)
    if entity and is_cache_fresh(entity) and not force:
        ok(f"Already fresh in DB — last scraped {entity.last_scraped_at.strftime('%Y-%m-%d')}")
        info(f"{entity.source_url}")
        return True
    if entity and not is_cache_fresh(entity):
        warn("Cache stale — re-scraping")
    elif entity and force:
        warn("Force flag set — re-scraping")

    # Scrape
    info("Scraping…")
    result = scraper.scrape_entity(name, fandom, entity_type)

    if not result.success:
        err(f"Scrape failed: {result.error}")
        return False

    # Store in SQL
    entity_id = database.upsert_entity(result.entity)
    database.upsert_attributes(entity_id, result.attributes)

    # Re-embed in ChromaDB
    vector_store.delete_entity_chunks(name, fandom)
    chunks = scraper.make_chunks(result.entity, entity_id, result.attributes)
    vector_store.upsert_chunks(chunks)

    ok(f"Stored {len(chunks)} chunks — {', '.join(result.attributes.keys())}")
    info(f"{result.entity.source_url}")
    return True


# ── Batch from file ────────────────────────────────────────────────────────

def scrape_file(path: str, force: bool = False):
    lines = Path(path).read_text().splitlines()
    entries = []
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
        entries.append((name, fandom, etype))

    if not entries:
        err("No valid entries found in file.")
        return

    print(f"\n  Found {len(entries)} entries in {path}")
    ok_count = 0
    for name, fandom, etype in entries:
        if scrape_one(name, fandom, etype, force):
            ok_count += 1

    print(f"\n{DIM}{'─'*55}{RESET}")
    print(f"\n  Done: {GREEN}{ok_count}/{len(entries)}{RESET} scraped successfully.\n")


# ── List stored entities ───────────────────────────────────────────────────

def list_entities(fandom: str = None):
    entities = database.list_entities(fandom=fandom or None)
    chunks_total = vector_store.count()

    if not entities:
        warn("No entities in the knowledge base yet.")
        return

    col_w = [max(len(e.name) for e in entities) + 2,
             max(len(e.fandom) for e in entities) + 2, 10, 12, 8]
    col_w[0] = max(col_w[0], 6)

    header = (f"{'Name':<{col_w[0]}}{'Fandom':<{col_w[1]}}"
              f"{'Type':<{col_w[2]}}{'Scraped':<{col_w[3]}}{'Cache':<{col_w[4]}}")
    print(f"\n  {DIM}{header}{RESET}")
    print(f"  {DIM}{'─' * sum(col_w)}{RESET}")

    for e in sorted(entities, key=lambda x: (x.fandom, x.name)):
        fresh = is_cache_fresh(e)
        date  = e.last_scraped_at.strftime("%Y-%m-%d") if e.last_scraped_at else "never"
        cache = f"{GREEN}fresh{RESET}" if fresh else f"{YELLOW}stale{RESET}"
        print(f"  {e.name:<{col_w[0]}}{e.fandom:<{col_w[1]}}"
              f"{e.entity_type:<{col_w[2]}}{date:<{col_w[3]}}{cache}")

    print(f"\n  {len(entities)} entities · {chunks_total} vector chunks\n")


# ── Interactive mode ───────────────────────────────────────────────────────

def cmd_interactive():
    print(f"\n  {CYAN}Fanfic Knowledge Base — Interactive Scraper{RESET}")
    print(f"  {DIM}Type a name and fandom to scrape, or a command:{RESET}")
    print(f"  {DIM}  list          — show stored entities{RESET}")
    print(f"  {DIM}  dedup         — remove duplicates{RESET}")
    print(f"  {DIM}  quit / exit   — exit{RESET}")
    print(f"  {DIM}  Name, Fandom  — scrape a character (comma-separated){RESET}")
    print(f"  {DIM}  Name, Fandom, type  — scrape with explicit type{RESET}\n")

    while True:
        try:
            raw = input(f"  {CYAN}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye.")
            break

        if not raw:
            continue

        cmd = raw.lower()
        if cmd in ("quit", "exit", "q"):
            print("  Bye.")
            break
        if cmd == "list":
            list_entities()
            continue
        if cmd == "dedup":
            cmd_dedup()
            continue

        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 2:
            warn("Format: Name, Fandom  or  Name, Fandom, type")
            continue

        name   = parts[0]
        fandom = parts[1]
        etype  = parts[2].lower() if len(parts) > 2 else "character"
        if etype not in ("character", "place", "concept", "event"):
            warn(f"Unknown type '{etype}' — using 'character'")
            etype = "character"

        scrape_one(name, fandom, etype)
        print()


# ── Deduplication ─────────────────────────────────────────────────────────

def find_duplicates() -> list[list]:
    """Return groups of entities that share the same name (case-insensitive)."""
    entities = database.list_entities()
    by_name: dict[str, list] = {}
    for e in entities:
        key = e.name.lower().strip()
        by_name.setdefault(key, []).append(e)
    return [group for group in by_name.values() if len(group) > 1]


def cmd_dedup(yes: bool = False):
    groups = find_duplicates()
    if not groups:
        ok("No duplicates found.")
        return

    print(f"\n  Found {len(groups)} duplicate group(s):\n")
    to_delete: list[int] = []

    for group in groups:
        group_sorted = sorted(group, key=lambda e: e.last_scraped_at or __import__('datetime').datetime.min)
        print(f"  {CYAN}{group_sorted[-1].name}{RESET}")
        for i, e in enumerate(group_sorted):
            marker = f"{GREEN}keep{RESET}" if i == len(group_sorted) - 1 else f"{RED}delete{RESET}"
            date   = e.last_scraped_at.strftime("%Y-%m-%d %H:%M") if e.last_scraped_at else "never"
            print(f"    id={e.id}  fandom={e.fandom!r:<30}  scraped={date}  [{marker}]")
            if i < len(group_sorted) - 1:
                to_delete.append(e.id)
        print()

    if not to_delete:
        return

    print(f"  Will delete {len(to_delete)} older duplicate(s): ids {to_delete}")

    if not yes:
        answer = input("  Proceed? [y/N] ").strip().lower()
        if answer != "y":
            warn("Aborted.")
            return

    with database._get_conn() as conn:
        conn.execute(f"DELETE FROM entity_attributes WHERE entity_id IN ({','.join('?'*len(to_delete))})", to_delete)
        conn.execute(f"DELETE FROM entities WHERE id IN ({','.join('?'*len(to_delete))})", to_delete)

    for eid in to_delete:
        entity = next((e for g in groups for e in g if e.id == eid), None)
        if entity:
            vector_store.delete_entity_chunks(entity.name, entity.fandom)

    ok(f"Deleted {len(to_delete)} duplicate(s).")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape characters/topics directly into the knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("name",   nargs="?", help="Entity name, e.g. 'Hermione Granger'")
    parser.add_argument("fandom", nargs="?", help="Fandom, e.g. 'Harry Potter'")
    parser.add_argument("--type", default="character",
                        choices=["character", "place", "concept", "event"],
                        help="Entity type (default: character)")
    parser.add_argument("--force", action="store_true",
                        help="Re-scrape even if cached data is fresh")
    parser.add_argument("--file", metavar="PATH",
                        help="Batch file: one 'Name | Fandom [| type]' per line")
    parser.add_argument("--list", action="store_true",
                        help="List all stored entities and exit")
    parser.add_argument("--fandom", metavar="FANDOM",
                        help="Filter --list by fandom")
    parser.add_argument("--dedup", action="store_true",
                        help="Find and remove duplicate entries (same name, different fandom variant)")
    parser.add_argument("--yes", action="store_true",
                        help="Auto-confirm --dedup without prompting")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Start interactive prompt — type names to scrape one by one")

    args = parser.parse_args()
    database.init_db()

    if args.interactive:
        cmd_interactive()
        return

    if args.dedup:
        cmd_dedup(yes=args.yes)
        return

    if args.list:
        list_entities(fandom=args.fandom)
        return

    if args.file:
        scrape_file(args.file, force=args.force)
        return

    if not args.name or not args.fandom:
        parser.print_help()
        sys.exit(1)

    success = scrape_one(args.name, args.fandom, args.type, args.force)
    print()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
