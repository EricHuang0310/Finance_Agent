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
│   ├── sentiment.py             # SentimentAnalyzer — VADER NLP + news + earnings imminence + staleness
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

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Finance Agent Team v2**

A multi-agent trading system that simulates a professional trading desk, where specialized AI agents collaborate through Claude Code Agent Teams to analyze markets, debate investment theses, manage risk, and execute trades on Alpaca (paper/live). The system runs a daily one-shot pipeline targeting US equities using momentum/trend-following strategy.

**Core Value:** Agent Teams must be the primary execution mode -- every pipeline run uses TeamCreate + SendMessage with persistent teammates that communicate in real-time, not disposable subagents running scripts in isolation.

### Constraints

- **Tech Stack**: Python 3.11+, Alpaca API, Claude Code Agent Teams -- no framework changes
- **Cost**: Tiered model usage (Opus for critical decisions, Sonnet for analysis/debate, Haiku for execution tasks)
- **Trading**: Paper trading primary, live trading readiness as goal (not immediate switch)
- **Frequency**: Daily one-shot execution, no continuous monitoring requirement
- **Compatibility**: Must preserve existing config/settings.yaml structure and shared_state/ communication pattern
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ - All trading logic, orchestration, analysis, and agent task functions (`src/`)
- Uses `zoneinfo.ZoneInfo` (stdlib 3.9+), type hints with `list[dict]` syntax (3.9+), and `match` is not used but f-strings and walrus are
- JavaScript (Node.js) - Presentation generation only (`create_presentation.js`)
- Markdown - Agent specification files (`agents/**/*.md`, written in Chinese)
## Runtime
- Python 3.11+ (inferred from `zoneinfo` usage in `src/orchestrator.py`, `src/analysis/sentiment.py`)
- Node.js (for `create_presentation.js` only, not core trading)
- pip - Python dependencies via `requirements.txt`
- npm - JS dependencies via `package.json` / `package-lock.json`
- Lockfile: `package-lock.json` present for JS; no `pip` lockfile (no `requirements.lock` or `poetry.lock`)
## Frameworks
- No web framework - This is a CLI pipeline, not a web app
- Claude Code Agent Teams - Multi-agent orchestration framework (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true` env var)
- None configured - No test framework, linter, or formatter (per `CLAUDE.md`)
- No build system - Direct `python -m` execution
- Entry points: `python -m src.orchestrator` and `python -m src.agents_launcher`
## Key Dependencies
- `alpaca-py>=0.21.0` - Primary brokerage API SDK for market data, trading, screening (`src/alpaca_client.py`)
- `pandas>=2.0.0` - DataFrame operations for bar data, technical analysis (`src/analysis/technical.py`, `src/analysis/screener.py`)
- `numpy>=1.24.0` - Numerical computation for indicator calculations (`src/analysis/technical.py`)
- `yfinance>=0.2.36` - Yahoo Finance data for fundamentals, VIX, earnings calendar (`src/analysis/fundamentals.py`, `src/analysis/sentiment.py`, `src/orchestrator.py`)
- `vaderSentiment>=3.3.2` - NLP sentiment scoring on news text (`src/analysis/sentiment.py`)
- `ta>=0.11.0` - Technical analysis library, specifically ADX indicator (`src/analysis/technical.py`)
- `rank_bm25>=0.2.2` - BM25 lexical similarity for memory retrieval (`src/memory/situation_memory.py`)
- `pyyaml>=6.0` - YAML config parsing (`config/settings.yaml` loaded in `src/orchestrator.py`)
- `python-dotenv>=1.0.0` - Environment variable loading from `config/.env` (`src/alpaca_client.py`, `src/notifications/telegram.py`)
- `httpx>=0.24.0` - Async HTTP client for Telegram API calls (`src/notifications/telegram.py`)
- `pptxgenjs@^4.0.1` - PowerPoint generation (`create_presentation.js`)
- `react@^19.2.4`, `react-dom@^19.2.4` - Server-side rendering of icons to SVG
- `react-icons@^5.6.0` - Icon library for presentation slides
- `sharp@^0.34.5` - SVG-to-PNG image conversion for slides
## Configuration
- All secrets in `config/.env` (loaded via `python-dotenv`)
- Required: `ALPACA_API_KEY`, `ALPACA_API_SECRET`
- Optional: `ALPACA_PAPER` (defaults to `true`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Optional: `FINNHUB_API_KEY`, `NEWSAPI_KEY` (mentioned in `.env.example` but not imported in code)
- Runtime: `SHARED_STATE_DIR` set by orchestrator at startup, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` for agent mode
- `config/settings.yaml` - All tunables: watchlist, screener params, scoring weights, decision thresholds, risk limits, position exit config, debate settings, memory settings
- Loaded once in `TradingOrchestrator.__init__()` via `yaml.safe_load()`
- No build configuration - interpreted Python, run directly
- `create_presentation.js` run with `node` directly
## Platform Requirements
- Python 3.11+
- Node.js (only for presentation generation)
- Alpaca paper trading account (free)
- Claude Code CLI with Agent Teams experimental feature (for full pipeline)
- Same as development - designed for local execution
- No containerization, no cloud deployment config
- Paper or live Alpaca account
- Stable internet connection for API calls (Alpaca, yfinance, Telegram)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` for all Python modules: `alpaca_client.py`, `situation_memory.py`, `position_reviewer.py`
- Subdirectory `__init__.py` files exist but are empty (used only as package markers)
- Configuration files: `settings.yaml`, `.env.example`
- Use `PascalCase`: `TradingOrchestrator`, `AlpacaClient`, `TechnicalAnalyzer`, `SituationMemory`, `RiskManager`
- Analyzer/Manager suffix pattern for domain modules: `TechnicalAnalyzer`, `SentimentAnalyzer`, `FundamentalsAnalyzer`, `RiskManager`, `PositionReviewer`
- Use `snake_case` for all functions and methods
- Public methods: `analyze()`, `screen_all()`, `assess_trade()`, `review_position()`
- Private methods: prefix with underscore `_compute_score()`, `_rsi()`, `_get_bars()`, `_detect_catalysts()`
- Task functions (called by agent teams): `task_*()` prefix: `task_symbol_screener()`, `task_prepare_debate_context()`, `task_save_reflections()`
- Orchestrator pipeline methods: `run_*()` prefix: `run_market_analyst()`, `run_technical_analyst()`, `run_risk_manager()`
- Use `snake_case`: `exit_threshold`, `max_position_pct`, `regime_confidence`
- Config shortcuts stored as `self.<setting>` in `__init__`: e.g., `self.max_positions`, `self.min_price`
- Constants: `UPPER_SNAKE_CASE` for module-level constants: `ET`, `STATE_DIR`, `LOG_DIR`, `MEMORY_DIR`
- Private module-level constants with underscore prefix: `_HAS_YFINANCE`, `_HAS_TA`, `_SECTOR_AVG_PE`, `_REQUEST_DELAY`
- Use `PascalCase` with descriptive domain names: `TechnicalSignal`, `RiskAssessment`, `ExitSignal`, `FundamentalSignal`
## Code Style
- No formatter configured (no black, ruff, or autopep8)
- Indentation: 4 spaces (standard Python)
- Line length: generally under 120 characters, some lines exceed this
- String quotes: double quotes `"` used consistently throughout
- No linter configured (no flake8, ruff, pylint, or mypy)
- Type hints are used on most function signatures but not universally enforced
- No static type checking
- Triple-quoted docstrings on all classes and most public methods
- Module-level docstrings present on all `.py` files describing purpose
- Format: single-line summary for simple methods, multi-line with description for complex ones
- Example from `src/alpaca_client.py`:
- Example from `src/risk/manager.py`:
## Import Organization
- None. All imports use full dotted paths: `from src.analysis.technical import TechnicalAnalyzer`
- `sys.path.insert(0, ...)` used in `src/agents_launcher.py` to ensure project root is importable
## Error Handling
## Logging
- Emoji-prefixed status messages throughout: `print(f"  {symbol}: ${latest_close:.2f}")`
- Section headers with box-drawing characters:
- Comment dividers within classes using Unicode box-drawing:
- Status emoji convention:
## Configuration
- `config/settings.yaml` - All tuneable parameters (watchlist, scoring weights, risk limits, exit rules, debate settings, memory settings)
- `config/.env` - API keys and secrets (Alpaca, Telegram, optional Finnhub/NewsAPI)
- `.env.example` - Template for required environment variables
## Data Structures
- All analysis results use `@dataclass` with a `to_dict()` method calling `dataclasses.asdict()`:
- Dataclasses are NOT frozen (mutable). Fields have defaults where appropriate.
- Agents communicate via JSON files in `shared_state/YYYY-MM-DD/`
- All outputs serialized as plain dicts via `json.dump()`
- Downstream agents read with `json.load()`
- Analysis methods return `dict` for aggregate results or `@dataclass` for single-symbol results
- Lists of dicts for batch results
- `Optional[T]` return type when data may be unavailable
## Module Design
- No `__all__` defined in any module
- Empty `__init__.py` files in all packages (`src/`, `src/analysis/`, `src/risk/`, `src/notifications/`, `src/memory/`, `src/debate/`)
- All imports are explicit: `from src.analysis.technical import TechnicalAnalyzer`
- `src/agents_launcher.py` uses a module-level singleton for `TradingOrchestrator`:
- Both `src/debate/helpers.py` and `src/memory/reflection.py` use a `_LazyStateDir` class to defer resolution of the daily state directory
## Function Design
- Use keyword arguments with defaults for optional params
- Config values read from `self.<attr>` set in `__init__`
- Complex methods accept dicts (not typed objects) as inputs when reading from shared state
- Dataclasses for single-item results: `TechnicalSignal`, `RiskAssessment`, `ExitSignal`
- Dicts for aggregate/composite results
- `Optional[T]` when data may be unavailable
- Tuples for internal multi-value returns: `tuple[float, float]` from `_compute_score`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Sequential pipeline of 7 phases (Phase 0 through Phase 6) with limited parallelism in Phase 1
- Agents communicate exclusively via JSON files in a daily `shared_state/YYYY-MM-DD/` directory
- Two execution modes: **Agent Teams** (Claude Code multi-agent with LLM debate/reflection) and **Standalone** (pure rule-based, no LLM reasoning)
- Momentum/trend-following strategy with one-shot execution (no continuous monitoring)
- All orchestration logic lives in a single `TradingOrchestrator` class that delegates to specialist modules
## Layers
- Purpose: Wraps Alpaca brokerage API for market data, orders, and account info
- Location: `src/alpaca_client.py`
- Contains: `AlpacaClient` class with methods for bars, news, orders, positions, screener
- Depends on: `alpaca-py` SDK, `config/.env` for credentials
- Used by: `TradingOrchestrator`, `TelegramNotifier`, `agents_launcher.py`
- Purpose: Compute trading signals from raw market data
- Location: `src/analysis/`
- Contains: `TechnicalAnalyzer`, `SentimentAnalyzer`, `SymbolScreener`, `PositionReviewer`, `FundamentalsAnalyzer`
- Depends on: API Client Layer (for bar data), pandas, numpy, ta, vaderSentiment, yfinance
- Used by: `TradingOrchestrator` phase methods
- Purpose: Validate trades against portfolio constraints, size positions, enforce kill switch
- Location: `src/risk/manager.py`
- Contains: `RiskManager` class with `assess_trade()` method returning `RiskAssessment` dataclass
- Depends on: Portfolio state from Alpaca (account, positions)
- Used by: `TradingOrchestrator.run_risk_manager()`
- Purpose: Coordinate all phases, aggregate signals, generate trade plans, execute orders
- Location: `src/orchestrator.py`
- Contains: `TradingOrchestrator` class (~800 lines) with all phase methods and decision engine
- Depends on: All other layers
- Used by: `src/agents_launcher.py`, direct CLI invocation
- Purpose: Expose `task_*()` functions for Claude Agent Teams and provide standalone pipeline runner
- Location: `src/agents_launcher.py`
- Contains: 15+ `task_*()` functions, `run_full_pipeline()`, `AGENT_TEAMS_PROMPT` string
- Depends on: Orchestration Layer, Debate/Reflection helpers
- Used by: Claude Agent Teams Lead agent, CLI
- Purpose: Store and retrieve situation-lesson pairs for learning from past trades
- Location: `src/memory/`
- Contains: `SituationMemory` (BM25 lexical search), reflection helpers
- Depends on: `rank_bm25` library, `memory_store/` directory
- Used by: Debate context preparation, reflection phase
- Purpose: Prepare context and merge results for Bull/Bear/Judge investment debate
- Location: `src/debate/helpers.py`
- Contains: `task_prepare_debate_context()`, `task_merge_debate_results()`
- Depends on: shared_state JSON files, Memory Layer
- Used by: Agent Launcher (Phase 2.5)
- Purpose: Send trading alerts, portfolio reports, and pipeline summaries via Telegram
- Location: `src/notifications/telegram.py`
- Contains: `TelegramNotifier` class using `httpx`
- Depends on: `config/.env` for bot token and chat ID
- Used by: Agent Launcher task functions, Orchestrator
- Purpose: Markdown specifications that define agent behavior, I/O schema, and execution code for Claude subagents/teammates
- Location: `agents/`
- Contains: 12 `.md` files organized by role (analysts, researchers, risk_mgmt, trader, reporting, reflection)
- Depends on: Nothing (read by Claude Code at runtime)
- Used by: Claude Agent Teams as Task tool prompts
## Data Flow
- All inter-phase communication uses JSON files in `shared_state/YYYY-MM-DD/`
- The date is frozen at startup via `SHARED_STATE_DIR` env var so all processes share the same directory
- Old daily directories are auto-cleaned after 7 days by `cleanup_old_state()`
- Within a single process, `TradingOrchestrator` holds in-memory state (bar cache, config, component instances)
- The orchestrator uses a lazy singleton pattern in `agents_launcher.py` via `get_orchestrator()`
- `TradingOrchestrator._bar_cache` (dict) deduplicates Alpaca API calls within a single run
- Key: `(symbol, timeframe, lookback_days)`, Value: DataFrame
- Not persisted across runs
## Key Abstractions
- Purpose: Central coordinator that owns all component instances and runs the pipeline
- Location: `src/orchestrator.py`
- Pattern: God object / facade over all specialist modules
- Purpose: Structured output from technical analysis for a single symbol
- Location: `src/analysis/technical.py`
- Pattern: Data Transfer Object with `to_dict()` serialization
- Purpose: Structured risk evaluation result per trade candidate
- Location: `src/risk/manager.py`
- Pattern: Data Transfer Object with approval/rejection decision
- Purpose: Structured exit evaluation for an existing position
- Location: `src/analysis/position_reviewer.py`
- Pattern: Data Transfer Object with exit_action ("close"/"hold") and breakdown
- Purpose: BM25-based memory bank for storing/retrieving situation-lesson pairs
- Location: `src/memory/situation_memory.py`
- Pattern: Repository with `add()`, `search()`, `save()`, `load()` methods
- Purpose: Self-contained prompts for Claude subagents including role, scoring logic, execution code, I/O schema
- Location: `agents/{analysts,researchers,risk_mgmt,trader,reporting,reflection}/*.md`
- Pattern: Written in Chinese; used as Task tool prompts in Agent Teams mode
## Entry Points
- Location: `src/orchestrator.py` (`__main__` block)
- Triggers: `python -m src.orchestrator [--trade]`
- Responsibilities: Runs the full pipeline in standalone mode (no debate/reflection)
- Location: `src/agents_launcher.py` (`__main__` block)
- Triggers: `python -m src.agents_launcher --run [--trade] [--notify]`
- Responsibilities: Runs the full pipeline via `run_full_pipeline()`, supports `--prompt` to print Agent Teams launch prompt
- Location: `src/agents_launcher.py` (`AGENT_TEAMS_PROMPT` constant)
- Triggers: User pastes prompt into Claude Code with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`
- Responsibilities: Claude Lead agent reads the prompt and orchestrates subagents/teammates through all phases
- Location: `.claude/skills/{run-full-pipeline,check-portfolio,run-market-analysis,run-position-review,search-memory}/SKILL.md`
- Triggers: User invokes skill name in Claude Code session
- Responsibilities: Predefined workflows for common operations
## Error Handling
- Each symbol's analysis is wrapped in try/except; failures skip the symbol and print an error, allowing the pipeline to continue with remaining symbols
- API failures (Alpaca, yfinance) return empty/default values rather than crashing
- Kill switch pattern: `RiskManager.kill_switch_active` halts all trading when daily loss exceeds threshold or drawdown exceeds max
- Optional dependencies (yfinance, ta library) use `try/except ImportError` with `_HAS_YFINANCE` / `_HAS_TA` flags
- `FundamentalsAnalyzer` implements exponential backoff retry (3 attempts) with daily disk cache to avoid redundant API calls
- No structured error types or custom exceptions; all errors are caught as broad `Exception`
## Cross-Cutting Concerns
- Composite score = confidence-weighted average of tech, market, sentiment signals using regime-adjusted weights
- Base weights: `tech=0.35, market=0.20, sentiment=0.15` (risk_manager=0.30 is veto-only)
- `risk_on` regime boosts tech weight by 1.2x, reduces market by 0.8x
- `risk_off` regime boosts market weight by 1.3x
- Signal alignment bonus (+5%) or conflict penalty (-10%)
- Score range: [-1.0, 1.0] before debate adjustment; [-1.5, 1.5] after debate
- Tier 1 (Haiku): Pure code-execution subagents (analysts, screener, risk manager, executor, reporter) - `model="haiku"`
- Tier 2 (Sonnet): Structured argumentation teammates (Bull/Bear researchers) - `model="sonnet"`
- Tier 3 (Opus): Deep reasoning teammates (Research Judge, Reflection Analyst) - default model
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
