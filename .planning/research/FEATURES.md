# Feature Landscape: Trading Desk Roles for AI Agent System

**Domain:** Multi-agent AI trading desk (buy-side momentum/trend-following)
**Researched:** 2026-03-30
**Confidence:** MEDIUM-HIGH (grounded in real-world desk structures + comparable open-source framework analysis)

## Context: Buy-Side vs Sell-Side

**Recommendation: Buy-side hedge fund structure.** The system runs a momentum/trend-following strategy with its own capital, makes autonomous buy/sell decisions, and manages a portfolio. This maps directly to a buy-side trading desk (specifically a systematic/quantitative hedge fund pod), not a sell-side desk (which serves client orders and provides liquidity). The existing Research Judge already acts as a Portfolio Manager archetype, confirming this orientation.

The TradingAgents framework (arXiv:2412.20138) validated this approach -- it mirrors a buy-side trading firm with analyst team, research debate, risk management, and fund manager approval, achieving measurable improvements in Sharpe ratio and max drawdown vs single-agent baselines.

## Existing Roles (Already Implemented)

Before defining new roles, here is what the system already has:

| Role | Agent | Type | Model Tier |
|------|-------|------|------------|
| Symbol Screener | `analysts/symbol_screener.md` | Subagent | Haiku |
| Market Analyst | `analysts/market_analyst.md` | Subagent | Haiku |
| Technical Analyst | `analysts/technical_analyst.md` | Subagent | Haiku |
| Sentiment Analyst | `analysts/sentiment_analyst.md` | Subagent | Haiku |
| Fundamentals Analyst | `analysts/fundamentals_analyst.md` | Subagent | Haiku |
| Bull Researcher | `researchers/bull_researcher.md` | Teammate | Sonnet |
| Bear Researcher | `researchers/bear_researcher.md` | Teammate | Sonnet |
| Research Judge (PM role) | `researchers/research_judge.md` | Teammate | Opus |
| Risk Manager | `risk_mgmt/risk_manager.md` | Subagent | Haiku |
| Decision Engine | `trader/decision_engine.md` | Lead | Sonnet |
| Position Reviewer | `trader/position_reviewer.md` | Subagent | Haiku |
| Executor | `trader/executor.md` | Subagent | Haiku |
| Reporter | `reporting/reporter.md` | Subagent | Haiku |
| Reflection Analyst | `reflection/reflection_analyst.md` | Teammate | Opus |

**Gap analysis:** The system has strong coverage for analysis, debate, risk checking, and execution. It lacks: strategic oversight (CIO/macro), compliance, structured workflow orchestration (morning brief, EOD review), and portfolio-level reasoning (cross-position correlation, portfolio construction).

---

## Table Stakes

Roles every serious trading desk has. Missing these makes the system feel like a toy.

### 1. Chief Investment Officer (CIO) / Head of Trading

| Attribute | Detail |
|-----------|--------|
| **What it does** | Sets overall portfolio strategy, capital allocation targets, risk appetite for the day/week. Decides whether the desk should be aggressive, defensive, or flat based on macro conditions. Has ultimate veto power over the entire pipeline. |
| **Why expected** | Every real trading desk has a top-level decision-maker who sets the strategic direction. The current system has no one "above" the Research Judge -- the pipeline runs mechanically regardless of whether conditions warrant trading at all. |
| **Real-world analog** | CIO or Head PM at a hedge fund pod. Sets conviction levels, determines how much risk budget to deploy. |
| **AI agent value** | HIGH. An LLM can synthesize macro conditions, recent portfolio performance, market regime, and memory of past lessons to set a daily "trading stance" (aggressive/normal/defensive/sit-out) that cascades to all downstream agents. |
| **Execution type** | **Teammate** -- requires LLM reasoning to weigh qualitative factors |
| **Model tier** | **Opus** -- highest-stakes decision (whether to trade at all) |
| **Complexity** | Medium |
| **Where in pipeline** | Pre-Phase 0 (new Phase -1). Runs before anything else. Outputs a `daily_directive.json` with stance, risk budget, sector preferences, and any no-trade mandates. |

### 2. Macro Strategist

| Attribute | Detail |
|-----------|--------|
| **What it does** | Analyzes cross-asset signals (bonds/TLT, dollar/UUP, VIX, yield curve, commodities, sector rotation), Fed policy expectations, geopolitical events. Produces a macro outlook that informs the CIO's daily directive and the Decision Engine's regime adjustments. |
| **Why expected** | The current Market Analyst does SPY regime detection (EMA alignment + VIX + TLT/UUP), but this is a narrow technical view. Real desks have someone tracking the broader macro picture -- what is the Fed doing, are we in a risk-on/risk-off cycle, is there sector rotation underway. |
| **Real-world analog** | Global macro strategist, cross-asset strategist at a multi-strategy fund. |
| **AI agent value** | HIGH. LLMs excel at synthesizing diverse information sources into a coherent narrative. This is a natural LLM strength -- connecting dots between yield curve inversion, dollar strength, and equity sector implications. |
| **Execution type** | **Teammate** -- requires reasoning and narrative synthesis, not just indicator calculation |
| **Model tier** | **Sonnet** -- needs good reasoning but not the depth of final decisions |
| **Complexity** | Medium |
| **Where in pipeline** | Phase 0.5 (after screener, before analysts). Outputs `macro_outlook.json` consumed by CIO, Market Analyst, and Decision Engine. |

### 3. Compliance Officer

| Attribute | Detail |
|-----------|--------|
| **What it does** | Pre-trade compliance checks: restricted lists, wash sale rules, pattern day trader rules (if under 25K), concentration limits beyond what Risk Manager checks (regulatory limits vs portfolio limits), ensuring orders comply with exchange rules (lot sizes, price limits). Post-trade: audit trail verification, regulatory reporting readiness. |
| **Why expected** | Every regulated trading operation has compliance. For paper trading this is low-priority, but for live trading readiness (LIVE-01 in PROJECT.md) this is mandatory. Even in paper mode, building the compliance check pipeline now prevents costly retrofitting later. |
| **Real-world analog** | Chief Compliance Officer (CCO) or compliance analyst at any registered investment advisor. |
| **AI agent value** | MEDIUM. Most compliance checks are rule-based (better as code), but an LLM can catch edge cases and provide reasoning for borderline situations. The main value is the *checkpoint* in the pipeline, not the LLM reasoning per se. |
| **Execution type** | **Subagent** -- primarily rule-based checks with code execution |
| **Model tier** | **Haiku** -- rule application, not deep reasoning |
| **Complexity** | Low-Medium |
| **Where in pipeline** | Phase 3.5 (after Risk Manager, before Executor). Adds a compliance gate. Outputs `compliance_check.json`. |

### 4. Portfolio Strategist (Portfolio Construction)

| Attribute | Detail |
|-----------|--------|
| **What it does** | Evaluates proposed trades in the context of the overall portfolio -- not just individual risk (Risk Manager's job), but portfolio-level concerns: correlation between positions, beta exposure, sector tilt, factor exposure, net/gross exposure targets. Recommends position sizing adjustments to optimize portfolio characteristics. |
| **Why expected** | The current Risk Manager checks individual position limits and sector concentration, but does not reason about the portfolio as a whole. Real desks distinguish between risk management (guard rails) and portfolio construction (optimization). A system that approves 5 highly correlated tech stocks individually misses the portfolio-level risk. |
| **Real-world analog** | Portfolio construction analyst, quantitative portfolio manager. |
| **AI agent value** | MEDIUM-HIGH. An LLM can reason about correlation narratives ("NVDA, AMD, and AVGO are all exposed to the same AI capex cycle"), though quantitative correlation calculations should be done in code. |
| **Execution type** | **Teammate** -- needs to reason about cross-position relationships |
| **Model tier** | **Sonnet** -- analytical reasoning about portfolio composition |
| **Complexity** | High |
| **Where in pipeline** | Phase 2.8 (after debate, before Risk Manager). Takes the post-debate candidate list and adjusts sizing/selection for portfolio-level optimization. Outputs `portfolio_construction.json`. |

---

## Differentiators

Roles that elevate the system beyond a basic trading bot. Not every desk has these, but they add real edge.

### 5. Morning Brief Coordinator

| Attribute | Detail |
|-----------|--------|
| **What it does** | Synthesizes overnight developments (futures, Asia/Europe sessions, pre-market movers, earnings releases, economic calendar) into a structured morning brief before the pipeline runs. Identifies what changed since yesterday's close and what to watch today. |
| **Value proposition** | Provides context that pure technical analysis misses. A gap up/down overnight, a surprise earnings report, or an FOMC announcement completely changes the trading landscape. Currently the system starts each day fresh without considering what happened overnight. |
| **Real-world analog** | Morning meeting at any trading desk -- typically 15-30 minutes where the team reviews overnight events and sets the day's agenda. |
| **AI agent value** | HIGH. This is pure information synthesis -- exactly what LLMs do best. Gathering overnight news, futures data, pre-market action, and economic calendar items into a coherent brief. |
| **Execution type** | **Teammate** -- narrative synthesis of diverse overnight information |
| **Model tier** | **Sonnet** -- synthesis task, not decision-making |
| **Complexity** | Low-Medium |
| **Where in pipeline** | Phase -0.5 (before CIO directive, provides input to CIO). Outputs `morning_brief.json`. |

### 6. EOD Review Analyst

| Attribute | Detail |
|-----------|--------|
| **What it does** | End-of-day portfolio review: realized P&L attribution (what contributed/detracted), unrealized P&L changes, position drift from targets, today's execution quality assessment (slippage, timing), and tomorrow's watchlist adjustments. Feeds insights to the memory system and next day's Morning Brief. |
| **Value proposition** | Closes the feedback loop. The current Reflection Analyst only triggers on *closed trades*, missing the daily learning opportunity from positions that are still open. EOD Review catches "we should have exited NVDA today because X" before it becomes a realized loss. |
| **Real-world analog** | End-of-day P&L review meeting, portfolio review with the PM. |
| **AI agent value** | HIGH. P&L attribution and execution quality assessment require connecting multiple data points (entry price, current price, what happened during the day, how signals evolved). |
| **Execution type** | **Teammate** -- requires reasoning about what went right/wrong and why |
| **Model tier** | **Sonnet** -- analytical review, not final decision |
| **Complexity** | Medium |
| **Where in pipeline** | Phase 7 (new post-execution phase, after Reporter, before/alongside Reflection). Outputs `eod_review.json`. |

### 7. Sector/Thematic Specialist

| Attribute | Detail |
|-----------|--------|
| **What it does** | Provides deep expertise on specific sectors or themes currently relevant to the portfolio. When the system is considering NVDA, the specialist contributes AI/semiconductor supply chain knowledge. When considering XLE names, it contributes energy market dynamics. |
| **Value proposition** | The current Bull/Bear researchers are generalists. A sector specialist can identify risks and catalysts that generalists miss (e.g., "TSMC earnings next week will move all semis" or "crude oil inventory report on Wednesday affects all energy names"). |
| **Real-world analog** | Sector analyst at a hedge fund, industry specialist on the research team. |
| **AI agent value** | MEDIUM-HIGH. LLMs have broad knowledge of sector dynamics. The challenge is keeping this current -- would need to pull sector-specific news/data. |
| **Execution type** | **Teammate** -- domain reasoning about sector dynamics |
| **Model tier** | **Sonnet** -- specialized analysis |
| **Complexity** | Medium |
| **Where in pipeline** | Phase 2.5 (participates in debate alongside Bull/Bear, or provides input to them). Outputs appended to `debate_context_{symbol}.json`. |

### 8. Execution Strategist

| Attribute | Detail |
|-----------|--------|
| **What it does** | Determines optimal execution approach: market vs limit orders, timing (open, VWAP period, close), order splitting for larger positions, slippage estimation. Evaluates post-execution quality (was the fill good relative to VWAP/arrival price). |
| **Value proposition** | The current Executor simply fires bracket orders. Real desks obsess over execution quality because it directly impacts returns. Even in a daily one-shot system, the difference between market-on-open vs a limit order at a better price adds up. |
| **Real-world analog** | Execution trader, algorithmic trading desk, transaction cost analysis (TCA) team. |
| **AI agent value** | LOW-MEDIUM. Most execution optimization is better done with algorithms and rules than LLM reasoning. However, an LLM can decide *strategy* (e.g., "this is a thin name, use limit order with patience" vs "this is liquid, just hit the market"). |
| **Execution type** | **Subagent** -- mostly rule-based with some strategic reasoning |
| **Model tier** | **Haiku** -- execution logic is primarily computational |
| **Complexity** | Medium-High |
| **Where in pipeline** | Phase 3.8 (after compliance, enhances Executor's behavior). Outputs `execution_strategy.json` consumed by Executor. |

---

## Anti-Features

Roles that do NOT translate well to AI agents. Explicitly do not build these.

### Sell-Side Sales/Coverage Roles

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Sales Trader | Sell-side role -- handles client order flow, not relevant to autonomous buy-side system | N/A -- system has no clients |
| Market Maker | Requires continuous quoting and inventory management; contradicts daily one-shot model | Stick with directional momentum strategy |
| Broker Relations | Manages relationships with counterparties for best execution; Alpaca is the sole broker | Use Alpaca's native routing |

### Roles Better Served by Code Than LLM Agents

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Quantitative Developer | Builds trading infrastructure -- this is the *system itself*, not an agent role | Just write good Python code |
| Data Engineer | ETL pipelines, data quality -- operational infrastructure, not a reasoning role | Build data validation into existing analysts |
| Operations/Settlement | Back-office trade settlement and reconciliation -- Alpaca handles this | Use Alpaca's built-in position/order APIs |
| Accounting/NAV Calculation | Fund accounting -- simple portfolio math, no reasoning needed | Code this as a utility function, not an agent |

### Roles That Add Complexity Without Value

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Separate News Analyst (split from Sentiment) | TradingAgents framework splits these, but for a daily one-shot momentum system, news and sentiment are tightly coupled. Splitting adds agent coordination overhead for minimal gain. | Keep combined Sentiment Analyst with news integration |
| Multiple Trader Personas (aggressive/neutral/conservative) | TradingAgents uses this for risk calibration, but the current system already handles this through market regime detection and risk parameters. Adding trader personas duplicates existing functionality. | Use CIO daily directive + Risk Manager params instead |
| Legal Counsel Agent | Regulatory legal analysis is overkill for a paper/small-live trading system | Compliance Officer handles practical regulatory checks |

---

## Feature Dependencies

```
Morning Brief Coordinator
    |
    v
CIO / Head of Trading  (depends on: Morning Brief, Macro Strategist, EOD Review from yesterday)
    |
    v
Macro Strategist  (can run parallel with Morning Brief, but CIO needs both)
    |
    v
[Existing Phase 0-1 pipeline]  (analysts receive CIO directive as context)
    |
    v
Portfolio Strategist  (depends on: debate results + current portfolio state)
    |
    v
[Existing Risk Manager]  (receives portfolio-adjusted candidates)
    |
    v
Compliance Officer  (depends on: risk-approved candidates)
    |
    v
Execution Strategist  (depends on: compliance-approved candidates)
    |
    v
[Existing Executor]  (receives execution strategy)
    |
    v
EOD Review Analyst  (depends on: execution results + full day's data)
    |
    v
[Existing Reflection Analyst]  (can use EOD Review insights)
```

**Critical path for new roles:** CIO and Macro Strategist are the most impactful and should be added first. They sit at the top of the pipeline and cascade their influence to all downstream decisions.

---

## Communication Patterns

### Real-World Trading Desk Communication Map

```
                    CIO
                   / | \
                  /  |  \
     Macro Strat   PM   Risk Manager
         |        / | \       |
         |       /  |  \      |
    Analysts  Bull Bear Judge Compliance
                              |
                           Executor
```

### Proposed Agent Communication for This System

**Top-down directive flow:**
1. Morning Brief -> CIO: "Here's what happened overnight"
2. CIO -> All agents (via `daily_directive.json`): "Today we're defensive, reduce position sizes 30%, avoid earnings names"
3. Macro Strategist -> CIO + Decision Engine (via `macro_outlook.json`): "Yield curve steepening, favor cyclicals over growth"

**Bottom-up information flow:**
4. Analysts -> Decision Engine: Market/technical/sentiment signals (existing)
5. Bull/Bear/Judge -> Decision Engine: Debate score adjustments (existing)
6. Portfolio Strategist -> Risk Manager: Portfolio-level sizing recommendations
7. Risk Manager -> Compliance -> Executor: Approved trade list (existing, with compliance gate added)

**Feedback loop:**
8. EOD Review -> Memory System + next day's Morning Brief: What worked, what didn't
9. Reflection Analyst -> Memory Banks: Lessons from closed trades (existing)

### Decision Hierarchy and Veto Power

| Level | Role | Power | Rationale |
|-------|------|-------|-----------|
| 1 (highest) | CIO | Can halt all trading for the day ("sit-out" directive) | Strategic-level override |
| 2 | Risk Manager | Veto power on individual trades (existing) | Capital protection |
| 3 | Compliance Officer | Veto power on regulatory grounds | Regulatory protection |
| 4 | Portfolio Strategist | Can reduce position sizes, cannot veto | Optimization, not gatekeeping |
| 5 | Research Judge | Score adjustment (+/- 0.5), influences but doesn't veto | Advisory role (existing) |

---

## MVP Recommendation: Phase 1 New Roles

Prioritize these 3 roles for initial implementation (highest value-to-effort ratio):

1. **CIO / Head of Trading** -- Adds strategic oversight layer. Without it, the system trades mechanically regardless of whether conditions warrant it. This is the single highest-impact addition.

2. **Macro Strategist** -- Feeds the CIO with cross-asset intelligence. Upgrades the existing Market Analyst's narrow SPY-based regime detection into a proper macro view.

3. **EOD Review Analyst** -- Closes the daily feedback loop. Currently the system only learns from closed trades (Reflection Analyst). EOD Review enables daily learning from open positions and execution quality.

**Defer to Phase 2:**
- Portfolio Strategist: High value but high complexity. Requires correlation data infrastructure.
- Compliance Officer: Essential for live trading, not urgent for paper trading.
- Morning Brief Coordinator: Nice-to-have, can be folded into Macro Strategist initially.

**Defer to Phase 3:**
- Execution Strategist: Optimization role. Current bracket orders work fine for paper trading.
- Sector/Thematic Specialist: Enhancement to debate quality. Requires dynamic sector detection.

---

## Model Tier Summary for All Roles (Existing + New)

| Tier | Model | Roles | Rationale |
|------|-------|-------|-----------|
| Opus | Deepest reasoning | CIO, Research Judge, Reflection Analyst | Final decisions, strategic judgment, lesson extraction |
| Sonnet | Strong analytical | Macro Strategist, Portfolio Strategist, Bull/Bear Researchers, Decision Engine, EOD Review, Morning Brief, Sector Specialist | Analysis, debate, synthesis tasks |
| Haiku | Fast execution | All Analysts, Risk Manager, Compliance Officer, Executor, Execution Strategist, Reporter, Screener | Code execution, rule application, data processing |

---

## Sources

- [TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv)](https://arxiv.org/abs/2412.20138) -- PRIMARY: Directly comparable multi-agent trading framework with role definitions (HIGH confidence)
- [TradingAgents GitHub Repository](https://github.com/TauricResearch/TradingAgents) -- Reference implementation (HIGH confidence)
- [CFA Institute: What is a Portfolio Manager?](https://www.cfainstitute.org/programs/cfa-program/careers/portfolio-manager) -- PM role definition (HIGH confidence)
- [Chief Investment Officer - Wikipedia](https://en.wikipedia.org/wiki/Chief_investment_officer) -- CIO role and hierarchy (HIGH confidence)
- [Key Roles in a Hedge Fund - Finance Unlocked](https://financeunlocked.com/videos/who-works-in-a-hedge-fund) -- Hedge fund team structure (MEDIUM confidence)
- [The PM & The Trader - Global Trading](https://www.globaltrading.net/the-pm-the-trader/) -- PM-Trader communication patterns (MEDIUM confidence)
- [Buy-Side Trading Desk Automation - Bloomberg](https://www.bloomberg.com/professional/insights/trading/automation-a-holistic-view-of-buy-side-trading/) -- Buy-side workflow patterns (MEDIUM confidence)
- [P&L Reconciliations - Wiley](https://onlinelibrary.wiley.com/doi/10.1002/9781118939789.ch14) -- EOD reconciliation process (MEDIUM confidence)
- [Hedge Fund Talent Trends 2025-2026 - Resonanz Capital](https://resonanzcapital.com/insights/the-2025-hedge-fund-talent-tape-what-pod-hiring-signals-going-into-2026) -- Current industry hiring patterns (LOW confidence, market commentary)
