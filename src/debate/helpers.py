"""
Debate Helper Functions
Python utilities for preparing debate context, merging results, and managing
debate state via shared_state/ JSON files.

These functions are called by Claude Agent Team teammates and the Lead agent.
"""

import json
import math
from datetime import datetime
from pathlib import Path


STATE_DIR = Path("shared_state")


def task_prepare_debate_context(symbol: str, orchestrator) -> dict:
    """Assemble all signals + fundamentals + memories into debate context.

    Called by Lead Agent before spawning Bull/Bear/Judge teammates.
    """
    context = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
    }

    # Load technical signals
    tech_path = STATE_DIR / "technical_signals.json"
    if tech_path.exists():
        with open(tech_path) as f:
            tech_data = json.load(f)
        # Search in both stocks and crypto
        sig = tech_data.get("stocks", {}).get(symbol) or tech_data.get("crypto", {}).get(symbol, {})
        context["technical_signals"] = sig

    # Load sentiment signals
    sent_path = STATE_DIR / "sentiment_signals.json"
    if sent_path.exists():
        with open(sent_path) as f:
            sent_data = json.load(f)
        context["sentiment"] = sent_data.get("symbols", {}).get(symbol, {})

    # Load market overview
    mkt_path = STATE_DIR / "market_overview.json"
    if mkt_path.exists():
        with open(mkt_path) as f:
            mkt_data = json.load(f)
        mkt_sym = mkt_data.get("stocks", {}).get(symbol) or mkt_data.get("crypto", {}).get(symbol, {})
        context["market_data"] = mkt_sym
        context["market_regime"] = mkt_data.get("market_regime", "neutral")

    # Load fundamentals (if available)
    fund_path = STATE_DIR / "fundamentals_signals.json"
    if fund_path.exists():
        with open(fund_path) as f:
            fund_data = json.load(f)
        context["fundamentals"] = fund_data.get("signals", {}).get(symbol)

    # Load decision (composite score + side)
    dec_path = STATE_DIR / "decisions.json"
    if dec_path.exists():
        with open(dec_path) as f:
            dec_data = json.load(f)
        for c in dec_data.get("candidates", []):
            if c.get("symbol") == symbol or c.get("symbol") == symbol.replace("/", ""):
                context["decision"] = c
                break

    # Retrieve past memories for each debate role
    situation_text = _build_situation_text(context)
    context["past_memories_bull"] = [
        m["lesson"] for m in orchestrator.bull_memory.search(situation_text, top_k=2)
    ]
    context["past_memories_bear"] = [
        m["lesson"] for m in orchestrator.bear_memory.search(situation_text, top_k=2)
    ]
    context["past_memories_judge"] = [
        m["lesson"] for m in orchestrator.research_judge_memory.search(situation_text, top_k=2)
    ]

    # Save context file
    STATE_DIR.mkdir(exist_ok=True)
    out_path = STATE_DIR / f"debate_context_{symbol}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2, default=str)

    return context


def task_prepare_risk_context(trade: dict, orchestrator) -> dict:
    """Assemble risk debate context for a single approved trade.

    Called by Lead Agent before spawning Aggressive/Conservative/Neutral/Judge.
    """
    symbol = trade.get("symbol", "")
    context = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "trade_plan": trade,
    }

    # Portfolio state from risk manager
    risk_path = STATE_DIR / "risk_assessment.json"
    if risk_path.exists():
        with open(risk_path) as f:
            context["risk_summary"] = json.load(f).get("summary", {})

    # Load all signals for context
    for fname, key in [
        ("technical_signals.json", "technical_signals"),
        ("sentiment_signals.json", "sentiment"),
        ("market_overview.json", "market_data"),
        ("fundamentals_signals.json", "fundamentals"),
    ]:
        path = STATE_DIR / fname
        if path.exists():
            with open(path) as f:
                context[key] = json.load(f)

    # Retrieve past risk memories
    situation_text = _build_situation_text(context)
    context["past_memories_risk"] = [
        m["lesson"] for m in orchestrator.risk_judge_memory.search(situation_text, top_k=2)
    ]

    # Save context file
    out_path = STATE_DIR / f"risk_debate_context_{symbol}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2, default=str)

    return context


def task_merge_debate_results(candidates: list[dict]) -> list[dict]:
    """Merge debate score_adjustments back into candidate list.

    Reads debate_{symbol}_result.json for each candidate and applies
    the score_adjustment to composite_score.
    """
    for candidate in candidates:
        symbol = candidate.get("symbol", "")
        result_path = STATE_DIR / f"debate_{symbol}_result.json"
        if result_path.exists():
            with open(result_path) as f:
                result = json.load(f)
            adj = result.get("score_adjustment", 0)
            original = candidate.get("composite_score", 0)
            candidate["composite_score_before_debate"] = original
            candidate["composite_score"] = round(max(-1.5, min(1.5, original + adj)), 4)
            candidate["debate_adjustment"] = round(adj, 4)
            candidate["debate_confidence"] = result.get("confidence", 0)
            candidate["debate_recommendation"] = result.get("recommendation", "")
            candidate["debate_rationale"] = result.get("rationale", "")

    # Re-sort by absolute score after adjustments
    candidates.sort(key=lambda x: abs(x.get("composite_score", 0)), reverse=True)
    return candidates


def task_merge_risk_debate_results(trades: list[dict]) -> list[dict]:
    """Apply risk debate qty_ratio and adjusted stop/target to trades.

    Risk Judge can only reduce qty (qty_ratio 0.5-1.0), never increase.
    """
    for trade in trades:
        symbol = trade.get("symbol", "")
        result_path = STATE_DIR / f"risk_debate_{symbol}_result.json"
        if result_path.exists():
            with open(result_path) as f:
                result = json.load(f)

            qty_ratio = max(0.5, min(1.0, result.get("qty_ratio", 1.0)))
            original_qty = trade.get("suggested_qty", 0)
            trade["suggested_qty_before_debate"] = original_qty
            trade["suggested_qty"] = max(1, math.floor(original_qty * qty_ratio))
            trade["risk_debate_qty_ratio"] = qty_ratio
            trade["risk_debate_rationale"] = result.get("rationale", "")

            # Apply adjusted stop/target if provided
            if result.get("adjusted_stop_loss"):
                trade["stop_loss"] = result["adjusted_stop_loss"]
            if result.get("adjusted_take_profit"):
                trade["take_profit"] = result["adjusted_take_profit"]

    return trades


def _build_situation_text(context: dict) -> str:
    """Build a text representation of the current situation for memory search."""
    parts = []

    tech = context.get("technical_signals", {})
    if tech:
        parts.append(
            f"Technical: score={tech.get('score', 'N/A')} trend={tech.get('trend', 'N/A')} "
            f"RSI={tech.get('rsi', 'N/A')} MACD={tech.get('macd_signal', 'N/A')}"
        )

    sent = context.get("sentiment", {})
    if sent:
        parts.append(f"Sentiment: {sent.get('sentiment', 'N/A')} score={sent.get('score', 'N/A')}")

    mkt = context.get("market_data", {})
    if mkt:
        parts.append(f"Market: score={mkt.get('market_score', 'N/A')}")

    fund = context.get("fundamentals")
    if fund:
        parts.append(f"Fundamentals: {fund.get('summary', 'N/A')}")

    regime = context.get("market_regime", "neutral")
    parts.append(f"Regime: {regime}")

    return " | ".join(parts) if parts else "No data available"
