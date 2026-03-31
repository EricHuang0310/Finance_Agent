# Architecture

**Analysis Date:** 2026-03-30

## Pattern Overview

**Overall:** Multi-agent sequential pipeline with file-based inter-agent communication

**Key Characteristics:**
- Sequential pipeline of 7 phases (Phase 0 through Phase 6) with limited parallelism in Phase 1
- Agents communicate exclusively via JSON files in a daily `shared_state/YYYY-MM-DD/` directory
- Two execution modes: **Agent Teams** (Claude Code multi-agent with LLM debate/reflection) and **Standalone** (pure rule-based, no LLM reasoning)
- Momentum/trend-following strategy with one-shot execution (no continuous monitoring)
- All orchestration logic lives in a single `TradingOrchestrator` class that delegates to specialist modules

## Layers

**API Client Layer:**
- Purpose: Wraps Alpaca brokerage API for market data, orders, and account info
- Location: `src/alpaca_client.py`
- Contains: `AlpacaClient` class with methods for bars, news, orders, positions, screener
- Depends on: `alpaca-py` SDK, `config/.env` for credentials
- Used by: `TradingOrchestrator`, `TelegramNotifier`, `agents_launcher.py`

**Analysis Layer:**
- Purpose: Compute trading signals from raw market data
- Location: `src/analysis/`
- Contains: `TechnicalAnalyzer`, `SentimentAnalyzer`, `SymbolScreener`, `PositionReviewer`, `FundamentalsAnalyzer`
- Depends on: API Client Layer (for bar data), pandas, numpy, ta, vaderSentiment, yfinance
- Used by: `TradingOrchestrator` phase methods

**Risk Management Layer:**
- Purpose: Validate trades against portfolio constraints, size positions, enforce kill switch
- Location: `src/risk/manager.py`
- Contains: `RiskManager` class with `assess_trade()` method returning `RiskAssessment` dataclass
- Depends on: Portfolio state from Alpaca (account, positions)
- Used by: `TradingOrchestrator.run_risk_manager()`

**Orchestration Layer:**
- Purpose: Coordinate all phases, aggregate signals, generate trade plans, execute orders
- Location: `src/orchestrator.py`
- Contains: `TradingOrchestrator` class (~800 lines) with all phase methods and decision engine
- Depends on: All other layers
- Used by: `src/agents_launcher.py`, direct CLI invocation

**Agent Launcher Layer:**
- Purpose: Expose `task_*()` functions for Claude Agent Teams and provide standalone pipeline runner
- Location: `src/agents_launcher.py`
- Contains: 15+ `task_*()` functions, `run_full_pipeline()`, `AGENT_TEAMS_PROMPT` string
- Depends on: Orchestration Layer, Debate/Reflection helpers
- Used by: Claude Agent Teams Lead agent, CLI

**Memory Layer:**
- Purpose: Store and retrieve situation-lesson pairs for learning from past trades
- Location: `src/memory/`
- Contains: `SituationMemory` (BM25 lexical search), reflection helpers
- Depends on: `rank_bm25` library, `memory_store/` directory
- Used by: Debate context preparation, reflection phase

**Debate Layer:**
- Purpose: Prepare context and merge results for Bull/Bear/Judge investment debate
- Location: `src/debate/helpers.py`
- Contains: `task_prepare_debate_context()`, `task_merge_debate_results()`
- Depends on: shared_state JSON files, Memory Layer
- Used by: Agent Launcher (Phase 2.5)

**Notification Layer:**
- Purpose: Send trading alerts, portfolio reports, and pipeline summaries via Telegram
- Location: `src/notifications/telegram.py`
- Contains: `TelegramNotifier` class using `httpx`
- Depends on: `config/.env` for bot token and chat ID
- Used by: Agent Launcher task functions, Orchestrator

**Agent Spec Layer (non-code):**
- Purpose: Markdown specifications that define agent behavior, I/O schema, and execution code for Claude subagents/teammates
- Location: `agents/`
- Contains: 12 `.md` files organized by role (analysts, researchers, risk_mgmt, trader, reporting, reflection)
- Depends on: Nothing (read by Claude Code at runtime)
- Used by: Claude Agent Teams as Task tool prompts

## Data Flow

**Full Pipeline (Standalone Mode):**

1. **Phase 0 (Symbol Screener):** `SymbolScreener.screen_all()` queries Alpaca screener API for most-active/movers, filters by price/volume/liquidity, writes `shared_state/{date}/dynamic_watchlist.json`
2. **Phase 1 (Parallel Analysis):** Three analysts run (can be parallel in Agent Teams mode):
   - `run_market_analyst()` fetches bars, computes market_score per symbol, detects market regime via SPY EMA20/50/200 alignment + VIX + cross-asset (TLT, UUP). Writes `market_overview.json`
   - `run_technical_analyst()` computes RSI, MACD, BB, EMA, ATR, ADX per symbol, produces composite score [-1.0, 1.0]. Writes `technical_signals.json`
   - `run_sentiment_analyst()` fetches Alpaca news, runs VADER NLP, detects catalysts (earnings, FDA, FOMC, binary events), applies staleness decay. Writes `sentiment_signals.json`
3. **Phase 1.5 (Position Exit Review):** `PositionReviewer.review_all()` evaluates open positions using hard stops (breakeven, profit lock, give-back, time stop) and soft scoring (trend reversal, momentum weakening, ATR trailing stop, market context). Writes `exit_review.json`
4. **Phase 1.8 (Market Regime Detection):** Already computed in Phase 1 by `_detect_market_regime()`. Result stored in `market_overview.json` under `market_regime` key
5. **Phase 2 (Decision Engine):** `generate_trade_plan()` computes confidence-weighted composite score using regime-adjusted weights. Applies signal alignment bonus/penalty, regime conflict detection, catalyst flags. Writes `decisions.json`
6. **Phase 2.5 (Debate, Agent Teams only):** For top-N candidates: fetch fundamentals via yfinance, prepare debate context (all signals + past memories), spawn Bull/Bear/Judge teammates. Judge produces `score_adjustment` [-0.5, +0.5] merged back into composite score
7. **Phase 3 (Risk Manager):** `RiskManager.assess_trade()` checks kill switch, daily loss limit, max positions, max exposure, sector concentration, risk-reward ratio, ADX filter, 90d-high/low proximity. Writes `risk_assessment.json`
8. **Phase 4 (Executor):** Places bracket orders (market order + stop loss + take profit) or simple market orders via Alpaca. Exits are executed before new entries. Writes `execution_results.json`
9. **Phase 5 (Reporter):** Sends Telegram notifications with portfolio summary, approved/rejected trades, debate summaries
10. **Phase 6 (Reflection, Agent Teams only):** Finds unreflected closed trades in `logs/trade_log.json`, prepares context (original signals + actual P&L), spawns Reflection Analyst teammate who writes lessons to memory banks

**State Management:**
- All inter-phase communication uses JSON files in `shared_state/YYYY-MM-DD/`
- The date is frozen at startup via `SHARED_STATE_DIR` env var so all processes share the same directory
- Old daily directories are auto-cleaned after 7 days by `cleanup_old_state()`
- Within a single process, `TradingOrchestrator` holds in-memory state (bar cache, config, component instances)
- The orchestrator uses a lazy singleton pattern in `agents_launcher.py` via `get_orchestrator()`

**Bar Data Cache:**
- `TradingOrchestrator._bar_cache` (dict) deduplicates Alpaca API calls within a single run
- Key: `(symbol, timeframe, lookback_days)`, Value: DataFrame
- Not persisted across runs

## Key Abstractions

**TradingOrchestrator:**
- Purpose: Central coordinator that owns all component instances and runs the pipeline
- Location: `src/orchestrator.py`
- Pattern: God object / facade over all specialist modules

**TechnicalSignal (dataclass):**
- Purpose: Structured output from technical analysis for a single symbol
- Location: `src/analysis/technical.py`
- Pattern: Data Transfer Object with `to_dict()` serialization

**RiskAssessment (dataclass):**
- Purpose: Structured risk evaluation result per trade candidate
- Location: `src/risk/manager.py`
- Pattern: Data Transfer Object with approval/rejection decision

**ExitSignal (dataclass):**
- Purpose: Structured exit evaluation for an existing position
- Location: `src/analysis/position_reviewer.py`
- Pattern: Data Transfer Object with exit_action ("close"/"hold") and breakdown

**SituationMemory:**
- Purpose: BM25-based memory bank for storing/retrieving situation-lesson pairs
- Location: `src/memory/situation_memory.py`
- Pattern: Repository with `add()`, `search()`, `save()`, `load()` methods

**Agent Specs (.md files):**
- Purpose: Self-contained prompts for Claude subagents including role, scoring logic, execution code, I/O schema
- Location: `agents/{analysts,researchers,risk_mgmt,trader,reporting,reflection}/*.md`
- Pattern: Written in Chinese; used as Task tool prompts in Agent Teams mode

## Entry Points

**CLI - Orchestrator Direct:**
- Location: `src/orchestrator.py` (`__main__` block)
- Triggers: `python -m src.orchestrator [--trade]`
- Responsibilities: Runs the full pipeline in standalone mode (no debate/reflection)

**CLI - Agent Launcher:**
- Location: `src/agents_launcher.py` (`__main__` block)
- Triggers: `python -m src.agents_launcher --run [--trade] [--notify]`
- Responsibilities: Runs the full pipeline via `run_full_pipeline()`, supports `--prompt` to print Agent Teams launch prompt

**Agent Teams Entry:**
- Location: `src/agents_launcher.py` (`AGENT_TEAMS_PROMPT` constant)
- Triggers: User pastes prompt into Claude Code with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`
- Responsibilities: Claude Lead agent reads the prompt and orchestrates subagents/teammates through all phases

**Claude Skills:**
- Location: `.claude/skills/{run-full-pipeline,check-portfolio,run-market-analysis,run-position-review,search-memory}/SKILL.md`
- Triggers: User invokes skill name in Claude Code session
- Responsibilities: Predefined workflows for common operations

## Error Handling

**Strategy:** Defensive try/except with print-based logging and graceful degradation

**Patterns:**
- Each symbol's analysis is wrapped in try/except; failures skip the symbol and print an error, allowing the pipeline to continue with remaining symbols
- API failures (Alpaca, yfinance) return empty/default values rather than crashing
- Kill switch pattern: `RiskManager.kill_switch_active` halts all trading when daily loss exceeds threshold or drawdown exceeds max
- Optional dependencies (yfinance, ta library) use `try/except ImportError` with `_HAS_YFINANCE` / `_HAS_TA` flags
- `FundamentalsAnalyzer` implements exponential backoff retry (3 attempts) with daily disk cache to avoid redundant API calls
- No structured error types or custom exceptions; all errors are caught as broad `Exception`

## Cross-Cutting Concerns

**Logging:** Print statements with emoji prefixes throughout. No structured logging framework. Trade execution is logged to `logs/trade_log.json` as JSON append.

**Validation:** Input validation is minimal. `RiskManager.assess_trade()` validates trade parameters (entry price required). `AlpacaClient.__init__()` validates API key presence. No schema validation on shared_state JSON files.

**Authentication:** Alpaca API keys loaded from `config/.env` via `python-dotenv`. Telegram bot token also from `config/.env`. No auth middleware or token rotation.

**Configuration:** Single `config/settings.yaml` loaded at `TradingOrchestrator.__init__()`. All tunables (watchlist, weights, thresholds, risk limits, debate settings, memory settings) are in this file. Config is read once and cached in `self.config`.

**Scoring Formula:**
- Composite score = confidence-weighted average of tech, market, sentiment signals using regime-adjusted weights
- Base weights: `tech=0.35, market=0.20, sentiment=0.15` (risk_manager=0.30 is veto-only)
- `risk_on` regime boosts tech weight by 1.2x, reduces market by 0.8x
- `risk_off` regime boosts market weight by 1.3x
- Signal alignment bonus (+5%) or conflict penalty (-10%)
- Score range: [-1.0, 1.0] before debate adjustment; [-1.5, 1.5] after debate

**Agent Execution Tiers (Agent Teams mode):**
- Tier 1 (Haiku): Pure code-execution subagents (analysts, screener, risk manager, executor, reporter) - `model="haiku"`
- Tier 2 (Sonnet): Structured argumentation teammates (Bull/Bear researchers) - `model="sonnet"`
- Tier 3 (Opus): Deep reasoning teammates (Research Judge, Reflection Analyst) - default model

---

*Architecture analysis: 2026-03-30*
