"""Structured trade journal with lifecycle tracking (MEM-02).

Writes journal entries at two lifecycle points:
1. On fill -- captures entry thesis, signals, scoring data
2. On close -- adds exit data, P&L, R-multiple, outcome tag

Uses FileLock for concurrent safety and save_state_atomic for writes.
"""

import json
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from src.utils.state_io import save_state_atomic

# ══════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════

JOURNAL_PATH = Path("logs/trade_journal.json")
JOURNAL_LOCK = Path("logs/trade_journal.json.lock")


# ══════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════


def journal_on_fill(trade: dict, order_result: dict) -> None:
    """Write journal entry when a trade is filled.

    Args:
        trade: Trade dict with symbol, side, suggested_qty, entry_price,
               stop_loss, take_profit, composite_score, sector,
               signals_summary, risk_assessment, portfolio_correlation.
        order_result: Order result dict with id, status.
    """
    stop_loss = trade.get("stop_loss")
    entry_price = trade.get("entry_price", 0)

    initial_risk = (
        abs(entry_price - stop_loss)
        if stop_loss is not None and entry_price
        else None
    )

    entry = {
        "order_id": order_result["id"],
        "symbol": trade["symbol"],
        "side": trade["side"],
        "qty": trade.get("suggested_qty"),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": trade.get("take_profit"),
        "initial_risk": initial_risk,
        "order_type_used": trade.get("order_type_used", "bracket"),
        "estimated_fill_price": trade.get("entry_price"),
        "entry_thesis": {
            "composite_score": trade.get("composite_score"),
            "sector": trade.get("sector"),
            "signals_at_entry": trade.get("signals_summary", {}),
            "cio_stance": trade.get("risk_assessment", {}).get("cio_stance"),
            "portfolio_correlation": trade.get("portfolio_correlation"),
        },
        "filled_at": datetime.now().isoformat(),
        "status": "open",
    }
    _append_journal(entry)


def journal_on_close(candidate: dict, order_result: dict) -> None:
    """Update journal entry when a position is closed.

    Searches reversed journal for matching open entry by symbol.
    Computes P&L, R-multiple, outcome tag, and holding days.

    Args:
        candidate: Exit candidate dict with symbol, side, qty,
                   current_price, exit_reason, etc.
        order_result: Order result dict with id, status.
    """
    journal = _load_journal()

    # Find matching open entry (most recent first)
    matched = False
    for entry in reversed(journal):
        if entry["symbol"] == candidate["symbol"] and entry["status"] == "open":
            entry_price = entry["entry_price"]
            exit_price = candidate["current_price"]
            qty = entry.get("qty", 0) or 0
            direction = 1 if entry["side"] == "buy" else -1

            pnl_per_share = (exit_price - entry_price) * direction
            pnl = pnl_per_share * qty
            pnl_pct = pnl_per_share / entry_price if entry_price else 0
            initial_risk = entry.get("initial_risk")

            closed_at = datetime.now().isoformat()

            entry["exit_price"] = exit_price
            entry["exit_reason"] = candidate.get("exit_reason", "unknown")
            entry["closed_at"] = closed_at
            entry["pnl"] = round(pnl, 2)
            entry["pnl_pct"] = round(pnl_pct, 4)
            entry["r_multiple"] = (
                round(pnl_per_share / initial_risk, 2)
                if initial_risk and initial_risk > 0
                else None
            )
            entry["outcome"] = _classify_outcome(pnl_pct)
            entry["holding_days"] = _compute_holding_days(
                entry["filled_at"], closed_at
            )
            entry["status"] = "closed"
            entry["close_order_id"] = order_result["id"]
            matched = True
            break

    if not matched:
        print(
            f"  Warning: No open journal entry found for {candidate['symbol']}. "
            f"Skipping journal close."
        )
        return

    _save_journal(journal)


# ══════════════════════════════════════════════
# Outcome Classification
# ══════════════════════════════════════════════


def _classify_outcome(pnl_pct: float) -> str:
    """Win/Loss/Scratch classification per D-05.

    Args:
        pnl_pct: P&L as a decimal fraction (e.g., 0.05 = 5%).

    Returns:
        "scratch" if |pnl_pct| < 0.5%, "win" if positive, "loss" otherwise.
    """
    if abs(pnl_pct) < 0.005:
        return "scratch"
    return "win" if pnl_pct > 0 else "loss"


# ══════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════


def _compute_holding_days(filled_at: str, closed_at: str) -> int:
    """Compute holding period in days between two ISO timestamps.

    Args:
        filled_at: ISO format timestamp of entry fill.
        closed_at: ISO format timestamp of position close.

    Returns:
        Number of calendar days between fill and close.
    """
    fill_dt = datetime.fromisoformat(filled_at)
    close_dt = datetime.fromisoformat(closed_at)
    return (close_dt - fill_dt).days


def _load_journal() -> list[dict]:
    """Load trade journal from disk with FileLock.

    Returns:
        List of journal entry dicts, or empty list if file does not exist.
    """
    with FileLock(JOURNAL_LOCK, timeout=10):
        if JOURNAL_PATH.exists():
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []


def _save_journal(journal: list[dict]) -> None:
    """Save trade journal to disk atomically with FileLock.

    Args:
        journal: Full list of journal entries to write.
    """
    with FileLock(JOURNAL_LOCK, timeout=10):
        save_state_atomic(JOURNAL_PATH, journal)


def _append_journal(entry: dict) -> None:
    """Load journal, append entry, and save -- all under FileLock.

    Args:
        entry: Single journal entry dict to append.
    """
    with FileLock(JOURNAL_LOCK, timeout=10):
        journal = []
        if JOURNAL_PATH.exists():
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                journal = json.load(f)
        journal.append(entry)
        save_state_atomic(JOURNAL_PATH, journal)
