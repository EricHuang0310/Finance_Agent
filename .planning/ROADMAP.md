# Roadmap: Finance Agent Team v2

## Overview

Transform the existing working trading pipeline into a proper Agent Teams system with strategic oversight, portfolio intelligence, and enhanced workflows. Phase 1 establishes the Agent Teams foundation and adds the highest-impact roles (CIO, Macro Strategist, EOD Review) that address the system's biggest gap: no strategic decision layer. Phase 2 adds portfolio-level reasoning. Phase 3 enriches debate quality and execution optimization. Memory system improvements are woven into each phase where they are needed.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Strategic Oversight & Agent Teams Foundation** - Establish TeamCreate pipeline, add CIO/Macro/EOD roles, fix memory reliability
- [ ] **Phase 2: Portfolio Intelligence** - Add Portfolio Strategist for cross-position optimization and structured trade journals
- [ ] **Phase 3: Debate & Execution Enhancement** - Add Sector Specialist to debates and Execution Strategist for order optimization

## Phase Details

### Phase 1: Strategic Oversight & Agent Teams Foundation
**Goal**: The pipeline runs entirely through Agent Teams with persistent teammates, and a strategic layer (CIO + Macro Strategist) governs daily trading decisions while an EOD Review closes the feedback loop
**Depends on**: Nothing (first phase)
**Requirements**: TEAMS-01, TEAMS-02, TEAMS-03, TEAMS-04, TEAMS-05, CIO-01, CIO-02, CIO-03, MACRO-01, MACRO-02, MACRO-03, EOD-01, EOD-02, EOD-03, MEM-01, MEM-04, MEM-05
**Success Criteria** (what must be TRUE):
  1. Running the pipeline spawns a TeamCreate session where all agents communicate via SendMessage, with no manual prompt pasting required
  2. Before any analysis runs, a daily_directive.json exists with trading stance and risk_budget_multiplier, and the CIO can halt all trading for the day
  3. Macro Strategist produces macro_outlook.json with real data (not LLM memory) for bonds, dollar, VIX, and yield curve signals that feed into market regime detection
  4. After execution completes, eod_review.json contains P&L attribution for open positions and thesis-drift flags, and these insights appear in next day's pipeline with confidence decay
  5. Memory corruption no longer fails silently (errors are reported), and concurrent Agent Teams execution does not corrupt the trade log
**Plans:** 7/7 plans executed
Plans:
- [x] 01-01-PLAN.md — Memory fixes (MEM-01, MEM-04) + atomic write utility
- [x] 01-02-PLAN.md — Strategic role agent specs + model tiers + settings config
- [x] 01-03-PLAN.md — Macro Strategist + CIO task functions
- [x] 01-04-PLAN.md — EOD Review task function + confidence decay
- [x] 01-05-PLAN.md — CIO directive cascade + macro regime integration
- [x] 01-06-PLAN.md — Standalone pipeline update with new phases
- [x] 01-07-PLAN.md — Team Orchestrator (programmatic TeamCreate)

### Phase 2: Portfolio Intelligence
**Goal**: A Portfolio Strategist prevents the system from approving highly correlated positions by analyzing cross-position relationships and producing sizing adjustments
**Depends on**: Phase 1
**Requirements**: PORT-01, PORT-02, PORT-03, MEM-02
**Success Criteria** (what must be TRUE):
  1. Before new positions are approved, portfolio_construction.json exists showing cross-position correlation analysis and sizing adjustments
  2. Portfolio Strategist runs after Risk Manager and before Executor, rejecting or downsizing positions that would create excessive correlation
  3. Every trade has a structured journal entry with entry/exit prices, P&L, thesis, and outcome tagging stored in the memory system
**Plans:** 2/3 plans executed
Plans:
- [x] 02-01-PLAN.md — PortfolioStrategist class + agent spec + config + task function (PORT-01, PORT-02)
- [ ] 02-02-PLAN.md — Pipeline integration: wire into run_full_pipeline() + team_orchestrator (PORT-03)
- [x] 02-03-PLAN.md — Trade journal with lifecycle tracking and R-multiple (MEM-02)

### Phase 3: Debate & Execution Enhancement
**Goal**: Investment debates include deep sector expertise and trade execution uses intelligent order type selection based on market conditions
**Depends on**: Phase 2
**Requirements**: SECT-01, SECT-02, SECT-03, EXEC-01, EXEC-02, EXEC-03, MEM-03
**Success Criteria** (what must be TRUE):
  1. During investment debate, a Sector Specialist joins as a 4th voice providing supply chain dynamics, sector rotation signals, and competitive landscape analysis for each candidate
  2. Before orders execute, an execution_plan.json recommends order type (market, limit, bracket, TWAP) based on current volatility and liquidity conditions
  3. Execution Strategist tracks estimated vs actual fill quality, and this data is available for future order type decisions
  4. The memory system recognizes patterns across historical trades (which setups work, which fail) and surfaces relevant lessons during analysis
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Strategic Oversight & Agent Teams Foundation | 7/7 | Complete |  |
| 2. Portfolio Intelligence | 2/3 | In Progress|  |
| 3. Debate & Execution Enhancement | 0/TBD | Not started | - |
