"""
Tier 1: WritingPrompts narrative foundation (~50-60% of training data).

Loads euclaise/WritingPrompts_preferences and applies a multi-stage
quality filter.

ACTUAL SCHEMA (verified against the live dataset):
    post_text       str        body text of the prompt post (usually empty
                               for [WP], non-empty for some contest posts)
    post_title      str        the prompt itself, e.g. "[WP] 400-500 words, Power"
    post_scores     int        score of the prompt post (not the stories)
    comment_texts   list[str]  list of story responses to this prompt
    comment_scores  list[int]  parallel list of scores per story
    comment_times   list[str]  parallel list of timestamps (unused)

Each row is unrolled into N records (one per story comment), each paired
with its individual comment_score. That score is what we filter on.

Outputs JSONL with the agreed unified schema:
    {"instruction": str, "output": str, "source": "writingprompts", "meta": {...}}

Usage:
    python tier1_writingprompts.py --target-count 4000 --min-score 10 --out dataset/tier1_writingprompts.jsonl
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


# --- Filtering rules -------------------------------------------------------

META_PATTERNS = [
    re.compile(r"^\s*edit\s*[:\-]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*edit\s*\d*\s*[:\-]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bthanks?\s+for\s+(the\s+)?(prompt|gold|silver|award)", re.IGNORECASE),
    re.compile(r"\b(my\s+)?first\s+(post|attempt|try|story|writing)\b", re.IGNORECASE),
    re.compile(r"\bhere'?s?\s+my\s+(attempt|try|take|version)\b", re.IGNORECASE),
    re.compile(r"\bpart\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b(continued|to\s+be\s+continued|tbc|cont\.)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(more\s+at|check\s+out)\s+(r/|/r/|reddit\.com)", re.IGNORECASE),
    re.compile(r"^\s*(WC|word\s+count)\s*[:=]\s*\d", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bif\s+you\s+(liked|enjoyed)\s+this", re.IGNORECASE),
]

STRIP_PATTERNS = [
    (re.compile(r"\^"), ""),
    (re.compile(r"&amp;"), "&"),
    (re.compile(r"&lt;"), "<"),
    (re.compile(r"&gt;"), ">"),
    (re.compile(r"&nbsp;"), " "),
    (re.compile(r"&#x200B;"), ""),
    (re.compile(r"\r\n"), "\n"),
    (re.compile(r"\n{3,}"), "\n\n"),
]

TAG_PATTERN = re.compile(r"^\s*\[([A-Z]{2,4})\]\s*", re.IGNORECASE)


def word_count(text: str) -> int:
    return len(text.split())


def has_meta_commentary(text: str) -> bool:
    head = text[:400]
    tail = text[-400:] if len(text) > 400 else ""
    scan = head + "\n" + tail
    return any(p.search(scan) for p in META_PATTERNS)


def clean_text(text: str) -> str:
    out = text
    for pat, repl in STRIP_PATTERNS:
        out = pat.sub(repl, out)
    return out.strip()


def clean_prompt(prompt: str) -> str:
    cleaned = TAG_PATTERN.sub("", prompt).strip()
    if cleaned.isupper() and len(cleaned) > 20:
        cleaned = cleaned.capitalize()
    return cleaned


def make_instruction(prompt: str) -> str:
    templates = [
        "Write a short story based on this prompt: {p}",
        "{p}\n\nWrite a short story.",
        "Here's a writing prompt — write a short story for it:\n\n{p}",
        "Story prompt: {p}",
        "{p}",
    ]
    idx = hash(prompt) % len(templates)
    return templates[idx].format(p=prompt)


# --- Filter pipeline -------------------------------------------------------

def passes_filters(
    prompt: str,
    story: str,
    score: int | None,
    min_words: int,
    max_words: int,
    min_score: int,
) -> tuple[bool, str]:
    if score is not None and score < min_score:
        return False, f"low_score({score})"

    wc = word_count(story)
    if wc < min_words:
        return False, f"too_short({wc})"
    if wc > max_words:
        return False, f"too_long({wc})"

    if has_meta_commentary(story):
        return False, "meta_commentary"

    if "." not in story and '"' not in story:
        return False, "no_sentences"

    if word_count(prompt) < 3:
        return False, "prompt_too_short"

    return True, ""


def iter_examples(dataset) -> Iterable[tuple[str, str, int]]:
    """
    Unroll the WritingPrompts_preferences schema.

    Each dataset row is one prompt-post with many story-comments. We yield
    one (prompt, story, score) per comment, pairing comment_texts[i] with
    comment_scores[i].
    """
    for row in dataset:
        prompt = row.get("post_title") or ""
        stories = row.get("comment_texts") or []
        scores = row.get("comment_scores") or []

        if not prompt or not stories:
            continue

        # Defensive: if the arrays have mismatched lengths (shouldn't, but
        # parquet roundtripping can do odd things), pair what we can.
        n = min(len(stories), len(scores))
        for i in range(n):
            story = stories[i]
            score = scores[i]
            if story:
                yield prompt, story, score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dataset",
        default="euclaise/WritingPrompts_preferences",
    )
    ap.add_argument("--split", default="train")
    ap.add_argument(
        "--min-score",
        type=int,
        default=10,
        help="Minimum comment_score. Reddit comment scores cluster low; "
             "10 is a reasonable starting threshold. Tune via --reject-log.",
    )
    ap.add_argument("--min-words", type=int, default=600)
    ap.add_argument("--max-words", type=int, default=2500)
    ap.add_argument(
        "--target-count",
        type=int,
        default=4000,
        help="Stop after this many kept examples. 0 means keep all.",
    )
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--reject-log", type=Path, default=None)
    args = ap.parse_args()

    if load_dataset is None:
        print("ERROR: pip install datasets", file=sys.stderr)
        return 1

    print(f"Loading {args.dataset} split={args.split}...", file=sys.stderr)
    ds = load_dataset(args.dataset, split=args.split, streaming=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    reject_log = open(args.reject_log, "w", encoding="utf-8") if args.reject_log else None

    kept = 0
    seen = 0
    reasons: dict[str, int] = {}

    with open(args.out, "w", encoding="utf-8") as f:
        for prompt_raw, story_raw, score in iter_examples(ds):
            seen += 1
            if seen % 5000 == 0:
                print(f"  examples scanned={seen:,} kept={kept:,}", file=sys.stderr)

            if not prompt_raw or not story_raw:
                reasons["empty"] = reasons.get("empty", 0) + 1
                continue

            prompt = clean_prompt(prompt_raw)
            story = clean_text(story_raw)

            ok, reason = passes_filters(
                prompt, story, score, args.min_words, args.max_words, args.min_score
            )
            if not ok:
                bucket = reason.split("(")[0]
                reasons[bucket] = reasons.get(bucket, 0) + 1
                if reject_log:
                    reject_log.write(f"{reason}\t{prompt[:80]}\n")
                continue

            record = {
                "instruction": make_instruction(prompt),
                "output": story,
                "source": "writingprompts",
                "meta": {
                    "raw_prompt": prompt,
                    "word_count": word_count(story),
                    "score": score,
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1

            if args.target_count and kept >= args.target_count:
                break

    if reject_log:
        reject_log.close()

    print(f"\nDone. examples_scanned={seen:,} kept={kept:,}", file=sys.stderr)
    print(f"Output: {args.out}", file=sys.stderr)
    print("Rejection breakdown:", file=sys.stderr)
    for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {r:24s} {c:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())