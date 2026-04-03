"""
Reflection Engine — post-trade analysis and memory updates.

Provides helper functions for the Reflection Analyst Claude teammate.
The actual reasoning is done by the Claude agent; this module handles
data I/O and memory persistence.
"""

import json
from datetime import datetime
from pathlib import Path

from src.state_dir import get_state_dir


class _LazyStateDir:
    """Proxy that resolves to the daily shared_state dir on first attribute access."""
    def __truediv__(self, other):
        return get_state_dir() / other
    def mkdir(self, **kwargs):
        get_state_dir().mkdir(**kwargs)
    def __str__(self):
        return str(get_state_dir())
    def __fspath__(self):
        return str(get_state_dir())

STATE_DIR = _LazyStateDir()
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
    if result.get("lesson_decision_engine"):
        orchestrator.decision_engine_memory.add(situation, result["lesson_decision_engine"])

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

    # Trigger pattern re-extraction from updated journal (MEM-03)
    try:
        from src.memory.patterns import load_and_extract_patterns
        pattern_count = load_and_extract_patterns()
        if pattern_count > 0:
            print(f"  📊 Extracted {pattern_count} trade patterns from journal")
    except Exception as e:
        print(f"  ⚠️  Pattern extraction failed (non-critical): {e}")

    return True


def compute_performance_attribution(trade_record: dict, original_signals: dict = None) -> dict:
    """Compute 6-dimension performance attribution for a closed trade.

    Dimensions: direction, timing, sizing, exit, execution, external
    Each dimension gets a score from -1.0 (poor) to 1.0 (good).
    """
    attribution = {
        "direction": 0.0,
        "timing": 0.0,
        "sizing": 0.0,
        "exit": 0.0,
        "execution": 0.0,
        "external": 0.0,
    }

    actual_return = trade_record.get("unrealized_plpc", 0)
    side = trade_record.get("side", "buy")

    # Direction: was the trade direction correct?
    if (side == "buy" and actual_return > 0) or (side == "sell" and actual_return < 0):
        attribution["direction"] = min(1.0, abs(actual_return) * 10)
    else:
        attribution["direction"] = -min(1.0, abs(actual_return) * 10)

    # Timing: how much of the move was captured?
    score = trade_record.get("score", 0)
    if abs(score) > 0.5 and abs(actual_return) > 0.02:
        attribution["timing"] = 0.5 if actual_return > 0 else -0.5
    else:
        attribution["timing"] = 0.0

    # Execution: slippage assessment
    slippage = trade_record.get("estimated_slippage_bps", 0)
    if slippage < 10:
        attribution["execution"] = 0.5
    elif slippage < 30:
        attribution["execution"] = 0.0
    else:
        attribution["execution"] = -0.5

    return attribution


def compute_signal_accuracy(trade_record: dict, original_signals: dict = None) -> dict:
    """Evaluate per-signal accuracy vs actual outcome."""
    accuracy = {}

    actual_return = trade_record.get("unrealized_plpc", 0)
    was_profitable = actual_return > 0

    if original_signals:
        tech_score = original_signals.get("score", 0)
        tech_predicted_buy = tech_score > 0.3
        accuracy["technical"] = {
            "predicted": "buy" if tech_predicted_buy else "sell",
            "correct": (tech_predicted_buy and was_profitable) or (not tech_predicted_buy and not was_profitable),
        }

    return accuracy


def compute_strategy_decay(trade_log_path: str = "logs/trade_log.json") -> dict:
    """Compute rolling win rate and profit factor with decay warnings."""
    log_path = Path(trade_log_path)
    if not log_path.exists():
        return {"status": "no_data"}

    try:
        with open(log_path) as f:
            trades = json.load(f)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error"}

    if len(trades) < 10:
        return {"status": "insufficient_data", "trade_count": len(trades)}

    # Rolling 20-trade window
    recent = trades[-20:]
    wins = sum(1 for t in recent if t.get("score", 0) > 0)
    win_rate = wins / len(recent)

    # Profit factor
    gains = sum(t.get("score", 0) for t in recent if t.get("score", 0) > 0)
    losses = abs(sum(t.get("score", 0) for t in recent if t.get("score", 0) < 0))
    profit_factor = gains / losses if losses > 0 else float('inf')

    # Decay flags
    decay_warnings = []
    if win_rate < 0.40:
        decay_warnings.append("Low win rate (<40%)")
    if profit_factor < 1.0:
        decay_warnings.append("Profit factor below 1.0")
    if len(trades) >= 40:
        # Compare recent 20 to prior 20
        prior = trades[-40:-20]
        prior_wins = sum(1 for t in prior if t.get("score", 0) > 0)
        prior_wr = prior_wins / len(prior)
        if win_rate < prior_wr * 0.8:
            decay_warnings.append(f"Win rate declining: {prior_wr*100:.0f}% → {win_rate*100:.0f}%")

    return {
        "status": "ok",
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "recent_trades": len(recent),
        "total_trades": len(trades),
        "decay_warnings": decay_warnings,
    }


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
        regime_data = market.get("market_regime", {})
        if isinstance(regime_data, dict):
            parts.append(f"Regime: {regime_data.get('regime', 'N/A')}")
        else:
            parts.append(f"Regime: {regime_data}")

    trade = context.get("trade_record", {})
    parts.append(f"Action: {trade.get('action', 'N/A')}")
    parts.append(f"Return: {context.get('actual_return_pct', 0):.1%}")

    return " | ".join(parts)
