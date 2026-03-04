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
- **Agent Teams mode**: Full pipeline with investment debate and reflection (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`)
- **Standalone mode**: Pure rule-based pipeline; debate/reflection phases are skipped, but confidence weighting and market regime detection still apply

### Agent Directory Structure

```
agents/
├── analysts/          # Phase 0-1 data collection
│   ├── market_analyst.md
│   ├── technical_analyst.md
│   ├── sentiment_analyst.md
│   ├── fundamentals_analyst.md
│   └── symbol_screener.md
├── researchers/       # Phase 2.5 investment debate (Agent Teams only)
│   ├── bull_researcher.md
│   ├── bear_researcher.md
│   └── research_judge.md
├── risk_mgmt/         # Phase 3 risk assessment
│   └── risk_manager.md
├── trader/            # Phase 1.5, 2, 4 position management & execution
│   ├── decision_engine.md
│   ├── position_reviewer.md
│   └── executor.md
├── reporting/         # Phase 5 notifications
│   └── reporter.md
└── reflection/        # Phase 6 post-trade learning
    └── reflection_analyst.md
```

### Source Code Structure

```
src/
├── orchestrator.py              # Main pipeline, TradingOrchestrator class
│                                #   - Decision engine (generate_trade_plan)
│                                #   - Trade executor (execute_trades, execute_exits)
│                                #   - Market regime detection
│                                #   - Bar cache (_get_bars)
├── agents_launcher.py           # Agent Teams prompt + task_*() functions
├── alpaca_client.py             # Alpaca API wrapper (data + orders)
├── analysis/
│   ├── technical.py             # TechnicalAnalyzer — RSI, MACD, BB, EMA, ATR
│   ├── sentiment.py             # SentimentAnalyzer — VADER NLP + news
│   ├── screener.py              # SymbolScreener — dynamic watchlist
│   ├── position_reviewer.py     # PositionReviewer — 4-factor exit scoring
│   └── fundamentals.py          # FundamentalsAnalyzer — yfinance data
├── risk/
│   └── manager.py               # RiskManager — hard rules, position sizing, drawdown
├── notifications/
│   └── telegram.py              # TelegramNotifier — all Telegram messages
├── memory/
│   ├── situation_memory.py      # SituationMemory — BM25 memory banks
│   └── reflection.py            # Reflection helpers — lesson extraction
└── debate/
    └── helpers.py               # Debate context preparation + merge functions
```

### Pipeline (sequential phases)

```
Phase 0:   Symbol Screener           [Subagent]     (dynamic watchlist mode only)
Phase 1:   Market/Tech/Sentiment     [Subagent ×3]  (parallelizable, confidence tracking)
Phase 1.5: Position Exit Reviewer    [Subagent]     (evaluates existing positions for close)
Phase 1.8: Market Regime Detection   [Lead]         (SPY EMA alignment → risk_on/risk_off/neutral)
Phase 2:   Decision Engine           [Lead]         (confidence-weighted + regime-adjusted scoring)
Phase 2.5: Investment Debate         [Teammate ×3]  (Bull/Bear/Judge; Top-N only; Agent Teams mode)
Phase 3:   Risk Manager              [Subagent]     (hard rules: veto power, kill switch)
Phase 4:   Executor                  [Subagent]     (exits first, then new entries)
Phase 5:   Reporter                  [Subagent]     (Telegram notifications + debate summaries)
Phase 6:   Reflection                [Teammate]     (post-trade learning; Agent Teams mode)
```

### Execution Modes

- **Lead direct** — Lead agent calls `task_*()` Python functions directly. No spawn needed. (Decision Engine, Market Regime)
- **Subagent** — Agent spec (`agents/*.md`) is self-contained: includes role, scoring logic, execution code, I/O schema. Read the spec, use it as Task tool prompt. (Analysts, Screener, Exit Review, Risk Manager, Executor, Reporter)
- **Teammate** — Full independent agent with LLM reasoning. Required for debate/reflection where argumentation matters. (Bull/Bear/Research Judge, Reflection Analyst)

### Inter-agent Communication

Agents communicate via JSON files in `shared_state/YYYY-MM-DD/` (daily subfolder). The orchestrator freezes today's date in the `SHARED_STATE_DIR` env var at startup; all modules and agent subprocesses read from it via `src.state_dir.get_state_dir()`. Old daily folders are auto-cleaned after 7 days. Each agent writes its output file; downstream agents read from them. Debate agents follow the same pattern — each role writes its arguments/verdict to `{STATE_DIR}/debate_{symbol}_*.json`.

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
1. **Bull Researcher** (`agents/researchers/bull_researcher.md`) — bullish arguments
2. **Bear Researcher** (`agents/researchers/bear_researcher.md`) — bearish arguments + rebuttal
3. **Research Judge** (`agents/researchers/research_judge.md`) — verdict: BUY/SELL/HOLD + `score_adjustment` (-0.5 to +0.5)

The `score_adjustment` is added to the composite score, not a replacement.

### Key Design Decisions

- **Bar cache**: `TradingOrchestrator._bar_cache` deduplicates API calls within a single run, keyed by `(symbol, timeframe, lookback_days)`.
- **Scoring is momentum-oriented** (not mean-reversion): RSI 50-70 = bullish, BB upper = trend strength, price near 90d HIGH = positive.
- **Composite score**: Confidence-weighted with regime-adjusted weights. Base: `tech=0.35, market=0.20, sentiment=0.15`. Risk manager weight (0.30) is veto-only, excluded from scoring denominator.
- **Market Regime**: SPY EMA20/50/200 alignment. `risk_on` boosts tech weight, `risk_off` boosts market weight.
- **Position exit**: 4 weighted criteria (trend reversal 0.35, momentum weakening 0.25, ATR trailing stop 0.25, market context 0.15). `exit_score >= 0.5` triggers close.

## Configuration

- `config/.env` — API keys (Alpaca, Telegram, optional Finnhub/NewsAPI). Copy from `.env.example`.
- `config/settings.yaml` — All tunables: watchlist, screener params, scoring weights, decision thresholds, risk limits, position exit config, debate settings, memory settings.
- `watchlist_mode: dynamic|static` controls whether the screener (Phase 0) runs.
- `risk.kill_switch_pct` halts all trading when daily loss exceeds threshold.
- `debate.top_n` — number of top candidates entering investment debate (default 3).
- `debate.investment_rounds` — debate rounds per candidate.
- `memory.storage_dir` — directory for BM25 memory JSON files (default `memory_store`).
- Agent specs in `agents/{analysts,researchers,risk_mgmt,trader,reporting,reflection}/*.md` are written in Chinese. Subagent specs are self-contained (include execution code, I/O schema) and can be used directly as Task tool prompts.
- User-invocable skills in `.claude/skills/` (5 total): `run-full-pipeline`, `check-portfolio`, `run-market-analysis`, `run-position-review`, `search-memory`.
