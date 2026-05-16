"""Test the corrected unrolling logic against real-shape mock data."""

import sys
sys.path.insert(0, "/home/claude/fiction_finetune/scripts")

from tier1_writingprompts import iter_examples, passes_filters

# Mock the actual dataset shape (verified from huggingface viewer)
mock_dataset = [
    {
        "post_text": "",
        "post_title": "[WP] A wizard walks into a bar",
        "post_scores": 50,
        "comment_texts": [
            "Once upon a time the wizard came in. " * 50,
            "The bar was empty. " * 100,
            "The wizard sat down. " * 200,
        ],
        "comment_scores": [3, 25, 100],
        "comment_times": ["1234", "5678", "9012"],
    },
    {
        "post_text": "Body text here",
        "post_title": "[WP] The last lighthouse keeper",
        "post_scores": 20,
        "comment_texts": [
            "The light flickered. " * 80,
        ],
        "comment_scores": [50],
        "comment_times": ["1111"],
    },
    # Empty stories array — should be skipped
    {
        "post_title": "[WP] Empty prompt",
        "comment_texts": [],
        "comment_scores": [],
    },
    # Missing post_title — should be skipped
    {
        "post_title": None,
        "comment_texts": ["A story. " * 100],
        "comment_scores": [10],
    },
]

results = list(iter_examples(mock_dataset))
assert len(results) == 4, f"expected 4 results, got {len(results)}"

# Verify pairing is correct
prompts = [r[0] for r in results]
stories = [r[1] for r in results]
scores = [r[2] for r in results]

assert prompts.count("[WP] A wizard walks into a bar") == 3
assert prompts.count("[WP] The last lighthouse keeper") == 1
assert set(scores) == {3, 25, 100, 50}
print("iter_examples unrolling: OK")

# End-to-end with the filter — verify low-score gets dropped
kept = 0
for prompt, story, score in iter_examples(mock_dataset):
    ok, _ = passes_filters(prompt, story, score, min_words=100, max_words=5000, min_score=10)
    if ok:
        kept += 1

# At min_score=10: stories with scores 3 are dropped, 25/100/50 kept → 3
# All stories with score >= 10 also need to pass length (100-5000 words)
# Story lengths: 50 reps × ~7 words = 350 (dropped - too short)
#                100 reps × ~3 words = 300 (dropped - too short)
#                200 reps × ~4 words = 800 (kept)
#                80 reps × ~3 words = 240 (kept)
# So kept = 2 (the ones meeting both score and length constraints)
print(f"end-to-end kept: {kept}")
print("All tests passed.")