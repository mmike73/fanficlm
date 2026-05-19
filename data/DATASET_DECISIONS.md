# Tier 1 & 2 — Dataset Decisions

Date: 2026-05-16

This doc captures the source choices for Tier 1 (narrative foundation) and
Tier 2 (instruction diversity) and the unified JSONL schema both tiers
emit. The strategy doc had reasonable starting suggestions but the
landscape has moved — what follows are the updated recommendations.

---

## Unified JSONL Schema (agree on this first)

Every row across all three tiers must follow this exact shape. This is the
single most important thing to lock in before either of us writes code.

```json
{
  "instruction": "Write a short story about ...",
  "output": "The lighthouse keeper hadn't seen another soul in ...",
  "source": "writingprompts",
  "meta": {
    "word_count": 1247,
    "score": 312,
    "raw_prompt": "[WP] You're the last lighthouse keeper..."
  }
}
```

**Required:** `instruction`, `output`, `source`
**Optional but recommended:** `meta` (free-form per source, useful for ablations)

Notes:
- `instruction` is the natural-language prompt the model will see
- `output` is the target completion
- `source` enables later filtering/weighting per tier
- `meta.word_count` is computed at filter time, not derived again later
- The WizardLM/USER:/ASSISTANT: chat template is applied at training time by
  the trainer, NOT baked into these fields. Keep this representation
  template-agnostic so the same files can drive both LLaMA-Factory and TRL.

---

## Tier 1 — Narrative Foundation

**Target: 3,000–5,000 examples, ~50–60% of training mix**

### Chosen source: `euclaise/WritingPrompts_preferences`

The strategy doc named `euclaise/writingprompts`. Switching to the
preferences variant. Reasons:

1. **Upvote scores are exposed as a column** (`chosen_score`). The
   original `writingprompts` doesn't expose score data directly, so the
   "apply upvote threshold where available" step in the strategy doc
   would be impossible. Preferences gives us the signal natively.
2. **It's already a chosen/rejected split** — for SFT we just take the
   `chosen` field. The same dataset becomes reusable for DPO later if you
   ever go that direction.
3. **265k rows** vs ~300k in the raw — same magnitude, much higher
   floor on quality.

The two viable alternatives, and why I didn't pick them:

| Alternative | Why not |
|---|---|
| `euclaise/writingprompts` (the doc's pick) | No score field, harder to filter |
| `euclaise/WritingPrompts_curated` | Pre-curated but smaller and we lose control over what's kept |
| `euclaise/WritingPromptsX` | Larger, but unfiltered comments-dump format requires more work |

### Filtering pipeline (`tier1_writingprompts.py`)

Five stages, applied in order:

1. **Score threshold** — drop anything with `chosen_score < 50`. The 50
   threshold is conservative; tune via `--reject-log` after the first
   run if too much is being dropped.
2. **Word count bounds** — 600 ≤ words ≤ 2500. The 600 floor is below
   the 800 target because Reddit stories often run a touch short and we
   want to retain narrative shape examples; Tier 2 supplies the upper-range
   density.
3. **Meta-commentary detection** — scans first/last 400 chars only (not
   the whole text) for "Edit:", "Thanks for the gold", "Part 1 of 3",
   etc. Edge-only scanning avoids false positives where "edit" appears
   in normal narration.
4. **Cosmetic cleanup** — strip Reddit HTML entities (`&amp;`, `&nbsp;`,
   `&#x200B;`), normalize line endings, collapse 3+ blank lines.
5. **Prompt tag stripping** — remove `[WP]`/`[EU]`/`[CW]`/etc. brackets
   so the model sees natural prose, not Reddit's tagging convention.

### Instruction wrapping

Bare Reddit prompts get wrapped in one of 5 templates, deterministically
chosen by `hash(prompt) % 5`. One of those templates is the bare prompt
itself (no wrapper) — this matters because end users sometimes paste a
prompt verbatim, and we want the model to handle that gracefully.

### Expected yield

The strategy doc estimated 15–25% survival on the raw dataset. With score
filtering on preferences, expect 40–60% survival at `min_score=50`, so
~4,000 kept rows pulls from ~7–10k scanned, which the streaming dataset
handles in minutes.

---

## Tier 2 — Instruction Diversity

**Target: 1,000–2,000 examples, ~20–30% of training mix**

### Recommendation: **swap OpenHermes + Airoboros for Gryphe writing-prompts datasets**

The strategy doc named:
- `OpenHermes-2.5` (fiction subset)
- Airoboros (story generation examples)

These are reasonable but suboptimal for our specific use case. The
better Tier 2 mix:

| Source | Rows | Notes |
|---|---|---|
| `Gryphe/Opus-WritingPrompts` | ~3,900 | Claude 3 Opus stories |
| `Gryphe/ChatGPT-4o-Writing-Prompts` | ~3,746 | GPT-4o stories |

### Why swap

| Criterion | OpenHermes + Airoboros | Gryphe writing-prompts |
|---|---|---|
| Fiction density | <5% of rows — must filter 1M to find ~50k fiction-ish | 100% — every row is fiction |
| Download size | 1.94 GB | ~50 MB each |
| Instruction richness | Mixed: many bare "write a story" prompts | Pre-enriched with title + genres + tone |
| Source quality | Variable (many sources, many models) | Single high-quality model per dataset |
| ShareGPT-ready | Yes | Yes |
| Length | Random | Targeted to 6000-8000 char range |

The killer feature of the Gryphe sets: **they were generated with rich
multi-attribute prompts** (genre, tone, character, setting), which is
exactly the "instruction diversity" property the strategy doc is asking
Tier 2 to provide. OpenHermes is broader but most of its breadth is in
non-fiction domains we don't need.

### Model-diversity bonus

Mixing Opus stories and GPT-4o stories gives the SFT mix two distinct
prose styles, which reduces the risk of the fine-tune collapsing into
one model's voice. This is a free win.

### Filtering pipeline (`tier2_instruction_diversity.py`)

For Gryphe sources:
1. Parse ShareGPT `conversations` field, extract first human + first
   assistant turn
2. Enforce word-count bounds (default 800–2500, skewing higher than
   Tier 1 per the strategy doc's length-calibration note)
3. No fiction-keyword filter (the dataset is already 100% fiction —
   filtering would just throw away good rows that don't use trigger
   words)

For OpenHermes (fallback path, kept in the script):
1. Same ShareGPT parsing
2. Word-count bounds
3. **Fiction-keyword filter** required because the dataset is mixed
4. Anti-pattern filter (rejects haiku/code/essay/etc. that contain
   fiction keywords but aren't fiction)

### License note

Gryphe datasets are listed as "license: unknown" — same as OpenHermes
2.5 (the maintainer flagged it as "FAFO license" since subsets vary).
For a fine-tuning run that isn't being publicly redistributed this is
acceptable; if the final model goes public, both teams need to
re-verify per-source licenses before release. This is true with or
without the swap, so it doesn't change the recommendation.

---

## Open Items for Coordination

1. **Schema sign-off** — does `{instruction, output, source, meta}` work
   on your colleague's side? If she needs an additional field (e.g., for
   her own dedup tracking), better to add it now than retrofit later.

2. **Tokenization sanity check** — once you have ~100 sample rows from
   each tier, tokenize a sample with the WizardLM tokenizer and verify
   none of the outputs blow past the training context window. The 2,500
   word ceiling should keep us well under 4k tokens, but verify.

3. **Storage location** — HuggingFace private repo is cleanest. The
   merged dataset will land around 100–150 MB total which is fine for
   a single HF dataset repo and means neither of you needs Git LFS.

4. **Synthetic Tier 3 generation** — separate question, but the
   Gryphe Opus dataset effectively gives us a head start on
   "synthetic high-quality stories" anchor data. May be worth checking
   if Tier 2 already covers what Tier 3 was supposed to add before
   running expensive synthetic generation.

---

## Quick Start (your side)

```bash
pip install datasets

# Tier 1
python scripts/tier1_writingprompts.py \
    --target-count 4000 \
    --out data/tier1_writingprompts.jsonl \
    --reject-log data/tier1_rejections.txt

# Tier 2 (recommended path)
python scripts/tier2_instruction_diversity.py \
    --mode gryphe \
    --target-count 1500 \
    --out data/tier2_instruction_diversity.jsonl

# Tier 2 (if you want to stick with the original strategy doc)
python scripts/tier2_instruction_diversity.py \
    --mode openhermes \
    --target-count 1500 \
    --out data/tier2_instruction_diversity.jsonl
```

Both scripts use HF streaming, so you don't need to download the full
datasets to local disk. First run end-to-end takes ~10–20 min depending
on your connection.
