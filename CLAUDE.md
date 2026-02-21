# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

All commands must be run from the project root (paths like `config/settings.yaml` and `shared_state/` are relative).

```bash
# Install dependencies
pip install -r requirements.txt
# Note: pyarrow is needed for backtesting but not in requirements.txt

# Run analysis only
python -m src.orchestrator

# Run analysis + execute trades (paper)
python -m src.orchestrator --trade

# Full pipeline via agents_launcher
python -m src.agents_launcher --run [--trade] [--notify]

# Show Claude Code Agent Teams prompt
python -m src.agents_launcher --prompt

# Backtest
python -m src.backtest.runner --start 2020-01-01 --end 2025-12-31 --capital 100000

# Test Telegram
python -m src.agents_launcher --test-telegram
```

There are no automated tests, linter, or formatter configured.

## Architecture

Multi-agent trading system using Alpaca API (paper/live). Strategy is **momentum/trend-following** with **one-shot execution** (no continuous monitoring).

### Pipeline (sequential phases)

```
Phase 0:   Symbol Screener        (dynamic watchlist mode only)
Phase 1:   Market + Technical + Sentiment Analysts  (parallelizable)
Phase 1.5: Position Exit Reviewer  (evaluates existing positions for close)
Phase 2:   Decision Engine         (composite scoring)
Phase 3:   Risk Manager            (veto power, not in composite score)
Phase 4:   Executor                (exits first, then new entries)
Phase 5:   Reporter                (Telegram notifications)
```

### Inter-agent Communication

Agents communicate via JSON files in `shared_state/`. Each agent writes its output file; downstream agents read from them.

### Key Design Decisions

- **Dependency injection**: `TradingOrchestrator.__init__` accepts optional `client=None`. Live/paper mode creates `AlpacaClient` internally; backtest mode injects `BacktestClient`.
- **Bar cache**: `TradingOrchestrator._bar_cache` deduplicates API calls within a single run, keyed by `(symbol, timeframe, lookback_days)`.
- **Scoring is momentum-oriented** (not mean-reversion): RSI 50-70 = bullish, BB upper = trend strength, price near 90d HIGH = positive.
- **Composite score**: `(tech * 0.35 + market * 0.20 + sentiment * 0.15) / 0.70` — risk_manager weight (0.30) is veto-only, excluded from scoring denominator.
- **Position exit**: 4 weighted criteria (trend reversal 0.35, momentum weakening 0.25, ATR trailing stop 0.25, market context 0.15). `exit_score >= 0.5` triggers close.

### Crypto Symbol Conventions

- Data API calls: `BTC/USD` (with slash)
- Order placement: `BTCUSD` (slash stripped)
- Alpaca positions: `BTCUSD` format
- `PositionReviewer` auto-converts via `_CRYPTO_BASES` set

## Configuration

- `config/.env` — API keys (Alpaca, Telegram, optional Finnhub/NewsAPI). Copy from `.env.example`.
- `config/settings.yaml` — All tunables: watchlist, screener params, scoring weights, decision thresholds, risk limits, position exit config.
- `watchlist_mode: dynamic|static` controls whether the screener (Phase 0) runs.
- `risk.kill_switch_pct` halts all trading when daily loss exceeds threshold.
- Agent specs in `agents/*.md` are written in Chinese.

## Backtest System (`src/backtest/`)

- `data_loader.py`: Fetches historical bars from Alpaca, caches as Parquet in `data/backtest_cache/`
- `client.py`: `BacktestClient` — drop-in mock for `AlpacaClient` with date-windowed serving (prevents look-ahead bias)
- `runner.py`: Iterates trading days, creates fresh `TradingOrchestrator` per day with injected `BacktestClient`
- `report.py`: Computes Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor
- Output: `logs/backtest_report.json`
- Limitations: stocks only (no crypto), no sentiment (weight=0), static watchlist mode only
