# Finance Agent Team v2

## What This Is

A multi-agent trading system that simulates a professional trading desk, where specialized AI agents collaborate through Claude Code Agent Teams to analyze markets, debate investment theses, manage risk, and execute trades on Alpaca (paper/live). The system runs a daily one-shot pipeline targeting US equities using momentum/trend-following strategy.

## Core Value

Agent Teams must be the primary execution mode -- every pipeline run uses TeamCreate + SendMessage with persistent teammates that communicate in real-time, not disposable subagents running scripts in isolation.

## Current State (v1.0 shipped)

**Shipped 2026-04-03.** 3 phases, 13 plans, 28 requirements, 59/59 UAT tests passed.

The system now has:
- **Programmatic Agent Teams** — CIO as Lead, phased teammate spawning via `src/team_orchestrator.py`
- **Strategic oversight** — CIO (daily directive), Macro Strategist (cross-asset signals), EOD Review (P&L attribution)
- **Portfolio intelligence** — Cross-position correlation analysis, graduated sizing, partial close suggestions
- **Enhanced debate** — Sector Specialist enriches debate context with supply chain, rotation, competitive landscape
- **Intelligent execution** — Order type selection (market/limit/bracket), fill quality tracking
- **Memory upgrade** — Trade journal with R-multiple, cross-session pattern learning, corruption fixes, concurrent safety

**Entry points:**
```bash
python -m src.team_orchestrator        # Agent Teams prompt (primary)
python -m src.agents_launcher --run    # Standalone pipeline (fallback)
```

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
- [x] Agent Teams primary mode with TeamCreate/SendMessage -- v1.0
- [x] CIO daily directive with trading stance and risk budget -- v1.0
- [x] Macro Strategist with cross-asset real-time data -- v1.0
- [x] EOD Review with P&L attribution and thesis drift detection -- v1.0
- [x] Portfolio Strategist with correlation analysis and sizing -- v1.0
- [x] Sector Specialist enriching investment debate -- v1.0
- [x] Execution Strategist with order type selection -- v1.0
- [x] Trade journal with lifecycle tracking and R-multiple -- v1.0
- [x] Cross-session pattern learning in memory system -- v1.0
- [x] Memory corruption fix with backup and error reporting -- v1.0
- [x] Trade log race condition fix with FileLock -- v1.0
- [x] Atomic JSON writes for concurrent safety -- v1.0

### Active

(None -- next milestone not yet defined. Run `/gsd:new-milestone` to plan next version.)

### Out of Scope

- Multi-market support (crypto, forex, non-US) -- focus on US equities first
- Continuous intra-day monitoring -- staying with daily one-shot execution
- Web UI or dashboard -- CLI + Telegram is sufficient
- Mean-reversion or options strategies -- momentum/trend-following only
- HFT or sub-second execution -- not the system's purpose

## Constraints

- **Tech Stack**: Python 3.11+, Alpaca API, Claude Code Agent Teams -- no framework changes
- **Cost**: Tiered model usage (Opus for CIO/Judge, Sonnet for analysts/debate, Haiku for data collection)
- **Trading**: Paper trading primary, live trading readiness as future goal
- **Frequency**: Daily one-shot execution, no continuous monitoring
- **Compatibility**: Preserve config/settings.yaml structure and shared_state/ pattern

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Agent Teams as primary mode | Real-time teammate communication, not script-running subagents | Good |
| CIO as Team Lead | Avoids extra Opus teammate cost; CIO naturally orchestrates | Good |
| Phased teammate spawning | Keeps active count at 3-5, saves tokens | Good |
| Tiered model assignment | Opus for CIO/Judge, Sonnet for analysts/debate, Haiku for data collection | Good |
| Sector Specialist as context enrichment | Avoids 15-30s latency of 4th sequential debater | Good |
| Execution Strategist as code, not LLM | Order type selection is quantitative, no LLM needed | Good |
| Pattern learning via tag grouping | Low trade volume makes statistical clustering impractical | Pending |
| Paper-first with live readiness | Validate improvements before risking real capital | Good |
| Chinese agent specs preserved | Consistent with existing 12 specs, well-written | Good |

## v2 Backlog

Potential next milestone items:
- Morning Brief Coordinator (overnight event synthesis)
- Compliance Officer (wash sales, PDT rules -- needed for live trading)
- Orchestrator decomposition (break 1000-line god object)
- Test suite (pytest for scoring, risk, execution)
- Linter/formatter (ruff, black, pre-commit hooks)
- Live trading transition with safety guardrails

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-04-03 after v1.0 milestone completion*
