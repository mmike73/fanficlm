"""
Theme detector for fanfic prompts.

Uses a DistilBERT embeddings model served by LM Studio to compute the
cosine similarity between the user's prompt and each candidate theme,
then returns the closest theme.

LM Studio exposes an OpenAI-compatible embeddings endpoint at
`POST {base_url}/embeddings`, accepting any embedding model loaded in
its "Local Server" tab (e.g. a DistilBERT sentence-embedding model
such as `sentence-transformers/distilbert-base-nli-stsb-mean-tokens`
or `distilbert-base-uncased`).
"""

from __future__ import annotations

import math
import httpx

from app.core.config import app_settings


# Each theme is described by a short natural-language sentence rather
# than a single word. Embedding similarity works far better against a
# descriptive phrase than against a bare label, because the embedding
# space encodes meaning, not lexical identity.
THEME_DESCRIPTIONS: dict[str, str] = {
    "love":    "A romantic story about love, affection, attraction and relationships.",
    "sadness": "A sad, melancholic, sorrowful story about grief, loss or heartbreak.",
    "anime":   "An anime-inspired story with Japanese pop culture, manga tropes and characters.",
    "history": "A historical story set in the past, featuring real historical events or eras.",
    "war":     "A war story about soldiers, battles, military conflict and the front line.",
    "cozy":    "A cozy, warm, comforting slice-of-life story with tea, blankets and quiet moments.",
    "royal":   "A royal story about kings, queens, princes, princesses, palaces and court intrigue.",
    "mafia":   "A mafia story about crime families, gangsters, organized crime and the underworld.",
}

DEFAULT_THEME = "cozy"  # Neutral fallback when nothing scores well.
MIN_CONFIDENCE = 0.15   # Below this, we keep the previous theme.


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class ThemeDetector:
    """Zero-shot theme classifier backed by an LM-Studio embedding model."""

    def __init__(self) -> None:
        self.base_url = app_settings.LM_STUDIO_BASE_URL
        self.model = app_settings.LM_STUDIO_EMBEDDING_MODEL
        self.timeout = app_settings.TIMEOUT
        self.labels = list(THEME_DESCRIPTIONS.keys())
        self.descriptions = [THEME_DESCRIPTIONS[lbl] for lbl in self.labels]
        # Cache the label embeddings — they never change at runtime, so
        # we only pay the embedding cost once per server start.
        self._label_vectors: list[list[float]] | None = None

    async def _embed(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        """Call LM Studio's embeddings endpoint for a batch of strings."""
        response = await client.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        # OpenAI-compatible response: { "data": [ { "embedding": [...] }, ... ] }
        return [item["embedding"] for item in data["data"]]

    async def _ensure_label_vectors(self, client: httpx.AsyncClient) -> list[list[float]]:
        if self._label_vectors is None:
            self._label_vectors = await self._embed(client, self.descriptions)
        return self._label_vectors

    async def detect(self, prompt: str) -> dict:
        """
        Return the most likely theme for the given prompt plus per-label scores.

        Response shape:
            {
                "theme": "love",
                "confidence": 0.42,
                "scores": { "love": 0.42, "sadness": 0.11, ... }
            }
        """
        prompt = (prompt or "").strip()
        if not prompt:
            return {"theme": DEFAULT_THEME, "confidence": 0.0, "scores": {}}

        async with httpx.AsyncClient() as client:
            label_vectors = await self._ensure_label_vectors(client)
            [prompt_vector] = await self._embed(client, [prompt])

        scores = {
            label: _cosine(prompt_vector, vec)
            for label, vec in zip(self.labels, label_vectors)
        }
        best_label = max(scores, key=scores.get)
        best_score = scores[best_label]

        if best_score < MIN_CONFIDENCE:
            best_label = DEFAULT_THEME

        return {
            "theme": best_label,
            "confidence": round(best_score, 4),
            "scores": {k: round(v, 4) for k, v in scores.items()},
        }