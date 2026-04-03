# Phase 3: Debate & Execution Enhancement - Research

**Researched:** 2026-04-03
**Domain:** Sector-specialized debate enrichment, intelligent order execution, cross-session pattern learning
**Confidence:** HIGH

## Summary

Phase 3 adds three capabilities to the existing trading pipeline: (1) a Sector Specialist agent that joins the Bull/Bear/Judge investment debate as a 4th voice providing supply chain and sector catalyst intelligence, (2) an Execution Strategist that recommends order types (market vs limit vs bracket) based on volatility and liquidity conditions, and (3) cross-session pattern learning that identifies recurring trade setups from the trade journal (MEM-02) and surfaces relevant lessons during analysis.

All three features extend well-established patterns from Phases 1 and 2. The Sector Specialist follows the existing debate Teammate pattern (like Bull/Bear researchers). The Execution Strategist follows the hybrid agent pattern from Phase 2 -- code for quantitative calculations, LLM for strategic reasoning. Pattern learning extends the existing BM25 `SituationMemory` system with a new memory bank for trade setup patterns extracted from the journal.

**Primary recommendation:** Implement in three work streams: (1) Sector Specialist as a Sonnet-tier Teammate in the debate flow, running in parallel with or before Bull/Bear, writing sector intelligence to `debate_context_{symbol}.json`. (2) Execution Strategist as a Haiku-tier Subagent producing `execution_plan.json` between Portfolio Strategist and Executor. (3) Pattern learning as a new `trade_patterns` memory bank populated during Reflection phase from closed journal entries.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
No locked decisions -- full Claude discretion on all Phase 3 decisions.

### Claude's Discretion (All Areas)

**Sector Specialist:**
- Agent type, model tier, spec format, data sources
- How it integrates into Bull/Bear/Judge debate flow (timing, ordering)
- What sector intelligence it provides (supply chain, rotation signals, competitive landscape)

**Execution Strategist:**
- Order type selection logic (market vs limit vs bracket vs TWAP)
- Fill quality tracking mechanism
- How execution_plan.json is consumed by Executor

**Memory Pattern Learning:**
- How to identify trade "setups" from journal entries
- Pattern recognition approach (tag-based grouping, statistical clustering, or LLM-driven)
- How to surface relevant lessons during analysis phases

### Carried from Phase 1 & 2
- **D-07/P1:** Agent specs in Chinese, in `agents/` directory
- **D-09/P1:** Hybrid communication: SendMessage + JSON files
- **D-12/P1:** Graceful degradation: new roles fail gracefully, pipeline continues
- **D-07/P2:** Hybrid agent pattern for complex roles: code for quantitative work, LLM for reasoning

### Design Guidelines (from research)
- Research recommended Sector Specialist as "supply chain + sector catalysts only" (narrow scope to avoid bloat)
- Execution Strategist is lowest priority -- current bracket orders work; this is optimization
- Memory pattern learning needs accumulated trade journal data (from Phase 2's MEM-02) to be meaningful
- Agent proliferation tax: measure cumulative latency/cost before adding all three roles

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SECT-01 | Sector Specialist agent provides deep sector intelligence during investment debate for top-N candidates | New `agents/researchers/sector_specialist.md` Teammate spec + `task_sector_specialist()` function + debate context enrichment |
| SECT-02 | Sector Specialist covers supply chain dynamics, sector rotation signals, and competitive landscape | Spec content focuses on these 3 pillars; data sourced from yfinance sector/industry info + existing fundamentals_signals.json |
| SECT-03 | Sector Specialist joins Bull/Bear/Judge debate as a 4th voice providing domain expertise | Sector Specialist runs before Bull/Bear, writes sector intelligence into debate_context; Judge reads it alongside debate arguments |
| EXEC-01 | Execution Strategist recommends order type (market, limit, bracket, TWAP) based on volatility and liquidity | New `task_execution_strategist()` hybrid function: code computes ATR/volume metrics, logic selects order type |
| EXEC-02 | Execution Strategist produces execution_plan.json consumed by Executor agent | New JSON state file with per-trade order_type, limit_price (if applicable), urgency, and rationale |
| EXEC-03 | Execution Strategist tracks estimated vs actual fill quality for learning | Extend existing slippage tracking in Executor; write fill_quality metrics to trade journal entries |
| MEM-03 | Cross-session strategy learning: pattern recognition across trades (which setups work, which fail) | New `trade_patterns` memory bank + `extract_trade_patterns()` function in reflection phase + surface patterns in debate context |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| alpaca-py | >=0.21.0 | LimitOrderRequest for limit orders | Already installed; provides all order types needed by Execution Strategist |
| rank_bm25 | >=0.2.2 | BM25 memory for pattern learning bank | Already installed; proven pattern from existing 5 memory banks |
| yfinance | >=0.2.36 | Sector/industry info for Sector Specialist | Already installed; `Ticker.info` provides sector, industry data |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | >=2.0.0 | ATR/volatility calculations for execution strategy | Already installed; reuse existing `TechnicalAnalyzer` cached data |
| numpy | >=1.24.0 | Statistical aggregation for pattern recognition | Already installed; groupby/mean operations on journal data |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BM25 for pattern matching | Embedding-based search (sentence-transformers) | BM25 is zero-dependency, offline, proven in this system; embeddings add complexity + model dependency |
| yfinance sector data | Finnhub sector classification API | yfinance is already imported; Finnhub key is optional and may not be configured |
| Rule-based order selection | LLM-driven order selection | Rules are deterministic, auditable, faster; LLM adds latency for marginal benefit on a code-first decision |

**Installation:**
```bash
# No new packages needed -- all dependencies already in requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
agents/
  researchers/
    sector_specialist.md       # NEW: Chinese spec, Teammate pattern
src/
  debate/
    helpers.py                 # MODIFY: add sector data to debate context
  execution/
    strategist.py              # NEW: hybrid code + LLM execution strategy
  memory/
    situation_memory.py        # EXISTING: unchanged
    patterns.py                # NEW: trade pattern extraction + memory bank
  journal/
    trade_journal.py           # MODIFY: add fill_quality tracking fields
config/
  settings.yaml               # MODIFY: add sector_specialist + execution config sections
```

### Pattern 1: Sector Specialist as Debate Enrichment (not 4th Debater)
**What:** Sector Specialist runs BEFORE Bull/Bear and writes sector intelligence INTO `debate_context_{symbol}.json` as a new `sector_intelligence` field. Bull, Bear, and Judge all read this enrichment. The Specialist does NOT produce its own debate argument file.
**When to use:** When adding domain expertise to an existing debate flow without increasing debate rounds.
**Why this over a 4th debater:** Adding a 4th sequential debater (Bull -> Bear -> Sector -> Judge) adds significant latency. Writing to the shared context lets all three existing debaters benefit from sector intelligence simultaneously. The Judge evaluates sector knowledge as part of existing argument quality scoring.

```python
# In task_prepare_debate_context(), after loading existing data:
sector_intelligence = _fetch_sector_intelligence(symbol, context)
context["sector_intelligence"] = sector_intelligence

# Sector intelligence structure:
{
    "sector": "Technology",
    "industry": "Semiconductors",
    "supply_chain": {
        "key_suppliers": ["TSMC (foundry)", "ASML (lithography)"],
        "supply_risks": "TSMC Q2 earnings May 15 -- moves all semis",
        "demand_signals": "Cloud capex up 25% YoY, datacenter GPU demand strong"
    },
    "sector_rotation": {
        "sector_momentum": "Technology outperforming SPY by 3.2% this month",
        "fund_flows": "positive",
        "relative_strength": 1.12
    },
    "competitive_landscape": {
        "peer_performance": {"AMD": "+5.2%", "INTC": "-2.1%", "AVGO": "+3.8%"},
        "catalyst_calendar": ["NVDA earnings May 28", "AI conference June 2"]
    }
}
```

### Pattern 2: Execution Strategist as Hybrid Code Function
**What:** A `task_execution_strategist()` function (not a Teammate) that computes order type recommendations using code-based rules on ATR, volume, and spread data. Produces `execution_plan.json` consumed by the Executor.
**When to use:** For decisions that are primarily quantitative with clear decision rules.
**Why hybrid, not pure LLM:** Order type selection is rule-based (high ATR + low volume = limit order; liquid name + normal volatility = bracket). LLM adds latency without adding reasoning value. The Executor spec is updated to read execution_plan.json.

```python
def select_order_type(trade: dict, market_data: dict) -> dict:
    """Rule-based order type selection per EXEC-01."""
    atr_pct = trade.get("atr_pct", 0)  # ATR as % of price
    avg_volume = market_data.get("avg_volume_20d", 0)
    qty = trade.get("suggested_qty", 0)
    volume_impact = qty / avg_volume if avg_volume > 0 else 1.0

    # Decision matrix
    if volume_impact >= 0.05:
        # Large relative order -- use limit to control slippage
        return {"order_type": "limit", "limit_offset_bps": 10, "urgency": "patient"}
    elif atr_pct > 0.03:
        # High volatility -- bracket with wider stops
        return {"order_type": "bracket", "stop_multiplier": 2.5, "urgency": "normal"}
    elif atr_pct < 0.01 and volume_impact < 0.001:
        # Very liquid, low vol -- market order is fine
        return {"order_type": "market", "urgency": "immediate"}
    else:
        # Default: bracket (existing behavior)
        return {"order_type": "bracket", "stop_multiplier": 2.0, "urgency": "normal"}
```

### Pattern 3: Trade Pattern Memory via Tag-Based Grouping
**What:** Extract trade "setups" from closed journal entries by grouping on entry conditions (sector, regime, technical signals at entry). Store as situation-lesson pairs in a new `trade_patterns` BM25 memory bank. Surface during debate context preparation.
**When to use:** After enough journal entries accumulate (minimum 10 closed trades).
**Why tag-based over statistical clustering:** With daily one-shot trading, closed trade volume is low (1-3 per day). Statistical clustering needs hundreds of data points. Tag-based grouping works with small datasets and produces human-readable patterns.

```python
def extract_trade_patterns(journal: list[dict]) -> list[tuple[str, str]]:
    """Extract setup patterns from closed journal entries."""
    closed = [e for e in journal if e["status"] == "closed"]
    if len(closed) < 5:
        return []  # Not enough data yet

    patterns = []
    # Group by sector + regime + outcome
    from collections import defaultdict
    groups = defaultdict(list)
    for entry in closed:
        thesis = entry.get("entry_thesis", {})
        key = (
            thesis.get("sector", "unknown"),
            thesis.get("cio_stance", "neutral"),
            entry.get("outcome", "unknown"),
        )
        groups[key].append(entry)

    for (sector, stance, outcome), trades in groups.items():
        if len(trades) >= 2:  # Need at least 2 trades to form a pattern
            avg_r = sum(t.get("r_multiple", 0) or 0 for t in trades) / len(trades)
            avg_holding = sum(t.get("holding_days", 0) for t in trades) / len(trades)
            situation = (
                f"Sector={sector} CIO_stance={stance} "
                f"trades={len(trades)} outcome_pattern={outcome}"
            )
            lesson = (
                f"{outcome.upper()} pattern in {sector} during {stance} stance: "
                f"{len(trades)} trades, avg R-multiple={avg_r:.2f}, "
                f"avg holding={avg_holding:.1f} days. "
                f"Symbols: {', '.join(t['symbol'] for t in trades[-3:])}"
            )
            patterns.append((situation, lesson))
    return patterns
```

### Anti-Patterns to Avoid
- **Sector Specialist as full Teammate debater:** Adding a 4th sequential LLM call to the debate chain adds 15-30s latency per candidate. Enriching context is faster and equally effective.
- **Execution Strategist as Opus/Sonnet agent:** This is a quantitative decision. Using an expensive LLM for "if ATR > X then limit order" wastes cost and adds latency.
- **Pattern learning without minimum data threshold:** Running pattern extraction on 2 trades produces noise, not signal. Gate on minimum closed trade count.
- **TWAP order splitting:** Alpaca's API does not natively support TWAP for retail accounts. Do not attempt to hand-roll time-sliced orders.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Order type placement | Custom HTTP calls to Alpaca | `alpaca-py` `LimitOrderRequest`, `MarketOrderRequest`, `place_bracket_order` | SDK handles authentication, error codes, order class semantics |
| Sector/industry classification | Custom sector mapping dict | `yfinance.Ticker(symbol).info["sector"]` and `info["industry"]` | Maintained mapping, covers all US equities |
| Memory search | Custom similarity algorithm | Existing `SituationMemory` with BM25 | Proven in 5 existing memory banks, offline, no API cost |
| ATR calculation | Custom ATR function | Existing `TechnicalAnalyzer.analyze()` which already computes ATR | Cached per symbol, avoids duplicate API calls |

**Key insight:** Phase 3's features are extensions of existing patterns, not new capabilities. Every component reuses existing infrastructure (BM25 memory, debate flow, Alpaca order SDK, TechnicalAnalyzer cache). The risk is in integration complexity, not in building new primitives.

## Common Pitfalls

### Pitfall 1: Sector Specialist Scope Creep
**What goes wrong:** Sector Specialist tries to be a general research analyst, duplicating Bull/Bear work with sector-flavored language instead of providing unique supply chain/catalyst intelligence.
**Why it happens:** The spec is too broad, or it lacks concrete examples of what "sector intelligence" means vs "general analysis."
**How to avoid:** Spec must explicitly state: "You provide ONLY supply chain risks, sector rotation signals, and competitive landscape. You do NOT evaluate whether to buy or sell -- that is Bull/Bear/Judge's job."
**Warning signs:** Sector Specialist output contains buy/sell recommendations or technical analysis.

### Pitfall 2: Execution Plan Ignored by Executor
**What goes wrong:** `execution_plan.json` is written but Executor continues using its existing bracket-only logic because the spec and code were not updated.
**Why it happens:** Executor spec (`agents/trader/executor.md`) and `task_execute_trades()` both hardcode bracket/market order logic.
**How to avoid:** Update BOTH the Executor spec AND `task_execute_trades()` to read `execution_plan.json`. Add a fallback: if no plan exists, use existing bracket behavior (graceful degradation per D-12).
**Warning signs:** All orders are still bracket orders after Execution Strategist is active.

### Pitfall 3: Pattern Learning Cold Start
**What goes wrong:** Pattern extraction runs on an empty or near-empty journal, producing meaningless patterns ("1 trade in Technology was a win").
**Why it happens:** MEM-03 is implemented before enough MEM-02 journal data accumulates.
**How to avoid:** Gate pattern extraction on minimum closed trade count (recommend >= 5). Return empty patterns gracefully. The feature becomes useful over time, not immediately.
**Warning signs:** Memory bank has 1-2 entries with trivially obvious "patterns."

### Pitfall 4: Limit Order Never Fills
**What goes wrong:** Execution Strategist recommends limit orders aggressively, orders expire unfilled, system misses trades entirely.
**Why it happens:** Limit offset too tight, or limit orders used for time-sensitive momentum entries where market orders are appropriate.
**How to avoid:** For momentum strategy, default to bracket orders. Use limit orders ONLY for high-volume-impact trades (qty > 1% of avg daily volume). Set time_in_force=DAY so unfilled limits expire same day.
**Warning signs:** Fill rate drops below 80% after Execution Strategist is enabled.

### Pitfall 5: Agent Proliferation Tax
**What goes wrong:** Adding Sector Specialist as a Teammate adds 15-30s per debate candidate (Top-3 = 45-90s total), pushing total pipeline time past acceptable limits.
**Why it happens:** Each Teammate spawn has LLM inference overhead.
**How to avoid:** Sector Specialist writes to context (code function), not a Teammate. Execution Strategist is a code function, not a Teammate. Only MEM-03 pattern extraction runs during Reflection (already in pipeline). Net new latency: minimal.
**Warning signs:** Pipeline time increases by more than 30s total.

## Code Examples

### Adding Sector Intelligence to Debate Context
```python
# In src/debate/helpers.py -- extend task_prepare_debate_context()
def _fetch_sector_intelligence(symbol: str, context: dict) -> dict:
    """Fetch sector-specific intelligence for debate enrichment (SECT-01/02)."""
    import yfinance as yf

    intelligence = {"symbol": symbol}

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        intelligence["sector"] = info.get("sector", "Unknown")
        intelligence["industry"] = info.get("industry", "Unknown")
        intelligence["market_cap"] = info.get("marketCap")

        # Peer comparison from same industry
        # (Limited by yfinance -- use sector from fundamentals_signals.json as backup)
        fund_path = STATE_DIR / "fundamentals_signals.json"
        if fund_path.exists():
            with open(fund_path) as f:
                fund_data = json.load(f)
            fund_sig = fund_data.get("signals", {}).get(symbol, {})
            intelligence["pe_ratio"] = fund_sig.get("pe_ratio")
            intelligence["revenue_growth"] = fund_sig.get("revenue_growth")
    except Exception as e:
        intelligence["error"] = str(e)

    # Sector rotation signal from technical data
    tech_path = STATE_DIR / "technical_signals.json"
    if tech_path.exists():
        with open(tech_path) as f:
            tech_data = json.load(f)
        # Compare symbol's trend to sector peers (if available)
        intelligence["sector_rotation_context"] = "See sector ETF comparison in market overview"

    return intelligence
```

### Execution Strategist Task Function
```python
# In src/execution/strategist.py
def task_execution_strategist(assessed: list[dict]) -> list[dict]:
    """Produce execution_plan.json with order type recommendations (EXEC-01/02)."""
    from src.agents_launcher import get_orchestrator
    from src.state_dir import get_state_dir

    orch = get_orchestrator()
    state_dir = get_state_dir()
    plans = []

    # Load market data for volume/ATR
    mkt_path = state_dir / "market_overview.json"
    market_data = {}
    if mkt_path.exists():
        with open(mkt_path) as f:
            market_data = json.load(f)

    for trade in assessed:
        if not trade.get("approved"):
            continue
        symbol = trade["symbol"]
        stock_data = market_data.get("stocks", {}).get(symbol, {})
        plan = select_order_type(trade, stock_data)
        plan["symbol"] = symbol
        plan["side"] = trade["side"]
        plan["qty"] = trade.get("suggested_qty")
        plan["entry_price"] = trade.get("entry_price")

        # For limit orders, compute limit price
        if plan["order_type"] == "limit":
            offset_bps = plan.get("limit_offset_bps", 10)
            entry = trade.get("entry_price", 0)
            if trade["side"] == "buy":
                plan["limit_price"] = round(entry * (1 - offset_bps / 10000), 2)
            else:
                plan["limit_price"] = round(entry * (1 + offset_bps / 10000), 2)

        plans.append(plan)

    result = {
        "timestamp": datetime.now().isoformat(),
        "plans": plans,
        "total_assessed": len(assessed),
        "total_planned": len(plans),
    }
    save_state_atomic(state_dir / "execution_plan.json", result)
    return assessed  # Pass through unchanged
```

### Adding Limit Order to AlpacaClient
```python
# In src/alpaca_client.py -- new method
def place_limit_order(
    self, symbol: str, qty: float, limit_price: float, side: str = "buy"
) -> dict:
    """Place a limit order with day time-in-force."""
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
    request = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        limit_price=limit_price,
        time_in_force=TimeInForce.DAY,
    )
    order = self.trading_client.submit_order(request)
    return {"id": str(order.id), "status": order.status.value}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bracket-only orders | Order type selection based on conditions | Phase 3 | Better fill quality for illiquid/volatile names |
| Generalist Bull/Bear debate | Sector-enriched debate context | Phase 3 | Debates informed by supply chain and catalyst data |
| Trade-by-trade memory | Cross-session pattern recognition | Phase 3 | System learns from accumulated trade history |

**Deprecated/outdated:**
- None -- Phase 3 extends existing patterns without deprecating anything.

## Open Questions

1. **Sector Specialist Data Depth**
   - What we know: `yfinance.Ticker.info` provides sector, industry, market cap, PE ratio. Fundamentals analyst already fetches some of this.
   - What's unclear: How much unique sector intelligence can be derived without a dedicated sector news API (e.g., Finnhub sector news)?
   - Recommendation: Start with yfinance + fundamentals_signals.json data. If insufficient, add Finnhub sector news as an optional enhancement. The LLM's training knowledge of sector dynamics (TSMC supply chain, semiconductor cycle, etc.) fills gaps.

2. **Fill Quality Tracking Granularity (EXEC-03)**
   - What we know: Executor already tracks `estimated_slippage_bps` and `actual_slippage_bps` in execution_results.json.
   - What's unclear: Whether to track fill quality per order type (bracket vs limit vs market) separately for learning.
   - Recommendation: Add `order_type_used` field to both execution_results.json and trade journal entries. Aggregate fill quality by order type in pattern learning.

3. **Pattern Learning Minimum Data**
   - What we know: Trade journal may have very few entries initially (system trades 1-3 symbols per day, not every day).
   - What's unclear: How many closed trades are needed before pattern extraction is meaningful.
   - Recommendation: Gate at >= 5 closed trades. Return empty gracefully. This feature matures over weeks of operation.

## Project Constraints (from CLAUDE.md)

- **Tech stack:** Python 3.11+, Alpaca API, Claude Code Agent Teams -- no framework changes
- **Agent specs:** Written in Chinese, in `agents/` directory
- **Communication:** Hybrid -- SendMessage for coordination, JSON files in `shared_state/` for data
- **Graceful degradation:** All new roles must fail gracefully (D-12)
- **Cost tiers:** Haiku for execution, Sonnet for analysis/debate, Opus for deep reasoning
- **No tests/linter:** No automated tests configured (per CLAUDE.md)
- **Config:** New settings go in `config/settings.yaml`; preserve existing structure
- **State files:** Use `save_state_atomic()` for all JSON writes
- **GSD workflow:** All changes go through GSD commands

## Sources

### Primary (HIGH confidence)
- **Existing codebase** -- `src/debate/helpers.py`, `src/agents_launcher.py`, `src/memory/situation_memory.py`, `src/journal/trade_journal.py`, `src/alpaca_client.py`
- **Phase 1/2 implementation** -- Established patterns for agent specs, task functions, hybrid agents, debate flow, memory banks
- **`alpaca-py` SDK** -- `LimitOrderRequest` verified available in installed version

### Secondary (MEDIUM confidence)
- **`.planning/research/FEATURES.md`** -- Sector Specialist and Execution Strategist role definitions
- **`.planning/research/SUMMARY.md`** -- Phase ordering rationale and pitfall analysis
- **yfinance sector data** -- `Ticker.info` provides sector/industry fields (verified via existing `FundamentalsAnalyzer` usage)

### Tertiary (LOW confidence)
- **Sector intelligence depth** -- Unclear how much unique intelligence yfinance alone can provide vs dedicated sector news APIs. Flagged in Open Questions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries
- Architecture: HIGH -- all three features extend proven Phase 1/2 patterns
- Pitfalls: HIGH -- pitfalls identified from direct code analysis and prior research findings

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable -- no fast-moving dependencies)
