# Project Research Summary

**Project:** Finance Agent Team v2 -- New Trading Desk Roles Milestone
**Domain:** Multi-agent AI trading desk (buy-side momentum/trend-following)
**Researched:** 2026-03-30
**Confidence:** MEDIUM-HIGH

## Executive Summary

This project extends an existing multi-agent AI trading system by adding trading desk roles that mirror a buy-side hedge fund pod structure. The system already has strong analyst, debate, risk, and execution coverage (14 agents across 7 phases). The critical gap is strategic oversight: no agent currently decides *whether* the desk should trade on a given day, no macro context informs decisions, and no structured daily feedback loop exists. The TradingAgents framework (arXiv:2412.20138) validates this multi-agent trading desk approach, demonstrating measurable improvements in Sharpe ratio and max drawdown versus single-agent baselines.

The recommended approach is incremental role addition in 3 phases, prioritizing the highest-impact roles first: CIO (strategic gatekeeper), Macro Strategist (cross-asset intelligence), and EOD Review Analyst (daily feedback loop). No new core technologies are required -- all new roles operate within the existing Claude Code Agent Teams framework using the `shared_state/` JSON communication pattern. The only new data needs (economic calendar, overnight futures) are minor and can be approximated with existing Alpaca data and LLM reasoning.

The top risks are agent proliferation tax (each new Teammate agent adds 10-30s latency and significant API cost), CIO calibration failure (rubber stamp or over-conservative), and conflicting veto chains between CIO, Risk Manager, and Compliance Officer. All three are mitigable with incremental rollout, historical calibration, and explicit modeling of combined pass-through rates. The estimated cost increase for Phase 1 roles is $3-7 per daily run.

## Key Findings

### Recommended Stack

No new core dependencies are needed. The existing Python 3.11+ / Claude Code Agent Teams / Alpaca API stack handles all new roles. Two optional libraries (fredapi for FRED economic data, scipy for correlation matrices) may be added in later phases but are not required for Phase 1.

**Model tier assignments for new roles:**
- **CIO / Head of Trading**: Opus -- highest-stakes strategic decision (whether to trade at all)
- **Macro Strategist**: Sonnet -- cross-asset synthesis requiring strong analytical reasoning
- **EOD Review Analyst**: Sonnet -- P&L attribution connecting multiple data points
- **Portfolio Strategist**: Sonnet -- cross-position correlation reasoning
- **Compliance Officer**: Haiku -- rule-based checks, minimal reasoning
- **Execution Strategist**: Haiku -- primarily rule-based order strategy

**Cost impact:** Phase 1 adds ~$3-7 per daily run. The CIO (Opus) is the largest single cost driver at ~$2-5/run.

### Expected Features (Roles)

**Must have (table stakes):**
- **CIO / Head of Trading** -- strategic oversight, daily trading stance, veto power. Without this, the system trades mechanically regardless of conditions.
- **Macro Strategist** -- cross-asset signals (bonds, dollar, VIX, yield curve) that inform regime detection beyond the current narrow SPY-based view.
- **Compliance Officer** -- regulatory gate (wash sales, PDT rules, concentration limits). Essential for live trading readiness.
- **Portfolio Strategist** -- cross-position correlation and portfolio-level optimization. Prevents approving 5 highly correlated positions individually.

**Should have (differentiators):**
- **EOD Review Analyst** -- closes the daily feedback loop for open positions (Reflection only handles closed trades)
- **Morning Brief Coordinator** -- overnight event synthesis providing context the pure-technical pipeline misses
- **Sector/Thematic Specialist** -- deep sector intelligence during investment debate

**Defer (v2+):**
- **Execution Strategist** -- optimization over current bracket orders; marginal gain for paper trading

**Anti-features (do not build):**
- Sell-side roles (Sales Trader, Market Maker, Broker Relations)
- Roles better as code (Quant Dev, Data Engineer, Accounting/NAV)
- Redundant splits (separate News Analyst, multiple Trader Personas)

### Architecture Approach

The existing 7-phase sequential pipeline extends with new phases inserted at natural decision boundaries. Three new layers emerge: a Pre-Market Layer (Morning Brief + Macro Strategist + CIO), an expanded Risk & Compliance Layer (Compliance Officer gate), and a Review Layer extension (EOD Review). The core communication pattern remains unchanged -- JSON files in `shared_state/YYYY-MM-DD/`. Three key architectural patterns govern integration: (1) Directive Cascade -- CIO broadcasts a `daily_directive.json` read by all downstream agents; (2) Gate Pattern -- Compliance extends the existing Risk Manager checkpoint model; (3) Feedback Loop -- EOD Review writes structured daily insights consumed by next day's pipeline.

**Major components (new):**
1. **CIO Daily Directive** -- sets trading stance, risk budget multiplier, sector preferences; broadcast to all downstream agents
2. **Macro Strategist** -- produces `macro_outlook.json` consumed by CIO and Decision Engine
3. **EOD Review Analyst** -- produces `eod_review.json` feeding next day's Morning Brief and memory system
4. **Portfolio Strategist** -- produces `portfolio_construction.json` with cross-position sizing adjustments
5. **Compliance Officer** -- produces `compliance_check.json` as a regulatory gate before execution

**Parallelization opportunities:** Morning Brief + Macro Strategist run in parallel (both feed CIO). Reporter + EOD Review + Reflection run in parallel post-execution.

### Critical Pitfalls

1. **Agent Proliferation Tax** -- Each new Teammate agent adds 10-30s latency and significant cost. Add 2-3 roles per milestone maximum. Set hard budget and latency ceilings. Track per-run cost as a first-class metric.

2. **CIO Rubber Stamp / Over-Conservatism** -- LLMs default to hedging language. Calibrate with historical data, define explicit stance triggers (VIX > 25 AND yield curve inverted = "defensive"), start with narrow scope (risk_budget_multiplier only, not individual trade decisions). Track stance distribution over 30 days.

3. **Conflicting Veto Chains** -- CIO + Risk Manager + Compliance in series creates a compound rejection rate (0.8 x 0.7 x 0.9 = 50.4% pass-through). Model combined rates, ensure non-overlapping concerns, track rejection funnel.

4. **Macro Strategist Data Hallucination** -- LLM teammate may fabricate market numbers. Mandate code execution for data retrieval before reasoning. Consider hybrid subagent/teammate approach.

5. **EOD Review Circular Reasoning** -- "Be more aggressive" -> losses -> "be more conservative" -> oscillation. Frame EOD insights as observations not directives. Apply confidence decay (1.0 yesterday, 0.5 two days ago, 0.25 three days ago).

## Implications for Roadmap

### Phase 1: Strategic Oversight (CIO + Macro Strategist + EOD Review)
**Rationale:** These three roles deliver the highest value-to-effort ratio and address the system's biggest gap: no strategic decision layer. CIO and Macro Strategist sit at the top of the pipeline and cascade influence to all downstream decisions. EOD Review closes the feedback loop from day one, enabling calibration of the new roles.
**Delivers:** Daily trading stance, cross-asset macro context, daily P&L attribution and feedback loop.
**Addresses:** CIO, Macro Strategist, EOD Review Analyst from FEATURES.md.
**Avoids:** Agent Proliferation Tax (only 3 roles). CIO calibration risk (start with narrow scope -- risk_budget_multiplier only).
**New state files:** `daily_directive.json`, `macro_outlook.json`, `eod_review.json`
**Cost impact:** ~$3-7 additional per daily run.

### Phase 2: Portfolio Intelligence (Portfolio Strategist + Compliance Officer)
**Rationale:** Once strategic oversight is in place, the next gap is portfolio-level reasoning and regulatory readiness. Portfolio Strategist prevents correlated-position risk that the individual Risk Manager misses. Compliance Officer is the prerequisite for live trading.
**Delivers:** Cross-position optimization, regulatory gate, live-trading readiness foundation.
**Addresses:** Portfolio Strategist, Compliance Officer from FEATURES.md.
**Avoids:** Conflicting Veto Chains (model combined pass-through rates when adding Compliance gate). Portfolio/Risk overlap (define clear boundary: correlation vs position limits).
**New state files:** `portfolio_construction.json`, `compliance_check.json`
**Optional dependencies:** scipy for correlation matrix computation.

### Phase 3: Workflow Enhancement (Morning Brief + Sector Specialist + Execution Strategist)
**Rationale:** Enhancement roles that improve quality but are not critical path. Morning Brief formalizes overnight context (currently handled ad-hoc by Macro Strategist). Sector Specialist enriches debate quality. Execution Strategist optimizes order types.
**Delivers:** Structured overnight intelligence, sector-specific debate input, execution quality optimization.
**Addresses:** Morning Brief Coordinator, Sector Specialist, Execution Strategist from FEATURES.md.
**Avoids:** Sector Specialist scope creep (narrow scope to supply chain and sector catalysts only). Agent Proliferation (measure cumulative latency/cost before adding all three).

### Phase Ordering Rationale

- CIO + Macro first because they sit at pipeline entry and influence everything downstream. Adding Portfolio Strategist without CIO context would be optimizing details while missing strategy.
- EOD Review in Phase 1 (not deferred) because the feedback loop from day 1 enables calibrating the CIO and Macro Strategist outputs. Without it, CIO calibration is blind.
- Compliance in Phase 2 (not Phase 1) because it adds zero value during paper trading validation of the new roles. Essential only when live trading is planned.
- Morning Brief deferred to Phase 3 because the Macro Strategist can absorb overnight synthesis initially. Splitting them out is an optimization, not a necessity.
- Execution Strategist last because current bracket orders work and optimization is marginal until the strategic layer is validated.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (CIO):** Needs prompt calibration research -- how to prevent rubber stamp behavior. Test with historical market data to validate stance outputs. Consider 2-week "shadow mode" before going live.
- **Phase 2 (Portfolio Strategist):** Needs research on correlation computation approach -- rolling windows, factor exposure models, how to combine quantitative correlation with LLM narrative reasoning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Macro Strategist + EOD Review):** Well-documented patterns. Macro Strategist follows existing analyst pattern with upgraded model tier. EOD Review follows existing Reflection Analyst pattern.
- **Phase 2 (Compliance Officer):** Standard gate pattern, same as Risk Manager. Rule-based checks are well-defined (wash sales, PDT, concentration limits).
- **Phase 3 (all roles):** Standard patterns. Morning Brief is information synthesis. Sector Specialist joins existing debate flow. Execution Strategist is a pre-Executor enrichment step.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new technologies needed. All roles use existing framework. Cost estimates based on Claude API pricing. |
| Features | MEDIUM-HIGH | Role definitions grounded in real trading desk structures and TradingAgents framework. Buy-side vs sell-side distinction is clear. |
| Architecture | HIGH | Extends existing pipeline pattern cleanly. JSON state file communication is proven. Directive cascade and gate patterns are straightforward. |
| Pitfalls | MEDIUM-HIGH | Proliferation tax and veto chain risks well-understood. CIO calibration is the biggest unknown -- no precedent for LLM-as-CIO in production. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **CIO prompt calibration:** No established methodology for calibrating an LLM CIO agent. Will need empirical testing with historical data during Phase 1 implementation. Consider running CIO in "shadow mode" (generates directives but pipeline ignores them) for 2 weeks before going live.
- **Macro data freshness:** LLM training data has a knowledge cutoff. Macro Strategist must rely on code-fetched real-time data, not LLM "memory" of market conditions. The hybrid subagent/teammate pattern needs concrete design during Phase 1 planning.
- **Language consistency:** Existing agent specs are in Chinese. Decision needed upfront: write new specs in Chinese (consistent) or migrate all to English (accessible). Mixing languages is explicitly flagged as a pitfall.
- **Combined latency budget:** No measurement of current pipeline latency exists. Need a baseline before adding roles, to know how much headroom exists for 3 new Teammate agents in Phase 1.
- **Decision Engine integration:** Each new upstream role produces output, but the Decision Engine's composite scoring formula must be updated to consume it. This integration point is under-specified and needs detailed design per phase.

## Sources

### Primary (HIGH confidence)
- [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138) -- multi-agent trading desk architecture, role definitions, performance validation
- [TradingAgents GitHub Repository](https://github.com/TauricResearch/TradingAgents) -- reference implementation
- Existing system codebase: `CLAUDE.md`, `.planning/codebase/ARCHITECTURE.md`, agent specs in `agents/`

### Secondary (MEDIUM confidence)
- [Alpaca API documentation](https://docs.alpaca.markets/) -- available data endpoints for new roles
- [CFA Institute](https://www.cfainstitute.org/programs/cfa-program/careers/portfolio-manager) -- PM role definitions
- [Bloomberg Buy-Side Trading Desk Automation](https://www.bloomberg.com/professional/insights/trading/automation-a-holistic-view-of-buy-side-trading/) -- buy-side workflow patterns

### Tertiary (LOW confidence)
- [Resonanz Capital Hedge Fund Talent Trends 2025-2026](https://resonanzcapital.com/insights/the-2025-hedge-fund-talent-tape-what-pod-hiring-signals-going-into-2026) -- industry hiring patterns
- Cost-per-run estimates -- based on approximate token counts, needs validation with actual runs

---
*Research completed: 2026-03-30*
*Ready for roadmap: yes*
