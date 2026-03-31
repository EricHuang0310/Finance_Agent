# External Integrations

**Analysis Date:** 2026-03-30

## APIs & External Services

**Alpaca Markets (Primary - Brokerage & Data):**
- Trading, market data, news, screening - core of the entire system
- SDK/Client: `alpaca-py` (`alpaca.trading.client.TradingClient`, `alpaca.data.historical.StockHistoricalDataClient`)
- Auth: `ALPACA_API_KEY` + `ALPACA_API_SECRET` env vars in `config/.env`
- Paper/Live toggle: `ALPACA_PAPER` env var (defaults `true`)
- Wrapper: `src/alpaca_client.py` - `AlpacaClient` class
- Endpoints used:
  - `TradingClient` - account info, positions, order placement (market + bracket), position close, clock
  - `StockHistoricalDataClient` - historical bars (1Day, 1Hour, 1Min timeframes)
  - `NewsClient` (`alpaca.data.historical.news`) - news articles by symbol
  - `ScreenerClient` (`alpaca.data.historical.screener`) - most active stocks, market movers (gainers/losers)

**Yahoo Finance (Secondary - Fundamentals & VIX):**
- Company financials, earnings calendar, VIX data, cross-asset data (TLT, UUP)
- SDK/Client: `yfinance` (imported as `yf`)
- Auth: None required (public API, rate-limited)
- Used in: `src/analysis/fundamentals.py`, `src/analysis/sentiment.py`, `src/orchestrator.py`
- Rate limiting: 2s delay between calls, exponential backoff (3 retries, 3s base) in `src/analysis/fundamentals.py`
- Data fetched: PE ratio, forward PE, PB ratio, debt-to-equity, revenue/earnings growth, FCF, market cap, ROE, operating margin, short interest, sector, earnings dates
- VIX: `^VIX` symbol for market regime detection (`config/settings.yaml` → `regime.vix_force_risk_off: 35`)

**Telegram Bot API (Notifications):**
- Trading alerts, portfolio updates, debate summaries
- SDK/Client: `httpx` (direct HTTP calls to `api.telegram.org`)
- Auth: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars in `config/.env`
- Implementation: `src/notifications/telegram.py` - `TelegramNotifier` class
- Gracefully disabled if tokens not configured (prints warning, returns `False`)
- Supports sync and async send via `httpx`

**Finnhub (Optional - Not Currently Wired):**
- Mentioned in `.env.example` as `FINNHUB_API_KEY`
- No import or usage found in current source code

**NewsAPI (Optional - Not Currently Wired):**
- Mentioned in `.env.example` as `NEWSAPI_KEY`
- No import or usage found in current source code

## Data Storage

**Databases:**
- None - No database used. All persistence is file-based JSON.

**File Storage (Local Filesystem Only):**
- `shared_state/YYYY-MM-DD/` - Daily inter-agent communication via JSON files
  - Managed by `src/state_dir.py` - `get_state_dir()` creates daily dirs, `cleanup_old_state()` prunes dirs older than 7 days
  - Files include: `technical_signals.json`, `sentiment_signals.json`, `fundamentals_signals.json`, `market_overview.json`, `risk_assessment.json`, `decisions.json`, `execution_results.json`, `exit_review.json`, `dynamic_watchlist.json`, `fundamentals_cache.json`, `debate_*.json`
- `memory_store/` - Persistent BM25 memory banks as JSON files
  - 5 banks: `bull_memory.json`, `bear_memory.json`, `research_judge_memory.json`, `risk_judge_memory.json`, `decision_engine_memory.json`
  - Managed by `src/memory/situation_memory.py` - `SituationMemory` class
  - Also `memory_store/reflected_trades.json` for tracking processed reflections
- `logs/` - Trade logs and execution logs
  - `logs/trade_log.json` - Historical trade records (read by reflection engine)

**Caching:**
- In-memory bar cache: `TradingOrchestrator._bar_cache` - deduplicates Alpaca API calls within a single run, keyed by `(symbol, timeframe, lookback_days)`
- Disk cache: `shared_state/YYYY-MM-DD/fundamentals_cache.json` - daily fundamentals cache to avoid redundant yfinance calls

## Authentication & Identity

**Auth Provider:**
- No user authentication - Single-user CLI tool
- API authentication via key/secret pairs stored in `config/.env`

## Monitoring & Observability

**Error Tracking:**
- None - No Sentry, Datadog, or similar service

**Logs:**
- `print()` statements throughout codebase (with emoji prefixes for visual scanning)
- `logs/trade_log.json` for trade history
- No structured logging framework (no `logging` module usage)

## CI/CD & Deployment

**Hosting:**
- Local machine execution only - No cloud deployment
- No Dockerfile, docker-compose, or cloud config files

**CI Pipeline:**
- None - No GitHub Actions, no CI configuration
- Not a git repository (no `.git` directory detected)

## Environment Configuration

**Required env vars (in `config/.env`):**
- `ALPACA_API_KEY` - Alpaca brokerage API key
- `ALPACA_API_SECRET` - Alpaca brokerage API secret

**Optional env vars (in `config/.env`):**
- `ALPACA_PAPER` - Paper trading mode (default: `true`)
- `TELEGRAM_BOT_TOKEN` - Telegram bot token for notifications
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications
- `FINNHUB_API_KEY` - Finnhub API key (reserved, not used)
- `NEWSAPI_KEY` - NewsAPI key (reserved, not used)

**Runtime env vars (set programmatically):**
- `SHARED_STATE_DIR` - Set by orchestrator at startup to freeze daily state directory path
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` - Must be `true` for full agent teams pipeline

**Secrets location:**
- `config/.env` file (gitignored via `.env.example` pattern)
- Template: `.env.example` at project root

## Webhooks & Callbacks

**Incoming:**
- None - No webhook endpoints (not a web server)

**Outgoing:**
- Telegram Bot API `sendMessage` - Sends trade alerts and reports via `httpx` POST to `https://api.telegram.org/bot{token}/sendMessage`

## Integration Architecture Summary

```
                    +-------------------+
                    |   Alpaca Markets  |
                    | (Trading + Data)  |
                    +--------+----------+
                             |
                    alpaca-py SDK
                             |
                    +--------v----------+
                    |  AlpacaClient     |
                    | src/alpaca_client |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v--+  +-------v----+  +------v------+
     | Technical  |  | Sentiment  |  |  Screener   |
     | Analyzer   |  | Analyzer   |  |             |
     +--------+---+  +------+-----+  +------+------+
              |             |               |
              |      +------v------+        |
              |      |  yfinance   |        |
              |      | (Yahoo Fin) |        |
              |      +-------------+        |
              |                             |
     +--------v-----------------------------v------+
     |           TradingOrchestrator               |
     |           src/orchestrator.py                |
     +-----+------------------+--------------------+
            |                  |
     +------v------+   +------v------+
     | Risk Mgr    |   |  Telegram   |
     | (local)     |   |  Bot API    |
     +-------------+   +-------------+
```

---

*Integration audit: 2026-03-30*
