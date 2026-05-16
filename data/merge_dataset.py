"""
Merge Tier 1 + Tier 2 (+ optionally Tier 3) JSONLs into a single shuffled
training dataset, with optional train/eval split.

Deduplication is done on the (instruction, output) pair — exact match.
This catches accidental cross-tier overlap but won't catch near-duplicates;
that needs embeddings, which is overkill for this scale.

Usage:
    python merge_dataset.py \
        --inputs dataset/tier1_writingprompts.jsonl dataset/tier2_instruction_diversity.jsonl \
        --out-train dataset/train.jsonl \
        --out-eval dataset/eval.jsonl \
        --eval-fraction 0.05 \
        --seed 42

Single-file output (no eval split):
    python merge_dataset.py \
        --inputs dataset/tier1_writingprompts.jsonl dataset/tier2_instruction_diversity.jsonl \
        --out-train dataset/train.jsonl \
        --eval-fraction 0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path


def fingerprint(record: dict) -> str:
    """Hash (instruction, output) for dedup. Order-insensitive to whitespace."""
    inst = " ".join(record.get("instruction", "").split())
    out = " ".join(record.get("output", "").split())
    h = hashlib.sha256()
    h.update(inst.encode("utf-8"))
    h.update(b"\x1f")  # ASCII unit separator — won't appear in normal text
    h.update(out.encode("utf-8"))
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARN: skipping malformed line {i} in {path}: {e}", file=sys.stderr)
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, type=Path,
                    help="One or more tier JSONLs to merge.")
    ap.add_argument("--out-train", required=True, type=Path)
    ap.add_argument("--out-eval", type=Path, default=None,
                    help="Eval set output. Required if --eval-fraction > 0.")
    ap.add_argument("--eval-fraction", type=float, default=0.05,
                    help="Fraction of merged data to hold out for eval. 0 disables.")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for shuffling and split. Fixed for reproducibility.")
    args = ap.parse_args()

    if args.eval_fraction > 0 and args.out_eval is None:
        print("ERROR: --out-eval required when --eval-fraction > 0", file=sys.stderr)
        return 1
    if not (0 <= args.eval_fraction < 1):
        print("ERROR: --eval-fraction must be in [0, 1)", file=sys.stderr)
        return 1

    # Load all inputs
    all_records: list[dict] = []
    source_counts: Counter = Counter()
    for path in args.inputs:
        if not path.exists():
            print(f"ERROR: input not found: {path}", file=sys.stderr)
            return 1
        print(f"Loading {path}...", file=sys.stderr)
        records = load_jsonl(path)
        print(f"  loaded {len(records):,} records", file=sys.stderr)
        all_records.extend(records)
        for r in records:
            source_counts[r.get("source", "unknown")] += 1

    print(f"\nTotal loaded: {len(all_records):,}", file=sys.stderr)
    print("By source:", file=sys.stderr)
    for src, count in source_counts.most_common():
        print(f"  {src:30s} {count:,}", file=sys.stderr)

    # Dedup
    seen: set[str] = set()
    deduped: list[dict] = []
    duplicates_dropped = 0
    for r in all_records:
        fp = fingerprint(r)
        if fp in seen:
            duplicates_dropped += 1
            continue
        seen.add(fp)
        deduped.append(r)

    if duplicates_dropped:
        print(f"\nDropped {duplicates_dropped:,} exact duplicates", file=sys.stderr)
    print(f"After dedup: {len(deduped):,}", file=sys.stderr)

    # Shuffle deterministically
    rng = random.Random(args.seed)
    rng.shuffle(deduped)

    # Split
    if args.eval_fraction > 0:
        eval_n = max(1, int(len(deduped) * args.eval_fraction))
        eval_records = deduped[:eval_n]
        train_records = deduped[eval_n:]
        print(f"\nSplit (seed={args.seed}):", file=sys.stderr)
        print(f"  train: {len(train_records):,}", file=sys.stderr)
        print(f"  eval:  {len(eval_records):,}", file=sys.stderr)
        write_jsonl(args.out_train, train_records)
        write_jsonl(args.out_eval, eval_records)
        print(f"\nWrote:\n  {args.out_train}\n  {args.out_eval}", file=sys.stderr)
    else:
        train_records = deduped
        print(f"\nNo split (eval_fraction=0). All records → train.", file=sys.stderr)
        write_jsonl(args.out_train, train_records)
        print(f"\nWrote: {args.out_train}", file=sys.stderr)

    # Final breakdown by source in train set
    train_sources: Counter = Counter()
    for r in train_records:
        train_sources[r.get("source", "unknown")] += 1
    print("\nTrain set composition:", file=sys.stderr)
    for src, count in train_sources.most_common():
        pct = 100 * count / len(train_records) if train_records else 0
        print(f"  {src:30s} {count:,}  ({pct:.1f}%)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())