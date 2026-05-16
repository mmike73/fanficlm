"""Test Tier 2 filter logic — no HF dependency required."""

import sys
sys.path.insert(0, "/home/claude/fiction_finetune/scripts")

from tier2_instruction_diversity import (
    adapt_sharegpt_conversation,
    looks_like_fiction_request,
    passes_length,
    word_count,
)

# --- adapt_sharegpt_conversation ---------------------------------
conv1 = [
    {"from": "human", "value": "Write a story about a wizard."},
    {"from": "gpt", "value": "Once upon a time..."},
]
assert adapt_sharegpt_conversation(conv1) == ("Write a story about a wizard.", "Once upon a time...")

# With system turn first
conv2 = [
    {"from": "system", "value": "You are helpful."},
    {"from": "user", "value": "Tell me a tale."},
    {"from": "assistant", "value": "Long ago..."},
]
assert adapt_sharegpt_conversation(conv2) == ("Tell me a tale.", "Long ago...")

# Malformed: only human turn
conv3 = [{"from": "human", "value": "Hello?"}]
assert adapt_sharegpt_conversation(conv3) is None

# Empty
assert adapt_sharegpt_conversation([]) is None
print("adapt_sharegpt_conversation: OK")

# --- looks_like_fiction_request ----------------------------------
yes = [
    "Write a short story about a haunted lighthouse.",
    "Compose a story set in 1920s Paris with a jazz pianist protagonist.",
    "Craft a tale of betrayal in a medieval kingdom.",
    "Create a short story exploring loss and memory.",
    "Write a fictional account of the first human on Mars.",
]
no = [
    "Write a Python function that sorts a list.",
    "Write an essay about climate change.",
    "Compose a haiku about autumn.",
    "Write a cover letter for a software job.",
    "Write a news article about the election.",
    "Summarize this paper about quantum physics.",
    "What is the capital of France?",
    "Tell me a joke.",  # ambiguous — currently rejected, which is fine
]
for t in yes:
    assert looks_like_fiction_request(t), f"FAILED to recognize fiction: {t!r}"
for t in no:
    assert not looks_like_fiction_request(t), f"FALSE POSITIVE: {t!r}"
print("looks_like_fiction_request: OK")

# --- passes_length ------------------------------------------------
short_text = "word " * 100   # 100 words
mid_text = "word " * 1000    # 1000 words
long_text = "word " * 3000   # 3000 words

assert not passes_length(short_text, 800, 2500)
assert passes_length(mid_text, 800, 2500)
assert not passes_length(long_text, 800, 2500)
print("passes_length: OK")

print("\nAll Tier 2 filter logic tests passed.")
