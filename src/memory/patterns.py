"""Cross-session trade pattern learning (MEM-03).

Extracts recurring trade setups from closed journal entries and stores
as situation-lesson pairs in a BM25 memory bank.  Groups closed trades
by (sector, cio_stance, outcome) and (sector, order_type, outcome) tuples,
computing aggregate statistics for each group.

The ``trade_patterns`` memory bank is re-derived from the full journal on
every extraction call (idempotent) and surfaced during debate context
preparation so Bull, Bear, and Judge can reference historical patterns.
"""

import json
from collections import defaultdict
from pathlib import Path

from filelock import FileLock

from src.memory.situation_memory import SituationMemory

# ══════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════

JOURNAL_PATH = Path("logs/trade_journal.json")
JOURNAL_LOCK = Path("logs/trade_journal.json.lock")


# ══════════════════════════════════════════════
# Pattern Extraction
# ══════════════════════════════════════════════


def extract_trade_patterns(
    journal: list[dict], min_closed: int = 5
) -> list[tuple[str, str]]:
    """Extract setup patterns from closed journal entries.

    Groups closed trades by (sector, cio_stance, outcome) and optionally
    by (sector, order_type_used, outcome).  For each group with >= 2
    trades, computes average R-multiple, holding days, and composite
    score, then builds a situation-lesson tuple.

    Args:
        journal: Full list of journal entry dicts.
        min_closed: Minimum number of closed trades required before
            extraction begins (cold-start gate).

    Returns:
        List of (situation, lesson) tuples.  Empty list if fewer than
        ``min_closed`` closed trades exist.
    """
    closed = [e for e in journal if e.get("status") == "closed"]
    if len(closed) < min_closed:
        return []

    patterns: list[tuple[str, str]] = []

    # ── Group by (sector, cio_stance, outcome) ────────────
    stance_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for entry in closed:
        thesis = entry.get("entry_thesis", {})
        key = (
            thesis.get("sector", "unknown"),
            thesis.get("cio_stance", "neutral"),
            entry.get("outcome", "unknown"),
        )
        stance_groups[key].append(entry)

    for (sector, stance, outcome), trades in stance_groups.items():
        if len(trades) >= 2:
            avg_r = _safe_mean([t.get("r_multiple") for t in trades])
            avg_holding = _safe_mean(
                [t.get("holding_days", 0) for t in trades], skip_none=False
            )
            avg_score = _safe_mean(
                [
                    t.get("entry_thesis", {}).get("composite_score")
                    for t in trades
                ]
            )
            recent_symbols = ", ".join(t["symbol"] for t in trades[-3:])

            situation = (
                f"Sector={sector} CIO_stance={stance} "
                f"trades={len(trades)} outcome_pattern={outcome}"
            )
            lesson = (
                f"{outcome.upper()} pattern in {sector} during {stance} stance: "
                f"{len(trades)} trades, avg R-multiple={avg_r:.2f}, "
                f"avg holding={avg_holding:.1f} days, "
                f"avg entry score={avg_score:.2f}. "
                f"Recent symbols: {recent_symbols}"
            )
            patterns.append((situation, lesson))

    # ── Group by (sector, order_type_used, outcome) ───────
    order_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for entry in closed:
        order_type = entry.get("order_type_used")
        if not order_type:
            continue
        thesis = entry.get("entry_thesis", {})
        key = (
            thesis.get("sector", "unknown"),
            order_type,
            entry.get("outcome", "unknown"),
        )
        order_groups[key].append(entry)

    for (sector, order_type, outcome), trades in order_groups.items():
        if len(trades) >= 2:
            avg_r = _safe_mean([t.get("r_multiple") for t in trades])
            avg_holding = _safe_mean(
                [t.get("holding_days", 0) for t in trades], skip_none=False
            )
            recent_symbols = ", ".join(t["symbol"] for t in trades[-3:])

            situation = (
                f"Sector={sector} Order_type={order_type} outcome={outcome}"
            )
            lesson = (
                f"{outcome.upper()} pattern using {order_type} orders in {sector}: "
                f"{len(trades)} trades, avg R-multiple={avg_r:.2f}, "
                f"avg holding={avg_holding:.1f} days. "
                f"Recent symbols: {recent_symbols}"
            )
            patterns.append((situation, lesson))

    return patterns


# ══════════════════════════════════════════════
# Load + Extract + Store
# ══════════════════════════════════════════════


def load_and_extract_patterns(
    storage_dir: str = "memory_store", min_closed: int = 5
) -> int:
    """Load journal, extract patterns, and store in the trade_patterns memory bank.

    Patterns are re-derived from the full journal each time (idempotent).
    The existing ``trade_patterns`` bank is cleared and repopulated.

    Args:
        storage_dir: Directory for BM25 memory JSON files.
        min_closed: Minimum closed trades for extraction.

    Returns:
        Count of patterns extracted (0 if insufficient data or on error).
    """
    try:
        # Load journal under file lock (same pattern as trade_journal.py)
        with FileLock(JOURNAL_LOCK, timeout=10):
            if JOURNAL_PATH.exists():
                with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                    journal = json.load(f)
            else:
                journal = []

        patterns = extract_trade_patterns(journal, min_closed)
        if not patterns:
            return 0

        # Clear and repopulate the trade_patterns bank
        memory = SituationMemory(name="trade_patterns", storage_dir=storage_dir)
        memory.clear()
        memory.add_batch(patterns)
        return len(patterns)

    except Exception as e:
        print(f"  WARNING: Pattern extraction failed: {e}")
        return 0


# ══════════════════════════════════════════════
# Memory Bank Accessor
# ══════════════════════════════════════════════


def get_pattern_memory(storage_dir: str = "memory_store") -> SituationMemory:
    """Return a SituationMemory instance for the trade_patterns bank.

    Used by debate context preparation to search for relevant patterns.

    Args:
        storage_dir: Directory for BM25 memory JSON files.

    Returns:
        SituationMemory instance for ``trade_patterns``.
    """
    return SituationMemory(name="trade_patterns", storage_dir=storage_dir)


# ══════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════


def _safe_mean(values: list, skip_none: bool = True) -> float:
    """Compute mean of a list, optionally skipping None values.

    Args:
        values: List of numeric values (may contain None).
        skip_none: If True, filter out None before averaging.

    Returns:
        Mean value, or 0.0 if no valid values remain.
    """
    if skip_none:
        filtered = [v for v in values if v is not None]
    else:
        filtered = [v if v is not None else 0 for v in values]
    if not filtered:
        return 0.0
    return sum(filtered) / len(filtered)
