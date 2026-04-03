"""
Debate Helper Functions
Python utilities for preparing debate context, merging results, and managing
debate state via shared_state/ JSON files.

These functions are called by Claude Agent Team teammates and the Lead agent.
"""

import json
from datetime import datetime
from pathlib import Path

from src.state_dir import get_state_dir

# yfinance is optional; Sector Specialist enrichment degrades gracefully without it.
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False


def _get_state_dir() -> Path:
    return get_state_dir()


# Lazy accessor — all references below use STATE_DIR which resolves at call time
class _LazyStateDir:
    """Proxy that resolves to the daily shared_state dir on first attribute access."""
    def __truediv__(self, other):
        return _get_state_dir() / other
    def mkdir(self, **kwargs):
        _get_state_dir().mkdir(**kwargs)
    def __str__(self):
        return str(_get_state_dir())
    def __fspath__(self):
        return str(_get_state_dir())

STATE_DIR = _LazyStateDir()


def _fetch_sector_intelligence(symbol: str, context: dict) -> dict:
    """Fetch sector-specific intelligence for debate enrichment (SECT-01/02).

    Returns a dict with sector, industry, supply chain, rotation, and
    competitive landscape data.  On any failure the dict contains an
    ``error`` key so callers can degrade gracefully (D-12).
    """
    state_dir = _get_state_dir()

    # Check for pre-computed result from task_sector_specialist
    cached_path = state_dir / f"sector_intelligence_{symbol}.json"
    if cached_path.exists():
        try:
            with open(cached_path) as f:
                return json.load(f)
        except Exception:
            pass  # Fall through to re-fetch

    try:
        intelligence: dict = {"symbol": symbol}

        # --- Core sector/industry from yfinance ---
        if _HAS_YFINANCE:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            intelligence["sector"] = info.get("sector", "Unknown")
            intelligence["industry"] = info.get("industry", "Unknown")
            intelligence["market_cap"] = info.get("marketCap")
        else:
            intelligence["sector"] = "Unknown"
            intelligence["industry"] = "Unknown"
            intelligence["market_cap"] = None

        # --- Competitive landscape from fundamentals_signals.json ---
        fund_path = state_dir / "fundamentals_signals.json"
        pe_ratio = None
        revenue_growth = None
        if fund_path.exists():
            with open(fund_path) as f:
                fund_data = json.load(f)
            fund_sig = fund_data.get("signals", {}).get(symbol, {})
            if isinstance(fund_sig, dict):
                pe_ratio = fund_sig.get("pe_ratio")
                revenue_growth = fund_sig.get("revenue_growth")

        intelligence["competitive_landscape"] = {
            "pe_ratio": pe_ratio,
            "revenue_growth": revenue_growth,
            "peer_context": (
                f"{symbol} PE={pe_ratio}, revenue_growth={revenue_growth}"
                if pe_ratio is not None
                else "Peer data not available from fundamentals"
            ),
        }

        # --- Sector rotation from technical_signals.json ---
        sector_momentum = "Data not available"
        relative_strength = None
        tech_path = state_dir / "technical_signals.json"
        if tech_path.exists():
            with open(tech_path) as f:
                tech_data = json.load(f)
            sym_tech = tech_data.get("stocks", {}).get(symbol, {})
            trend = sym_tech.get("trend", "unknown")
            score = sym_tech.get("score")
            sector_momentum = (
                f"{symbol} trend={trend}, tech_score={score}"
                if score is not None
                else f"{symbol} trend={trend}"
            )
            relative_strength = score

        intelligence["sector_rotation"] = {
            "sector_momentum": sector_momentum,
            "relative_strength": relative_strength,
        }

        # --- Supply chain context (LLM training knowledge fills gaps) ---
        market_regime = "unknown"
        mkt_path = state_dir / "market_overview.json"
        if mkt_path.exists():
            with open(mkt_path) as f:
                mkt_data = json.load(f)
            regime_data = mkt_data.get("market_regime", {})
            if isinstance(regime_data, dict):
                market_regime = regime_data.get("regime", "transitional")
            elif regime_data:
                market_regime = str(regime_data)

        intelligence["supply_chain"] = {
            "key_context": (
                f"Sector={intelligence['sector']}, "
                f"Industry={intelligence['industry']}, "
                f"Market regime={market_regime}. "
                "LLM training knowledge should fill supply chain specifics."
            ),
            "demand_signals": None,
        }

        return intelligence

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


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
        sig = tech_data.get("stocks", {}).get(symbol, {})
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
        mkt_sym = mkt_data.get("stocks", {}).get(symbol, {})
        context["market_data"] = mkt_sym
        regime_data = mkt_data.get("market_regime", {})
        if isinstance(regime_data, dict):
            context["market_regime"] = regime_data.get("regime", "transitional")
            context["regime_confidence"] = regime_data.get("regime_confidence", 0.5)
        else:
            context["market_regime"] = regime_data if regime_data else "transitional"
            context["regime_confidence"] = 0.5

    # Load fundamentals (if available)
    fund_path = STATE_DIR / "fundamentals_signals.json"
    if fund_path.exists():
        with open(fund_path) as f:
            fund_data = json.load(f)
        context["fundamentals"] = fund_data.get("signals", {}).get(symbol)

    # Enrich with sector intelligence (SECT-01/02)
    context["sector_intelligence"] = _fetch_sector_intelligence(symbol, context)

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

    # Retrieve trade pattern memories (MEM-03)
    try:
        from src.memory.patterns import get_pattern_memory
        pattern_memory = get_pattern_memory()
        context["past_memories_patterns"] = [
            m["lesson"] for m in pattern_memory.search(situation_text, top_k=3)
        ]
    except Exception:
        context["past_memories_patterns"] = []

    # Save context file
    STATE_DIR.mkdir(exist_ok=True)
    out_path = STATE_DIR / f"debate_context_{symbol}.json"
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

    regime = context.get("market_regime", "transitional")
    parts.append(f"Regime: {regime}")

    # Sector information enriches pattern matching quality (MEM-03)
    sector_intel = context.get("sector_intelligence", {})
    if sector_intel and not sector_intel.get("error"):
        parts.append(f"Sector: {sector_intel.get('sector', 'N/A')} Industry: {sector_intel.get('industry', 'N/A')}")

    return " | ".join(parts) if parts else "No data available"
