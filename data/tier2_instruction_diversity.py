"""
Tier 2: Instruction diversity (~20-30% of training data).

The strategy doc named OpenHermes-2.5 + Airoboros. After review I'm
recommending a stronger Tier 2 mix — see DATASET_DECISIONS.md — but
this script supports both paths.

PRIMARY (recommended):
    - Gryphe/Opus-WritingPrompts          (Claude 3 Opus stories)
    - Gryphe/ChatGPT-4o-Writing-Prompts   (GPT-4o stories, ~3,746 rows)
  Both are already ShareGPT-formatted, fiction-specific, and ship with
  rich instructions (genre + tone + character + setting specifications).

FALLBACK:
    - teknium/OpenHermes-2.5  (filter to fiction-ish rows)

Outputs the same unified schema as Tier 1:
    {"instruction": str, "output": str, "source": str, "meta": {...}}

Usage:
    # Recommended path:
    python tier2_instruction_diversity.py \
        --mode gryphe \
        --target-count 1500 \
        --out ../data/tier2_instruction_diversity.jsonl

    # OpenHermes fallback:
    python tier2_instruction_diversity.py \
        --mode openhermes \
        --target-count 1500 \
        --out ../data/tier2_instruction_diversity.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    from datasets import load_dataset
except ImportError:
    load_dataset = None


# --- Filters --------------------------------------------------------------

# Same word-count bounds as Tier 1 so the model learns one consistent length
# distribution. Tier 2 is supposed to skew toward the upper half (1000-2000
# words) per the strategy doc, hence default min is higher than Tier 1's.
DEFAULT_MIN_WORDS = 800
DEFAULT_MAX_WORDS = 2500

# Keywords that signal a fiction-writing request. Used only for OpenHermes
# filtering, since the Gryphe datasets are already pure fiction.
FICTION_KEYWORDS = [
    r"\bwrite\s+a\s+(short\s+)?(story|novella|tale|narrative|fiction|piece)\b",
    r"\bcompose\s+a\s+(story|tale|narrative)\b",
    r"\bcraft\s+a\s+(story|tale|narrative)\b",
    r"\bcreate\s+a\s+(short\s+)?(story|tale|narrative)\b",
    r"\b(fictional|fictitious)\s+(story|account|narrative)\b",
    r"\bnarrative\s+(about|of|describing)\b",
    r"\bin\s+the\s+style\s+of\b.*\b(write|tell)\b",
]
FICTION_RE = re.compile("|".join(FICTION_KEYWORDS), re.IGNORECASE)

# Anti-patterns: things that look like fiction requests but aren't.
NON_FICTION_PATTERNS = [
    re.compile(r"\b(code|function|algorithm|class|method|api|sql)\b", re.IGNORECASE),
    re.compile(r"\b(essay|report|analysis|summary|review)\s+(of|on|about)\b", re.IGNORECASE),
    re.compile(r"\bnews\s+article\b", re.IGNORECASE),
    re.compile(r"\bcover\s+letter\b", re.IGNORECASE),
    re.compile(r"\b(haiku|poem|sonnet|limerick)\b", re.IGNORECASE),
]


def word_count(text: str) -> int:
    return len(text.split())


def looks_like_fiction_request(instruction: str) -> bool:
    if not FICTION_RE.search(instruction):
        return False
    if any(p.search(instruction) for p in NON_FICTION_PATTERNS):
        return False
    return True


def passes_length(text: str, min_words: int, max_words: int) -> bool:
    wc = word_count(text)
    return min_words <= wc <= max_words


# --- Source adapters ------------------------------------------------------

def adapt_sharegpt_conversation(conv: list[dict]) -> tuple[str, str] | None:
    """
    ShareGPT format: [{"from": "human", "value": ...}, {"from": "gpt", "value": ...}, ...]
    Some variants use "user"/"assistant" or have a "system" turn.
    We extract the first human turn and the first assistant turn.
    Returns (instruction, output) or None if shape is wrong.
    """
    human, assistant = None, None
    for turn in conv:
        role = turn.get("from") or turn.get("role")
        text = turn.get("value") or turn.get("content")
        if not role or text is None:
            continue
        role_l = role.lower()
        if role_l in ("human", "user") and human is None:
            human = text
        elif role_l in ("gpt", "assistant", "model") and assistant is None:
            assistant = text
        if human is not None and assistant is not None:
            break
    if human and assistant:
        return human.strip(), assistant.strip()
    return None


def iter_gryphe(dataset_path: str, split: str = "train") -> Iterable[tuple[str, str, dict]]:
    """
    Yields (instruction, output, meta) from a Gryphe writing-prompts dataset.

    Schema (both Opus-WritingPrompts and ChatGPT-4o-Writing-Prompts):
        {"conversations": [...], "title": str, "genres": [...]}
    """
    if load_dataset is None:
        raise RuntimeError("pip install datasets")
    ds = load_dataset(dataset_path, split=split, streaming=True)
    for row in ds:
        conv = row.get("conversations")
        if not conv:
            continue
        parsed = adapt_sharegpt_conversation(conv)
        if not parsed:
            continue
        instruction, output = parsed
        meta = {
            "title": row.get("title"),
            "genres": row.get("genres"),
            "word_count": word_count(output),
        }
        yield instruction, output, meta


def iter_openhermes(split: str = "train") -> Iterable[tuple[str, str, dict]]:
    """
    Yields (instruction, output, meta) from OpenHermes-2.5.

    Schema:
        {"conversations": [{"from": "human"|"gpt", "value": ...}, ...],
         "source": str, "category": str (sometimes)}
    """
    if load_dataset is None:
        raise RuntimeError("pip install datasets")
    ds = load_dataset("teknium/OpenHermes-2.5", split=split, streaming=True)
    for row in ds:
        conv = row.get("conversations")
        if not conv:
            continue
        parsed = adapt_sharegpt_conversation(conv)
        if not parsed:
            continue
        instruction, output = parsed
        meta = {
            "openhermes_source": row.get("source"),
            "category": row.get("category"),
            "word_count": word_count(output),
        }
        yield instruction, output, meta


# --- Main pipeline --------------------------------------------------------

def run(
    mode: str,
    target_count: int,
    min_words: int,
    max_words: int,
    out_path: Path,
    filter_fiction: bool,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[str, Iterable]] = []
    if mode == "gryphe":
        # GPT-4o variant only by default. Opus variant is gated on HF as
        # "Not-For-All-Audiences" (contains NSFW content) — opt in via
        # --include-opus if your use case wants it.
        sources = [
            ("gpt4o_writingprompts", iter_gryphe("Gryphe/ChatGPT-4o-Writing-Prompts")),
        ]
    elif mode == "gryphe_with_opus":
        sources = [
            ("gpt4o_writingprompts", iter_gryphe("Gryphe/ChatGPT-4o-Writing-Prompts")),
            ("opus_writingprompts", iter_gryphe("Gryphe/Opus-WritingPrompts")),
        ]
    elif mode == "openhermes":
        sources = [("openhermes_fiction", iter_openhermes())]
    else:
        raise ValueError(f"unknown mode: {mode}")

    kept = 0
    seen = 0
    rejections: dict[str, int] = {}

    with open(out_path, "w", encoding="utf-8") as f:
        for source_name, stream in sources:
            print(f"\nProcessing source: {source_name}", file=sys.stderr)
            for instruction, output, meta in stream:
                seen += 1
                if seen % 2000 == 0:
                    print(f"  scanned={seen:,} kept={kept:,}", file=sys.stderr)

                if filter_fiction and not looks_like_fiction_request(instruction):
                    rejections["not_fiction"] = rejections.get("not_fiction", 0) + 1
                    continue

                if not passes_length(output, min_words, max_words):
                    wc = word_count(output)
                    key = "too_short" if wc < min_words else "too_long"
                    rejections[key] = rejections.get(key, 0) + 1
                    continue

                record = {
                    "instruction": instruction,
                    "output": output,
                    "source": source_name,
                    "meta": meta,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1

                if target_count and kept >= target_count:
                    break

            if target_count and kept >= target_count:
                break

    print(f"\nDone. scanned={seen:,} kept={kept:,}", file=sys.stderr)
    print(f"Output: {out_path}", file=sys.stderr)
    print("Rejection breakdown:", file=sys.stderr)
    for r, c in sorted(rejections.items(), key=lambda x: -x[1]):
        print(f"  {r:20s} {c:,}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["gryphe", "gryphe_with_opus", "openhermes"], default="gryphe")
    ap.add_argument("--target-count", type=int, default=1500)
    ap.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    ap.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--filter-fiction",
        action="store_true",
        help="Apply fiction-keyword filter. Auto-on for openhermes mode.",
    )
    args = ap.parse_args()

    if load_dataset is None:
        print("ERROR: pip install datasets", file=sys.stderr)
        return 1

    # OpenHermes is mixed-content, so always filter. Gryphe is pure fiction,
    # so don't (it would just reject good rows that don't use trigger words).
    filter_fiction = args.filter_fiction or args.mode == "openhermes"

    run(
        mode=args.mode,
        target_count=args.target_count,
        min_words=args.min_words,
        max_words=args.max_words,
        out_path=args.out,
        filter_fiction=filter_fiction,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())