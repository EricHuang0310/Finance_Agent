# Technology Stack

**Analysis Date:** 2026-03-30

## Languages

**Primary:**
- Python 3.11+ - All trading logic, orchestration, analysis, and agent task functions (`src/`)
- Uses `zoneinfo.ZoneInfo` (stdlib 3.9+), type hints with `list[dict]` syntax (3.9+), and `match` is not used but f-strings and walrus are

**Secondary:**
- JavaScript (Node.js) - Presentation generation only (`create_presentation.js`)
- Markdown - Agent specification files (`agents/**/*.md`, written in Chinese)

## Runtime

**Environment:**
- Python 3.11+ (inferred from `zoneinfo` usage in `src/orchestrator.py`, `src/analysis/sentiment.py`)
- Node.js (for `create_presentation.js` only, not core trading)

**Package Manager:**
- pip - Python dependencies via `requirements.txt`
- npm - JS dependencies via `package.json` / `package-lock.json`
- Lockfile: `package-lock.json` present for JS; no `pip` lockfile (no `requirements.lock` or `poetry.lock`)

## Frameworks

**Core:**
- No web framework - This is a CLI pipeline, not a web app
- Claude Code Agent Teams - Multi-agent orchestration framework (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true` env var)

**Testing:**
- None configured - No test framework, linter, or formatter (per `CLAUDE.md`)

**Build/Dev:**
- No build system - Direct `python -m` execution
- Entry points: `python -m src.orchestrator` and `python -m src.agents_launcher`

## Key Dependencies

**Critical (Python - `requirements.txt`):**
- `alpaca-py>=0.21.0` - Primary brokerage API SDK for market data, trading, screening (`src/alpaca_client.py`)
- `pandas>=2.0.0` - DataFrame operations for bar data, technical analysis (`src/analysis/technical.py`, `src/analysis/screener.py`)
- `numpy>=1.24.0` - Numerical computation for indicator calculations (`src/analysis/technical.py`)
- `yfinance>=0.2.36` - Yahoo Finance data for fundamentals, VIX, earnings calendar (`src/analysis/fundamentals.py`, `src/analysis/sentiment.py`, `src/orchestrator.py`)
- `vaderSentiment>=3.3.2` - NLP sentiment scoring on news text (`src/analysis/sentiment.py`)
- `ta>=0.11.0` - Technical analysis library, specifically ADX indicator (`src/analysis/technical.py`)
- `rank_bm25>=0.2.2` - BM25 lexical similarity for memory retrieval (`src/memory/situation_memory.py`)

**Infrastructure (Python):**
- `pyyaml>=6.0` - YAML config parsing (`config/settings.yaml` loaded in `src/orchestrator.py`)
- `python-dotenv>=1.0.0` - Environment variable loading from `config/.env` (`src/alpaca_client.py`, `src/notifications/telegram.py`)
- `httpx>=0.24.0` - Async HTTP client for Telegram API calls (`src/notifications/telegram.py`)

**JS Dependencies (`package.json`) - Presentation only:**
- `pptxgenjs@^4.0.1` - PowerPoint generation (`create_presentation.js`)
- `react@^19.2.4`, `react-dom@^19.2.4` - Server-side rendering of icons to SVG
- `react-icons@^5.6.0` - Icon library for presentation slides
- `sharp@^0.34.5` - SVG-to-PNG image conversion for slides

## Configuration

**Environment:**
- All secrets in `config/.env` (loaded via `python-dotenv`)
- Required: `ALPACA_API_KEY`, `ALPACA_API_SECRET`
- Optional: `ALPACA_PAPER` (defaults to `true`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Optional: `FINNHUB_API_KEY`, `NEWSAPI_KEY` (mentioned in `.env.example` but not imported in code)
- Runtime: `SHARED_STATE_DIR` set by orchestrator at startup, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` for agent mode

**Settings:**
- `config/settings.yaml` - All tunables: watchlist, screener params, scoring weights, decision thresholds, risk limits, position exit config, debate settings, memory settings
- Loaded once in `TradingOrchestrator.__init__()` via `yaml.safe_load()`

**Build:**
- No build configuration - interpreted Python, run directly
- `create_presentation.js` run with `node` directly

## Platform Requirements

**Development:**
- Python 3.11+
- Node.js (only for presentation generation)
- Alpaca paper trading account (free)
- Claude Code CLI with Agent Teams experimental feature (for full pipeline)

**Production:**
- Same as development - designed for local execution
- No containerization, no cloud deployment config
- Paper or live Alpaca account
- Stable internet connection for API calls (Alpaca, yfinance, Telegram)

---

*Stack analysis: 2026-03-30*
