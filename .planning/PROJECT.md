# Finance Agent Team v2

## What This Is

A multi-agent trading system that simulates a professional trading desk, where specialized AI agents collaborate through Claude Code Agent Teams to analyze markets, debate investment theses, manage risk, and execute trades on Alpaca (paper/live). The system runs a daily one-shot pipeline targeting US equities using momentum/trend-following strategy.

## Core Value

Agent Teams must be the primary execution mode -- every pipeline run uses TeamCreate + SendMessage with persistent teammates that communicate in real-time, not disposable subagents running scripts in isolation.

## Requirements

### Validated

- [x] Dynamic symbol screening with activity scoring and sector diversification -- existing
- [x] Parallel market/technical/sentiment analysis with confidence tracking -- existing
- [x] Position exit review with 4-factor scoring and ATR-based stops -- existing
- [x] Confidence-weighted composite scoring with market regime adjustment -- existing
- [x] Investment debate (Bull/Bear/Judge) for top-N candidates -- existing
- [x] Risk management with hard rules, kill switch, and position sizing -- existing
- [x] Bracket order execution (stop-loss + take-profit) via Alpaca -- existing
- [x] Telegram notifications for signals, orders, and portfolio reports -- existing
- [x] BM25-based memory system with 5 memory banks -- existing
- [x] Post-trade reflection and lesson extraction -- existing
- [x] Shared state communication via daily JSON files -- existing
- [x] Configurable watchlist (static/dynamic) and scoring weights -- existing

### Active

- [ ] **TEAMS-01**: Refactor pipeline to use TeamCreate/SendMessage as primary execution mode
- [ ] **TEAMS-02**: Replace AGENT_TEAMS_PROMPT text blob with programmatic team orchestration
- [ ] **TEAMS-03**: Design tiered model assignment (Opus/Sonnet/Haiku) per agent role
- [ ] **ROLES-01**: Research and add real trading desk roles (e.g., CIO, Macro Strategist, Compliance)
- [ ] **ROLES-02**: Redesign agent specs to support teammate communication patterns
- [ ] **ROLES-03**: Add pre-trade and post-trade review workflows matching trading desk practices
- [ ] **ARCH-01**: Break up TradingOrchestrator god object (~1000 lines) into focused modules
- [ ] **ARCH-02**: Consolidate duplicated logic (exit execution, _LazyStateDir, etc.)
- [ ] **ARCH-03**: Replace global mutable singleton with dependency injection
- [ ] **MEM-01**: Improve memory system with structured trade journals and performance tracking
- [ ] **MEM-02**: Add cross-session strategy learning (pattern recognition across trades)
- [ ] **MEM-03**: Fix memory corruption silent failure and race conditions
- [ ] **QUAL-01**: Add pytest test suite for critical paths (scoring, risk, execution)
- [ ] **QUAL-02**: Add linter/formatter (ruff, black) and pre-commit hooks
- [ ] **LIVE-01**: Ensure architecture supports paper-to-live transition with safety guardrails

### Out of Scope

- Multi-market support (crypto, forex, non-US) -- focus on US equities first
- Continuous intra-day monitoring -- staying with daily one-shot execution
- Web UI or dashboard -- CLI + Telegram is sufficient
- Mean-reversion or options strategies -- momentum/trend-following only
- HFT or sub-second execution -- not the system's purpose

## Context

**Current State:** Working brownfield system with ~1,400 lines of Python across 12 modules. Agent specs written in Chinese (12 .md files). Two execution modes exist but Agent Teams mode requires manual prompt pasting and doesn't use formal TeamCreate. The system successfully runs daily paper trading analysis.

**Codebase Map:** Available at `.planning/codebase/` (7 documents, analyzed 2026-03-30).

**Key Technical Debt:**
- Orchestrator is a god object handling analysis, scoring, execution, and state management
- Duplicated exit logic between agents_launcher.py and orchestrator.py
- Trade log race condition in concurrent Agent Teams mode
- No tests, no linter, no type checking
- Memory corruption silently ignored

**Prior Session (2026-03-30):** Successfully ran full Agent Teams pipeline with TeamCreate for investment debate (Bull/Bear/Judge as teammates). Confirmed the pattern works but isn't integrated into the default pipeline flow.

## Constraints

- **Tech Stack**: Python 3.11+, Alpaca API, Claude Code Agent Teams -- no framework changes
- **Cost**: Tiered model usage (Opus for critical decisions, Sonnet for analysis/debate, Haiku for execution tasks)
- **Trading**: Paper trading primary, live trading readiness as goal (not immediate switch)
- **Frequency**: Daily one-shot execution, no continuous monitoring requirement
- **Compatibility**: Must preserve existing config/settings.yaml structure and shared_state/ communication pattern

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Agent Teams as primary mode | Ensures real-time teammate communication, not script-running subagents | -- Pending |
| Tiered model assignment | Balance quality vs cost: Opus for judges/CIO, Sonnet for analysts/debate, Haiku for data collection | -- Pending |
| Research trading desk roles before implementing | Real-world trading desk structure should inform agent design, not ad-hoc additions | -- Pending |
| Paper-first with live readiness | Validate improvements before risking real capital | -- Pending |
| Preserve Chinese agent specs | Agent specs are well-written and functional, no need to translate | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check -- still the right priority?
3. Audit Out of Scope -- reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-31 after initialization*
