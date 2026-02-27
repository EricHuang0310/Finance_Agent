"""BM25-based memory system for storing and retrieving financial situations.

Adapted from TradingAgents' FinancialSituationMemory. Uses BM25 for lexical
similarity matching — no API calls, no embeddings, works fully offline.
"""

import json
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi


class SituationMemory:
    """Memory bank that stores situation-lesson pairs and retrieves by BM25 similarity."""

    def __init__(self, name: str, storage_dir: str = "memory_store", max_entries: int = 500):
        self.name = name
        self.storage_dir = Path(storage_dir)
        self.max_entries = max_entries
        self.documents: list[str] = []
        self.lessons: list[str] = []
        self.bm25: Optional[BM25Okapi] = None
        self.load()

    # ── Tokenization ──────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    # ── Index management ──────────────────────────

    def _rebuild_index(self):
        if self.documents:
            tokenized = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized)
        else:
            self.bm25 = None

    def _prune(self):
        """Drop oldest entries if over max_entries limit."""
        if len(self.documents) > self.max_entries:
            excess = len(self.documents) - self.max_entries
            self.documents = self.documents[excess:]
            self.lessons = self.lessons[excess:]

    # ── Add / Search ──────────────────────────────

    def add(self, situation: str, lesson: str):
        """Store a situation-lesson pair and rebuild the index."""
        self.documents.append(situation)
        self.lessons.append(lesson)
        self._prune()
        self._rebuild_index()
        self.save()

    def add_batch(self, pairs: list[tuple[str, str]]):
        """Add multiple (situation, lesson) pairs at once."""
        for situation, lesson in pairs:
            self.documents.append(situation)
            self.lessons.append(lesson)
        self._prune()
        self._rebuild_index()
        self.save()

    def search(self, query: str, top_k: int = 2) -> list[dict]:
        """Find the most similar past situations via BM25.

        Returns list of dicts:
            [{"matched_situation": str, "lesson": str, "score": float}, ...]
        """
        if not self.documents or self.bm25 is None:
            return []

        tokens = self._tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        max_score = max(scores) if max(scores) > 0 else 1.0

        results = []
        for idx in top_indices:
            norm_score = scores[idx] / max_score if max_score > 0 else 0.0
            results.append({
                "matched_situation": self.documents[idx],
                "lesson": self.lessons[idx],
                "score": round(norm_score, 4),
            })
        return results

    # ── Persistence ───────────────────────────────

    def save(self):
        """Persist memory to JSON file."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / f"{self.name}.json"
        data = {
            "name": self.name,
            "entries": [
                {"situation": s, "lesson": l}
                for s, l in zip(self.documents, self.lessons)
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        """Load memory from JSON file if it exists."""
        path = self.storage_dir / f"{self.name}.json"
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.documents = [e["situation"] for e in data.get("entries", [])]
            self.lessons = [e["lesson"] for e in data.get("entries", [])]
            self._rebuild_index()
        except (json.JSONDecodeError, KeyError):
            pass  # Corrupted file — start fresh

    def clear(self):
        """Clear all stored memories."""
        self.documents = []
        self.lessons = []
        self.bm25 = None
        self.save()

    def __len__(self) -> int:
        return len(self.documents)

    def __repr__(self) -> str:
        return f"SituationMemory(name={self.name!r}, entries={len(self)})"
