# Architecture Patterns: Trading Desk Role Integration

**Domain:** Multi-agent AI trading desk role additions
**Researched:** 2026-03-30

## Recommended Architecture

### Extended Pipeline with New Phases

The existing 7-phase pipeline (Phase 0 through Phase 6) extends to accommodate new roles without restructuring existing phases. New roles insert as additional phases at natural decision boundaries.

```
Pre-Market Layer (NEW)
  Phase -1:   Morning Brief Coordinator  [Teammate, Sonnet]  (overnight events synthesis)
  Phase -0.5: Macro Strategist           [Teammate, Sonnet]  (cross-asset macro outlook)
  Phase -0.2: CIO Daily Directive        [Teammate, Opus]    (trading stance + risk budget)

Analysis Layer (EXISTING)
  Phase 0:    Symbol Screener            [Subagent, Haiku]   (receives CIO sector preferences)
  Phase 1:    Market/Tech/Sentiment      [Subagent x3, Haiku] (receives CIO directive as context)
  Phase 1.5:  Position Exit Reviewer     [Subagent, Haiku]
  Phase 1.8:  Market Regime Detection    [Lead]

Decision Layer (EXISTING + NEW)
  Phase 2:    Decision Engine            [Lead, Sonnet]       (receives macro outlook + CIO directive)
  Phase 2.5:  Investment Debate          [Teammate x3]        (Bull/Bear/Judge, existing)
  Phase 2.8:  Portfolio Strategist       [Teammate, Sonnet]   (NEW: cross-position optimization)

Risk & Compliance Layer (EXISTING + NEW)
  Phase 3:    Risk Manager               [Subagent, Haiku]    (receives CIO risk budget)
  Phase 3.5:  Compliance Officer         [Subagent, Haiku]    (NEW: regulatory gate)

Execution Layer (EXISTING + NEW)
  Phase 3.8:  Execution Strategist       [Subagent, Haiku]    (NEW: order type/timing strategy)
  Phase 4:    Executor                   [Subagent, Haiku]    (receives execution strategy)

Review Layer (EXISTING + NEW)
  Phase 5:    Reporter                   [Subagent, Haiku]
  Phase 6:    Reflection Analyst         [Teammate, Opus]
  Phase 7:    EOD Review Analyst         [Teammate, Sonnet]   (NEW: daily P&L attribution + feedback)
```

### Component Boundaries

| Component | Responsibility | Communicates With | State File |
|-----------|---------------|-------------------|------------|
| Morning Brief (NEW) | Overnight event synthesis | CIO (output), Macro Strategist (parallel) | `morning_brief.json` |
| Macro Strategist (NEW) | Cross-asset macro analysis | CIO (output), Decision Engine (output) | `macro_outlook.json` |
| CIO (NEW) | Daily trading stance + risk budget | All downstream agents (via directive) | `daily_directive.json` |
| Portfolio Strategist (NEW) | Cross-position optimization | Risk Manager (output) | `portfolio_construction.json` |
| Compliance Officer (NEW) | Regulatory gate | Executor (output) | `compliance_check.json` |
| Execution Strategist (NEW) | Order strategy optimization | Executor (output) | `execution_strategy.json` |
| EOD Review (NEW) | Daily P&L attribution + learning | Memory System (output), next day's Brief | `eod_review.json` |

### Data Flow for New Roles

```
overnight_data + yesterday's eod_review.json
    |
    v
Morning Brief  -----> morning_brief.json
    |                       |
    v                       v
Macro Strategist -----> macro_outlook.json
    |                       |
    |    +------------------+
    v    v
CIO Directive -------> daily_directive.json
    |                       |
    |    +------ read by all downstream agents ------+
    v    v                                           v
[Phase 0-2 existing]                          [Risk Manager reads
                                               CIO risk budget]
    |
    v
Portfolio Strategist -> portfolio_construction.json
    |                       |
    v                       v
[Risk Manager] -------> risk_assessment.json
    |
    v
Compliance Officer ---> compliance_check.json
    |
    v
Execution Strategist -> execution_strategy.json
    |
    v
[Executor] -----------> execution_results.json
    |
    v
EOD Review -----------> eod_review.json (persists for next day)
```

## Patterns to Follow

### Pattern 1: Directive Cascade

**What:** CIO produces a `daily_directive.json` that all downstream agents read as additional context. This is a broadcast pattern -- one writer, many readers.

**When:** Any role that sets strategic direction for the entire pipeline.

**Example schema:**
```json
{
  "date": "2026-03-30",
  "trading_stance": "defensive",
  "risk_budget_multiplier": 0.7,
  "sector_preferences": {
    "favor": ["Healthcare", "Utilities"],
    "avoid": ["Technology"],
    "reason": "VIX elevated, yield curve steepening favors defensives"
  },
  "position_size_cap_override": null,
  "no_trade_mandate": false,
  "watchlist_additions": [],
  "watchlist_removals": ["TSLA"],
  "rationale": "Macro outlook suggests risk-off rotation. Reducing exposure to momentum-heavy tech names. Maintaining existing positions but no new aggressive entries.",
  "confidence": 0.75
}
```

**Why this pattern:** Mirrors how real CIOs communicate -- a concise directive that teams interpret in their specific context. The directive does not micromanage each analyst; it sets parameters they operate within.

### Pattern 2: Gate Pattern (Compliance)

**What:** A checkpoint that can approve, reject, or modify trades but never initiates trades. Same pattern as existing Risk Manager, extended to compliance concerns.

**When:** Any role whose primary function is gatekeeping rather than analysis.

**Why:** Keeps the pipeline's existing "propose then validate" flow. Risk Manager is the model for this pattern. Compliance extends it with different rules.

### Pattern 3: Feedback Loop (EOD Review)

**What:** EOD Review writes structured insights that are consumed by next day's Morning Brief and CIO. Creates a cross-session learning mechanism separate from the existing memory system.

**When:** Any role that synthesizes outcomes and feeds forward.

**Why:** The existing Reflection Analyst writes to memory banks (long-term learning). EOD Review writes to a structured daily file (short-term operational feedback). These serve different purposes and should remain separate.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Agent Proliferation

**What:** Adding a new agent for every conceivable trading desk role.
**Why bad:** Each agent adds API cost, latency, and coordination complexity. A 20-agent pipeline is slower and more expensive than a 14-agent one, without proportional quality improvement.
**Instead:** Merge related functions. Morning Brief + Macro Strategist could be one agent initially. Compliance could be a code module before becoming an agent.

### Anti-Pattern 2: Deep Agent Chains

**What:** Agent A calls Agent B calls Agent C in a serial chain with no parallelism.
**Why bad:** Multiplies latency. If CIO waits for Macro Strategist which waits for Morning Brief, that is 3 sequential LLM calls before the real pipeline even starts.
**Instead:** Run Morning Brief and Macro Strategist in parallel. CIO reads both outputs. This matches real-world desks where the macro strategist prepares their view independently of the morning brief coordinator.

### Anti-Pattern 3: Overriding Existing Decisions

**What:** New roles that re-do work existing agents already handle (e.g., a Portfolio Strategist that re-runs risk checks the Risk Manager already did).
**Why bad:** Creates confusion about which agent's output is authoritative. Can lead to conflicting guidance.
**Instead:** Each role has a clear, non-overlapping responsibility. Portfolio Strategist handles cross-position correlation; Risk Manager handles individual position limits. No overlap.

## Parallelization Opportunities

| Parallel Group | Agents | Why Parallelizable |
|----------------|--------|--------------------|
| Pre-market | Morning Brief + Macro Strategist | Independent data sources, both feed CIO |
| Analysis (existing) | Market + Technical + Sentiment Analyst | Independent per-symbol analysis |
| Post-execution | Reporter + EOD Review + Reflection | Independent review perspectives |

## Sources

- Existing system architecture: `.planning/codebase/ARCHITECTURE.md`
- [TradingAgents Framework Architecture](https://arxiv.org/html/2412.20138v5) -- Multi-agent pipeline design patterns
