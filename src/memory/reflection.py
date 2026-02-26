"""
Reflection Engine — post-trade analysis and memory updates.

Provides helper functions for the Reflection Analyst Claude teammate.
The actual reasoning is done by the Claude agent; this module handles
data I/O and memory persistence.
"""

import json
from datetime import datetime
from pathlib import Path


STATE_DIR = Path("shared_state")
LOG_DIR = Path("logs")
MEMORY_DIR = Path("memory_store")


def get_unreflected_trades() -> list[dict]:
    """Find closed trades in trade_log that haven't been reflected on yet.

    Uses memory_store/reflected_trades.json to track which trade_ids
    have already been processed.
    """
    # Load trade log
    log_path = LOG_DIR / "trade_log.json"
    if not log_path.exists():
        return []

    try:
        with open(log_path) as f:
            trade_log = json.load(f)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(trade_log, list):
        return []

    # Load already-reflected trade IDs
    reflected_path = MEMORY_DIR / "reflected_trades.json"
    reflected_ids = set()
    if reflected_path.exists():
        try:
            with open(reflected_path) as f:
                reflected_ids = set(json.load(f))
        except (json.JSONDecodeError, TypeError):
            pass

    # Find unreflected closed trades
    unreflected = []
    for trade in trade_log:
        trade_id = trade.get("order_id") or trade.get("id")
        if not trade_id:
            continue
        if trade_id in reflected_ids:
            continue
        # Only reflect on close/exit trades that have actual P&L
        if trade.get("action") in ("close_position", "exit"):
            unreflected.append(trade)

    return unreflected


def task_prepare_reflection_context(trade_record: dict, orchestrator=None) -> dict:
    """Assemble context for the Reflection Analyst to review a closed trade.

    Includes original signals, debate history (if any), and actual P&L.
    """
    trade_id = trade_record.get("order_id") or trade_record.get("id", "unknown")
    symbol = trade_record.get("symbol", "unknown")

    context = {
        "trade_id": trade_id,
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "trade_record": trade_record,
        "actual_return": trade_record.get("unrealized_pl", 0),
        "actual_return_pct": trade_record.get("unrealized_plpc", 0),
    }

    # Try to load original signals from when the trade was made
    for fname, key in [
        ("technical_signals.json", "original_signals"),
        ("sentiment_signals.json", "original_sentiment"),
        ("market_overview.json", "original_market"),
        (f"debate_{symbol}_result.json", "debate_result"),
        (f"risk_debate_{symbol}_result.json", "risk_debate_result"),
    ]:
        path = STATE_DIR / fname
        if path.exists():
            try:
                with open(path) as f:
                    context[key] = json.load(f)
            except json.JSONDecodeError:
                pass

    # Save reflection context
    STATE_DIR.mkdir(exist_ok=True)
    out_path = STATE_DIR / f"reflection_context_{trade_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2, default=str)

    return context


def task_save_reflections(trade_id: str, orchestrator) -> bool:
    """Read reflection result and save lessons to the appropriate memory banks.

    Called by Lead Agent after the Reflection Analyst teammate completes.
    """
    result_path = STATE_DIR / f"reflection_{trade_id}_result.json"
    if not result_path.exists():
        print(f"  ⚠️  No reflection result for {trade_id}")
        return False

    with open(result_path) as f:
        result = json.load(f)

    # Load the reflection context to get the situation text
    ctx_path = STATE_DIR / f"reflection_context_{trade_id}.json"
    situation = ""
    if ctx_path.exists():
        with open(ctx_path) as f:
            ctx = json.load(f)
        situation = _build_situation_summary(ctx)

    # Save lessons to each memory bank
    if result.get("lesson_bull"):
        orchestrator.bull_memory.add(situation, result["lesson_bull"])
    if result.get("lesson_bear"):
        orchestrator.bear_memory.add(situation, result["lesson_bear"])
    if result.get("lesson_judge"):
        orchestrator.research_judge_memory.add(situation, result["lesson_judge"])
    if result.get("lesson_risk"):
        orchestrator.risk_judge_memory.add(situation, result["lesson_risk"])
    if result.get("lesson_general"):
        orchestrator.decision_engine_memory.add(situation, result["lesson_general"])

    # Mark this trade as reflected
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    reflected_path = MEMORY_DIR / "reflected_trades.json"
    reflected_ids = []
    if reflected_path.exists():
        try:
            with open(reflected_path) as f:
                reflected_ids = json.load(f)
        except (json.JSONDecodeError, TypeError):
            reflected_ids = []
    reflected_ids.append(trade_id)
    with open(reflected_path, "w") as f:
        json.dump(reflected_ids, f)

    print(f"  ✅ Reflection saved for trade {trade_id} ({result.get('symbol', '?')})")
    return True


def _build_situation_summary(context: dict) -> str:
    """Build a concise situation summary for memory storage."""
    parts = [f"Symbol: {context.get('symbol', '?')}"]

    signals = context.get("original_signals", {})
    if signals:
        parts.append(f"Tech score: {signals.get('score', 'N/A')}")

    sentiment = context.get("original_sentiment", {})
    if sentiment:
        sym_sent = sentiment.get("symbols", {}).get(context.get("symbol", ""), {})
        parts.append(f"Sentiment: {sym_sent.get('sentiment', 'N/A')}")

    market = context.get("original_market", {})
    if market:
        parts.append(f"Regime: {market.get('market_regime', 'N/A')}")

    trade = context.get("trade_record", {})
    parts.append(f"Action: {trade.get('action', 'N/A')}")
    parts.append(f"Return: {context.get('actual_return_pct', 0):.1%}")

    return " | ".join(parts)
