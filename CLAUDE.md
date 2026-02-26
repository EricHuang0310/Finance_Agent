# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

All commands must be run from the project root (paths like `config/settings.yaml` and `shared_state/` are relative).

```bash
# Install dependencies
pip install -r requirements.txt
# Run analysis only
python -m src.orchestrator

# Run analysis + execute trades (paper)
python -m src.orchestrator --trade

# Full pipeline via agents_launcher
python -m src.agents_launcher --run [--trade] [--notify]

# Show Claude Code Agent Teams prompt
python -m src.agents_launcher --prompt

# Test Telegram
python -m src.agents_launcher --test-telegram
```

There are no automated tests, linter, or formatter configured.

## Architecture

Multi-agent trading system using Alpaca API (paper/live). Strategy is **momentum/trend-following** with **one-shot execution** (no continuous monitoring).

Supports two modes:
- **Agent Teams mode**: Full pipeline with investment debate, risk debate, and reflection (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`)
- **Standalone mode**: Pure rule-based pipeline; debate/reflection phases are skipped, but confidence weighting and market regime detection still apply

### Pipeline (sequential phases)

```
Phase 0:   Symbol Screener                               (dynamic watchlist mode only)
Phase 1:   Market + Technical + Sentiment Analysts        (parallelizable, with confidence tracking)
Phase 1.5: Position Exit Reviewer                         (evaluates existing positions for close)
Phase 1.8: Market Regime Detection                        (SPY EMA alignment → risk_on/risk_off/neutral)
Phase 2:   Decision Engine                                (confidence-weighted + regime-adjusted scoring)
Phase 2.5: Fundamentals Fetch + Investment Debate         (Top-N only; Agent Teams mode)
Phase 3:   Risk Manager                                   (hard rules: veto power, kill switch)
Phase 3.5: Risk Debate                                    (Aggressive/Conservative/Neutral/Judge; Agent Teams mode)
Phase 4:   Executor                                       (exits first, then new entries)
Phase 5:   Reporter                                       (Telegram notifications + debate summaries)
Phase 6:   Reflection & Memory Update                     (post-trade learning; Agent Teams mode)
```

### Inter-agent Communication

Agents communicate via JSON files in `shared_state/`. Each agent writes its output file; downstream agents read from them. Debate agents follow the same pattern — each role writes its arguments/verdict to `shared_state/debate_{symbol}_*.json` or `shared_state/risk_debate_{symbol}_*.json`.

### Memory System (BM25)

Uses `rank_bm25` for lexical similarity matching across 5 memory banks:
- `bull_memory` — lessons from Bull researcher perspective
- `bear_memory` — lessons from Bear researcher perspective
- `research_judge_memory` — lessons from investment judge verdicts
- `risk_judge_memory` — lessons from risk judge verdicts
- `decision_engine_memory` — general decision lessons

Memory files persist in `memory_store/<name>.json`. Reflection (Phase 6) writes lessons back into memory after trades close.

### Investment Debate (Phase 2.5, Agent Teams only)

Only Top-N candidates (default 3) by composite score enter debate:
1. **Bull Researcher** (`agents/bull_researcher.md`) — bullish arguments
2. **Bear Researcher** (`agents/bear_researcher.md`) — bearish arguments + rebuttal
3. **Research Judge** (`agents/research_judge.md`) — verdict: BUY/SELL/HOLD + `score_adjustment` (-0.5 to +0.5)

The `score_adjustment` is added to the composite score, not a replacement.

### Risk Debate (Phase 3.5, Agent Teams only)

Only trades that pass hard risk rules enter debate:
1. **Aggressive Analyst** (`agents/aggressive_analyst.md`) — argues for larger position
2. **Conservative Analyst** (`agents/conservative_analyst.md`) — argues for smaller position
3. **Neutral Analyst** (`agents/neutral_analyst.md`) — balanced view
4. **Risk Judge** (`agents/risk_judge.md`) — verdict: `qty_ratio` (0.5-1.0), adjusted stop/target

Hard rules (kill switch, exposure limits) are non-negotiable. Debate can only reduce position size.

### Key Design Decisions

- **Bar cache**: `TradingOrchestrator._bar_cache` deduplicates API calls within a single run, keyed by `(symbol, timeframe, lookback_days)`.
- **Scoring is momentum-oriented** (not mean-reversion): RSI 50-70 = bullish, BB upper = trend strength, price near 90d HIGH = positive.
- **Composite score**: Confidence-weighted with regime-adjusted weights. Base: `tech=0.35, market=0.20, sentiment=0.15`. Risk manager weight (0.30) is veto-only, excluded from scoring denominator.
- **Market Regime**: SPY EMA20/50/200 alignment. `risk_on` boosts tech weight, `risk_off` boosts market weight.
- **Position exit**: 4 weighted criteria (trend reversal 0.35, momentum weakening 0.25, ATR trailing stop 0.25, market context 0.15). `exit_score >= 0.5` triggers close.

### Crypto Symbol Conventions

- Data API calls: `BTC/USD` (with slash)
- Order placement: `BTCUSD` (slash stripped)
- Alpaca positions: `BTCUSD` format
- `PositionReviewer` auto-converts via `_CRYPTO_BASES` set

## Configuration

- `config/.env` — API keys (Alpaca, Telegram, optional Finnhub/NewsAPI). Copy from `.env.example`.
- `config/settings.yaml` — All tunables: watchlist, screener params, scoring weights, decision thresholds, risk limits, position exit config, debate settings, memory settings.
- `watchlist_mode: dynamic|static` controls whether the screener (Phase 0) runs.
- `risk.kill_switch_pct` halts all trading when daily loss exceeds threshold.
- `debate.top_n` — number of top candidates entering investment debate (default 3).
- `debate.investment_rounds` / `debate.risk_rounds` — debate rounds per candidate.
- `memory.storage_dir` — directory for BM25 memory JSON files (default `memory_store`).
- Agent specs in `agents/*.md` are written in Chinese.
