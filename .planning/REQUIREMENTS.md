# Requirements: Finance Agent Team v2

**Defined:** 2026-03-31
**Core Value:** Agent Teams must be the primary execution mode -- every pipeline run uses TeamCreate + SendMessage with persistent teammates that communicate in real-time.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Agent Teams Infrastructure

- [ ] **TEAMS-01**: Pipeline runs via TeamCreate with persistent teammates communicating through SendMessage, not disposable subagents
- [x] **TEAMS-02**: Each agent role has a `.claude/agents/*.md` definition with YAML frontmatter specifying model tier, tools, and permissions
- [x] **TEAMS-03**: Tiered model assignment enforced per role: Opus for CIO/Judge/Reflection, Sonnet for analysts/debate, Haiku for data collection/execution
- [ ] **TEAMS-04**: Team lifecycle managed programmatically: spawn at pipeline start, shutdown after completion, no manual prompt pasting
- [ ] **TEAMS-05**: Dual communication layer: SendMessage for coordination/decisions, shared_state JSON for structured data

### Strategic Oversight

- [x] **CIO-01**: CIO agent produces daily_directive.json with trading stance (aggressive/neutral/defensive) and risk_budget_multiplier before any analysis runs
- [x] **CIO-02**: CIO has veto power to halt all trading for the day based on macro conditions and risk assessment
- [x] **CIO-03**: CIO directive cascades to all downstream agents (Decision Engine reads risk_budget_multiplier, Risk Manager reads trading stance)
- [x] **MACRO-01**: Macro Strategist produces macro_outlook.json with cross-asset signals (bonds TLT, dollar UUP, VIX, yield curve) before CIO makes decisions
- [x] **MACRO-02**: Macro Strategist uses code-fetched real-time data (not LLM memory) for all market numbers
- [x] **MACRO-03**: Macro outlook integrates into existing market regime detection, enriching the narrow SPY-based view

### Portfolio Intelligence

- [ ] **PORT-01**: Portfolio Strategist analyzes cross-position correlations before new positions are approved
- [ ] **PORT-02**: Portfolio Strategist produces portfolio_construction.json with sizing adjustments to prevent approving highly correlated positions
- [ ] **PORT-03**: Portfolio Strategist runs after Risk Manager and before Executor, as an additional optimization layer

### Feedback Loop

- [x] **EOD-01**: EOD Review Analyst produces eod_review.json with daily P&L attribution for all open positions
- [x] **EOD-02**: EOD Review Analyst identifies positions that changed character since entry (thesis drift)
- [x] **EOD-03**: EOD insights feed into next day's pipeline via memory system with confidence decay (1.0 yesterday, 0.5 two days ago, 0.25 three days ago)

### Debate Enhancement

- [ ] **SECT-01**: Sector Specialist agent provides deep sector intelligence during investment debate for top-N candidates
- [ ] **SECT-02**: Sector Specialist covers supply chain dynamics, sector rotation signals, and competitive landscape
- [ ] **SECT-03**: Sector Specialist joins Bull/Bear/Judge debate as a 4th voice providing domain expertise

### Execution Optimization

- [ ] **EXEC-01**: Execution Strategist recommends order type (market, limit, bracket, TWAP) based on volatility and liquidity
- [ ] **EXEC-02**: Execution Strategist produces execution_plan.json consumed by Executor agent
- [ ] **EXEC-03**: Execution Strategist tracks estimated vs actual fill quality for learning

### Memory System

- [x] **MEM-01**: Fix silent memory corruption (replace pass-through exception handling with proper error reporting)
- [ ] **MEM-02**: Add structured trade journal with entry/exit prices, P&L, thesis, and outcome tagging
- [ ] **MEM-03**: Add cross-session strategy learning: pattern recognition across trades (which setups work, which fail)
- [x] **MEM-04**: Fix trade log race condition for concurrent Agent Teams execution
- [x] **MEM-05**: EOD review insights integrate into memory with confidence decay

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Workflow Enhancement

- [ ] Morning Brief Coordinator -- overnight event synthesis (currently absorbed by Macro Strategist)
- [ ] Compliance Officer -- wash sales, PDT, concentration limits (defer until live trading planned)

### Infrastructure

- [ ] Orchestrator god object decomposition (~1000 lines into focused modules)
- [ ] pytest test suite for critical paths (scoring, risk, execution)
- [ ] Linter/formatter (ruff, black) and pre-commit hooks
- [ ] Consolidate duplicated logic (_LazyStateDir, exit execution)

## Out of Scope

- Sell-side roles (Sales Trader, Market Maker) -- system is buy-side
- Roles better as code (Quant Dev, Data Engineer) -- no LLM value-add
- Redundant role splits (separate News Analyst, multiple Trader Personas) -- complexity without value
- Multi-market support (crypto, forex) -- US equities only
- Continuous intra-day monitoring -- daily one-shot only
- Web UI/dashboard -- CLI + Telegram sufficient
- Mean-reversion/options strategies -- momentum only

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEAMS-01 | Phase 1 | Pending |
| TEAMS-02 | Phase 1 | Complete |
| TEAMS-03 | Phase 1 | Complete |
| TEAMS-04 | Phase 1 | Pending |
| TEAMS-05 | Phase 1 | Pending |
| CIO-01 | Phase 1 | Complete |
| CIO-02 | Phase 1 | Complete |
| CIO-03 | Phase 1 | Complete |
| MACRO-01 | Phase 1 | Complete |
| MACRO-02 | Phase 1 | Complete |
| MACRO-03 | Phase 1 | Complete |
| PORT-01 | Phase 2 | Pending |
| PORT-02 | Phase 2 | Pending |
| PORT-03 | Phase 2 | Pending |
| EOD-01 | Phase 1 | Complete |
| EOD-02 | Phase 1 | Complete |
| EOD-03 | Phase 1 | Complete |
| SECT-01 | Phase 3 | Pending |
| SECT-02 | Phase 3 | Pending |
| SECT-03 | Phase 3 | Pending |
| EXEC-01 | Phase 3 | Pending |
| EXEC-02 | Phase 3 | Pending |
| EXEC-03 | Phase 3 | Pending |
| MEM-01 | Phase 1 | Complete |
| MEM-02 | Phase 2 | Pending |
| MEM-03 | Phase 3 | Pending |
| MEM-04 | Phase 1 | Complete |
| MEM-05 | Phase 1 | Complete |

---
*Defined: 2026-03-31 from research + user scoping*
