# Codebase Structure

**Analysis Date:** 2026-03-30

## Directory Layout

```
Finace_Agent_Team/
├── src/                        # Python source code (all pipeline logic)
│   ├── __init__.py
│   ├── orchestrator.py         # Main pipeline coordinator (~800 lines)
│   ├── agents_launcher.py      # Agent Teams task functions + CLI (~637 lines)
│   ├── alpaca_client.py        # Alpaca API wrapper (~245 lines)
│   ├── state_dir.py            # Shared state directory resolver (~43 lines)
│   ├── analysis/               # Signal generation modules
│   │   ├── __init__.py
│   │   ├── technical.py        # RSI, MACD, BB, EMA, ATR, ADX indicators
│   │   ├── sentiment.py        # VADER NLP + Alpaca news + catalysts
│   │   ├── screener.py         # Dynamic symbol discovery
│   │   ├── position_reviewer.py # 4-factor exit scoring + hard stops
│   │   └── fundamentals.py     # yfinance company data for debates
│   ├── risk/                   # Risk management
│   │   ├── __init__.py
│   │   └── manager.py          # Position sizing, kill switch, constraints
│   ├── notifications/          # External notifications
│   │   ├── __init__.py
│   │   └── telegram.py         # Telegram bot integration
│   ├── memory/                 # Learning & memory system
│   │   ├── __init__.py
│   │   ├── situation_memory.py # BM25-based memory bank
│   │   └── reflection.py       # Post-trade reflection helpers
│   └── debate/                 # Investment debate support
│       ├── __init__.py
│       └── helpers.py          # Debate context prep + result merge
├── agents/                     # Claude agent specifications (Markdown, Chinese)
│   ├── analysts/               # Phase 0-1 data collection agents
│   │   ├── market_analyst.md
│   │   ├── technical_analyst.md
│   │   ├── sentiment_analyst.md
│   │   ├── fundamentals_analyst.md
│   │   └── symbol_screener.md
│   ├── researchers/            # Phase 2.5 investment debate agents
│   │   ├── bull_researcher.md
│   │   ├── bear_researcher.md
│   │   └── research_judge.md
│   ├── risk_mgmt/              # Phase 3 risk assessment
│   │   └── risk_manager.md
│   ├── trader/                 # Phase 1.5, 2, 4 trading agents
│   │   ├── decision_engine.md
│   │   ├── position_reviewer.md
│   │   └── executor.md
│   ├── reporting/              # Phase 5 notifications
│   │   └── reporter.md
│   └── reflection/             # Phase 6 post-trade learning
│       └── reflection_analyst.md
├── config/                     # Configuration
│   ├── settings.yaml           # All tunables (watchlist, weights, thresholds, risk limits)
│   └── .env                    # API keys (Alpaca, Telegram) - NEVER read contents
├── shared_state/               # Inter-agent communication (JSON, daily subfolders)
│   ├── YYYY-MM-DD/             # Daily state directory (auto-created, auto-cleaned after 7 days)
│   │   ├── dynamic_watchlist.json
│   │   ├── market_overview.json
│   │   ├── technical_signals.json
│   │   ├── sentiment_signals.json
│   │   ├── fundamentals_signals.json
│   │   ├── fundamentals_cache.json
│   │   ├── exit_review.json
│   │   ├── decisions.json
│   │   ├── risk_assessment.json
│   │   ├── execution_results.json
│   │   ├── debate_context_{SYMBOL}.json
│   │   ├── debate_{SYMBOL}_bull_r1.json
│   │   ├── debate_{SYMBOL}_bear_r1.json
│   │   ├── debate_{SYMBOL}_result.json
│   │   ├── reflection_context_{trade_id}.json
│   │   └── reflection_{trade_id}_result.json
│   └── *.json                  # Root-level copies (latest run, for quick access)
├── memory_store/               # Persistent BM25 memory banks (JSON)
│   ├── bull_memory.json
│   ├── bear_memory.json
│   ├── research_judge_memory.json
│   ├── risk_judge_memory.json
│   ├── decision_engine_memory.json
│   └── reflected_trades.json   # List of trade IDs already reflected on
├── logs/                       # Trade execution logs
│   └── trade_log.json          # Append-only JSON array of executed trades
├── .claude/                    # Claude Code configuration
│   ├── settings.local.json     # Local Claude settings
│   └── skills/                 # User-invocable Claude skills
│       ├── run-full-pipeline/SKILL.md
│       ├── check-portfolio/SKILL.md
│       ├── run-market-analysis/SKILL.md
│       ├── run-position-review/SKILL.md
│       └── search-memory/SKILL.md
├── .planning/                  # GSD planning documents
│   └── codebase/               # Architecture analysis docs (this file)
├── CLAUDE.md                   # Claude Code guidance (architecture overview)
├── requirements.txt            # Python dependencies
├── package.json                # Node.js deps (pptxgenjs for presentation generation)
├── .env.example                # Template for config/.env
├── .gitignore
├── README.md
├── TODO.md
├── REVIEW_CHANGELOG.md
├── plan.md
└── create_presentation.js      # Presentation generator (standalone utility)
```

## Directory Purposes

**`src/`:**
- Purpose: All Python source code for the trading pipeline
- Contains: Orchestrator, agent launcher, API client, analysis modules, risk management, notifications, memory, debate helpers
- Key files: `orchestrator.py` (central coordinator), `agents_launcher.py` (Agent Teams interface)

**`src/analysis/`:**
- Purpose: Signal generation from market data
- Contains: Five analyzer classes, each producing structured signal output
- Key files: `technical.py` (most complex, produces `TechnicalSignal` dataclass), `position_reviewer.py` (exit logic with hard stops)

**`src/risk/`:**
- Purpose: Trade validation and position sizing
- Contains: `RiskManager` class with portfolio constraint enforcement
- Key files: `manager.py` (single file, ~200 lines)

**`src/memory/`:**
- Purpose: BM25-based learning system for storing and retrieving trading lessons
- Contains: `SituationMemory` class (BM25 search), reflection data I/O helpers
- Key files: `situation_memory.py` (memory bank implementation), `reflection.py` (reflection context prep + performance attribution)

**`src/debate/`:**
- Purpose: Investment debate preparation and result merging
- Contains: Context assembly from all signal files + memory retrieval, score adjustment merging
- Key files: `helpers.py` (single file with `task_prepare_debate_context()` and `task_merge_debate_results()`)

**`src/notifications/`:**
- Purpose: Telegram bot integration for trading alerts
- Contains: `TelegramNotifier` class using `httpx`
- Key files: `telegram.py` (single file)

**`agents/`:**
- Purpose: Claude Agent Team specifications written in Chinese
- Contains: 12 Markdown files defining agent roles, scoring logic, execution code, I/O schemas
- Note: These are NOT code - they are prompts used as Task tool inputs in Agent Teams mode. Subagent specs are self-contained and include inline Python code snippets.

**`config/`:**
- Purpose: All configuration files
- Contains: `settings.yaml` (all tunables), `.env` (API keys)
- Key files: `settings.yaml` is the single source of truth for all pipeline parameters

**`shared_state/`:**
- Purpose: Inter-agent communication directory
- Contains: Daily subdirectories with JSON files written by each pipeline phase
- Note: Auto-created at startup, auto-cleaned after 7 days. Root-level JSON files are copies of the latest run.

**`memory_store/`:**
- Purpose: Persistent storage for BM25 memory banks
- Contains: One JSON file per memory bank (5 banks) + reflected trades tracker
- Note: Grows over time as the system learns from trades

**`logs/`:**
- Purpose: Trade execution history
- Contains: `trade_log.json` (append-only JSON array)
- Note: Used by reflection system to find unreflected closed trades

**`.claude/skills/`:**
- Purpose: Predefined workflows invocable by name in Claude Code
- Contains: 5 skill definitions for common operations

## Key File Locations

**Entry Points:**
- `src/orchestrator.py`: Direct pipeline execution (`python -m src.orchestrator [--trade]`)
- `src/agents_launcher.py`: Agent Teams launcher (`python -m src.agents_launcher --run [--trade] [--notify]`)

**Configuration:**
- `config/settings.yaml`: All tunables (watchlist, scoring weights, risk limits, debate params, memory params)
- `config/.env`: API keys (Alpaca, Telegram, optional Finnhub/NewsAPI)
- `.env.example`: Template showing required env vars

**Core Logic:**
- `src/orchestrator.py`: `TradingOrchestrator` class - pipeline coordinator, decision engine, market regime detection, bar cache
- `src/analysis/technical.py`: `TechnicalAnalyzer` - RSI, MACD, Bollinger Bands, EMA, ATR, ADX computation
- `src/analysis/position_reviewer.py`: `PositionReviewer` - hard stops (breakeven, profit lock, give-back) + soft exit scoring
- `src/risk/manager.py`: `RiskManager` - kill switch, position sizing, sector limits, risk-reward validation
- `src/debate/helpers.py`: Debate context assembly from all signal files + BM25 memory retrieval

**Agent Specs (Claude prompts):**
- `agents/analysts/*.md`: Market, technical, sentiment, fundamentals analysts + symbol screener
- `agents/researchers/*.md`: Bull researcher, bear researcher, research judge (debate)
- `agents/trader/*.md`: Decision engine, position reviewer, executor
- `agents/risk_mgmt/risk_manager.md`: Risk assessment agent
- `agents/reporting/reporter.md`: Telegram reporting agent
- `agents/reflection/reflection_analyst.md`: Post-trade reflection agent

**Shared State Files (per daily run):**
- `shared_state/{date}/dynamic_watchlist.json`: Phase 0 output - screened symbols
- `shared_state/{date}/market_overview.json`: Phase 1 output - market data + regime
- `shared_state/{date}/technical_signals.json`: Phase 1 output - per-symbol technical signals
- `shared_state/{date}/sentiment_signals.json`: Phase 1 output - per-symbol sentiment
- `shared_state/{date}/decisions.json`: Phase 2 output - trade candidates with composite scores
- `shared_state/{date}/risk_assessment.json`: Phase 3 output - risk-assessed candidates
- `shared_state/{date}/execution_results.json`: Phase 4 output - executed order details
- `shared_state/{date}/debate_context_{SYMBOL}.json`: Phase 2.5 input - assembled context for debate
- `shared_state/{date}/debate_{SYMBOL}_result.json`: Phase 2.5 output - judge verdict + score_adjustment

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `situation_memory.py`, `position_reviewer.py`)
- Agent specs: `snake_case.md` (e.g., `bull_researcher.md`, `risk_manager.md`)
- Shared state: `snake_case.json` with symbol suffix where applicable (e.g., `debate_context_AAPL.json`)

**Directories:**
- Python packages: `snake_case` (e.g., `analysis/`, `risk_mgmt/`)
- Agent groups: `snake_case` matching pipeline role (e.g., `analysts/`, `researchers/`, `trader/`)

**Classes:**
- PascalCase: `TradingOrchestrator`, `TechnicalAnalyzer`, `SituationMemory`, `RiskManager`

**Functions:**
- snake_case: `task_*()` prefix for agent-callable functions in `agents_launcher.py`
- `run_*()` prefix for orchestrator phase methods
- `_private()` prefix for internal methods

**Dataclasses:**
- PascalCase: `TechnicalSignal`, `RiskAssessment`, `ExitSignal`, `FundamentalSignal`
- All have `to_dict()` method for JSON serialization

## Where to Add New Code

**New Analysis Module (e.g., options flow analyzer):**
- Implementation: `src/analysis/new_analyzer.py` - create a class with `analyze()` method returning a dataclass
- Integration: Add instance to `TradingOrchestrator.__init__()`, add `run_new_analyst()` phase method
- Agent spec: `agents/analysts/new_analyst.md` - write self-contained prompt with I/O schema
- Shared state: Write output to `shared_state/{date}/new_signals.json`
- Config: Add tunables to `config/settings.yaml`

**New Agent for Agent Teams:**
- Spec file: `agents/{category}/new_agent.md` - include role description, execution code, I/O schema (in Chinese to match existing)
- Task function: Add `task_new_agent()` to `src/agents_launcher.py`
- Pipeline integration: Add phase to `run_full_pipeline()` and `AGENT_TEAMS_PROMPT`

**New Risk Rule:**
- Implementation: Add check to `RiskManager.assess_trade()` in `src/risk/manager.py`
- Config: Add threshold to `risk:` section in `config/settings.yaml`

**New Notification Channel:**
- Implementation: `src/notifications/new_channel.py` - create class matching `TelegramNotifier` interface pattern
- Integration: Instantiate in `agents_launcher.py` task functions alongside `TelegramNotifier`

**New Memory Bank:**
- Add `SituationMemory` instance to `TradingOrchestrator.__init__()` (pattern: `self.new_memory = SituationMemory("new_memory", mem_dir, max_entries=max_mem)`)
- Add memory retrieval in `src/debate/helpers.py` `task_prepare_debate_context()`
- Add lesson saving in `src/memory/reflection.py` `task_save_reflections()`

**New Exit Rule (hard stop):**
- Add to `PositionReviewer` in `src/analysis/position_reviewer.py`
- Add config params to `position_exit:` section in `config/settings.yaml`

## Special Directories

**`shared_state/`:**
- Purpose: Runtime inter-agent communication
- Generated: Yes, at pipeline startup
- Committed: No (in `.gitignore`; root-level JSONs may exist as examples)

**`memory_store/`:**
- Purpose: Persistent learning data
- Generated: Yes, grows over time
- Committed: No (contains runtime data)

**`logs/`:**
- Purpose: Trade execution history
- Generated: Yes, append-only
- Committed: No

**`node_modules/`:**
- Purpose: Node.js dependencies for `create_presentation.js` (pptxgenjs)
- Generated: Yes, via `npm install`
- Committed: No

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes, user-created
- Committed: No

---

*Structure analysis: 2026-03-30*
