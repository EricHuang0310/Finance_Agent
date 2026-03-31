# Domain Pitfalls: Adding Trading Desk Roles to AI Agent System

**Domain:** Multi-agent AI trading desk role additions
**Researched:** 2026-03-30

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Agent Proliferation Tax

**What goes wrong:** Adding too many agent roles simultaneously creates a pipeline that is slow, expensive, and hard to debug. Each new Teammate (LLM-reasoning) agent adds 10-30 seconds of latency and significant API cost. A pipeline with 8 new agents could double the total runtime and cost.

**Why it happens:** It feels productive to design all roles at once. The TradingAgents framework has 10+ agent types, making it seem like more is better. But that framework runs on local models with no per-token cost.

**Consequences:** Pipeline becomes too slow for daily one-shot execution window (market hours are finite). API costs escalate beyond what paper trading justifies. Debugging failures across 20+ agents becomes intractable.

**Prevention:** Add roles incrementally -- 2-3 per milestone. Measure latency and cost after each addition. Set a hard budget ceiling (e.g., $X per daily run) and a hard latency ceiling (e.g., 15 minutes total pipeline). If a new role pushes past either, downgrade its model tier or merge it with another role.

**Detection:** Track per-run cost and latency as first-class metrics from day one. If total pipeline time exceeds 10 minutes or cost exceeds the set threshold, stop adding roles.

### Pitfall 2: CIO Agent Becomes a Bottleneck or Rubber Stamp

**What goes wrong:** The CIO agent either (a) always says "normal" stance making it useless, or (b) is too conservative and blocks trading on most days, preventing the system from generating returns.

**Why it happens:** LLMs tend toward hedging and moderate language. Without careful prompt engineering and calibration, the CIO will default to "proceed with caution" every day. Alternatively, if fed too much risk data, it becomes overly defensive.

**Consequences:** If rubber stamp: wasted API cost for zero decision-quality improvement. If too conservative: system stops trading and the momentum strategy cannot capture trends.

**Prevention:**
- Calibrate the CIO prompt with historical data: feed it past market conditions and verify its stances match what would have been profitable.
- Define explicit stance categories with concrete triggers (not vague thresholds): "defensive" means VIX > 25 AND yield curve inverted, not just "things look uncertain."
- Include a performance feedback loop: if CIO's "sit-out" calls consistently miss profitable days, the EOD Review flags this pattern.
- Start with a narrow scope: CIO only controls risk_budget_multiplier (0.5-1.5x), not individual trade decisions.

**Detection:** Track CIO stance distribution over 30 days. If >80% "normal" or >40% "sit-out", the agent needs recalibration.

### Pitfall 3: Conflicting Veto Chains

**What goes wrong:** CIO says "defensive but trade," Risk Manager approves trade at reduced size, then Compliance Officer rejects it for a different reason. The pipeline produces zero trades despite all agents nominally allowing trading. Multiple gatekeepers create an implicit "AND" gate that is stricter than any individual gate.

**Why it happens:** Each gatekeeper role is designed independently with its own rejection criteria. When composed in series, the combined rejection rate is the product of individual pass-through rates.

**Consequences:** System rarely trades. Momentum strategy requires being *in* the market to capture trends. Over-conservative combined gates destroy the strategy's edge.

**Prevention:**
- Model the combined pass-through rate mathematically. If CIO passes 80%, Risk passes 70%, and Compliance passes 90%, the combined rate is 0.8 x 0.7 x 0.9 = 50.4%. Design each gate's thresholds knowing the compound effect.
- Give each gate a clear, non-overlapping concern: CIO = strategic stance, Risk = position/portfolio limits, Compliance = regulatory rules. No overlap means no double-counting.
- Track the "rejection funnel" in Reporter output: how many candidates enter each gate, how many exit.

**Detection:** If overall trade approval rate drops below 30% of candidates that score above threshold, the veto chain is too restrictive.

## Moderate Pitfalls

### Pitfall 4: Macro Strategist Hallucinates Market Data

**What goes wrong:** The Macro Strategist, being an LLM teammate rather than a code-executing subagent, generates plausible-sounding but factually wrong macro claims ("the 10Y yield is at 5.2%" when it is actually 4.1%).

**Prevention:** The Macro Strategist must call code to fetch actual data (bond yields, VIX level, sector performance) before reasoning about it. Its prompt must mandate: "Always execute the data retrieval code first. Never state a market number from memory." Alternatively, make it a hybrid: subagent fetches data, then teammate reasons about it.

### Pitfall 5: Shared State File Explosion

**What goes wrong:** Adding 7 new roles means 7 new JSON files per daily run in `shared_state/`. With symbol-specific files (e.g., `debate_context_{symbol}.json` pattern), this could mean 50+ files per day. The state directory becomes hard to navigate and debug.

**Prevention:** Consolidate where possible. New roles should write to themed files, not per-role files. For example, all pre-market outputs could go in one `pre_market.json` with sections for brief, macro, and directive. Keep the per-symbol pattern only where genuinely needed (debate files).

### Pitfall 6: EOD Review Creates Circular Reasoning

**What goes wrong:** EOD Review writes "we should have been more aggressive yesterday" -> Morning Brief surfaces this -> CIO becomes aggressive -> positions lose money -> EOD Review writes "we should have been more conservative" -> cycle repeats. The system oscillates between aggressive and defensive without converging.

**Prevention:** EOD Review insights should be framed as observations, not directives. CIO should weight EOD observations alongside macro data and regime detection, not treat them as instructions. Include a "confidence decay" -- yesterday's EOD insight has weight 1.0, two days ago has 0.5, three days ago has 0.25.

### Pitfall 7: Sector Specialist Scope Creep

**What goes wrong:** Sector Specialist tries to become a full fundamental analyst, duplicating work that the Fundamentals Analyst and Bull/Bear researchers already do. Its output becomes a second opinion rather than unique sector intelligence.

**Prevention:** Define Sector Specialist's scope narrowly: supply chain dynamics, sector-specific catalysts (earnings season, regulatory decisions), and cross-name correlation within the sector. It should NOT re-analyze individual company fundamentals.

## Minor Pitfalls

### Pitfall 8: Model Tier Misassignment

**What goes wrong:** Assigning Opus to a role that only needs Sonnet, or Haiku to a role that needs genuine reasoning. Wastes money in the first case, produces poor decisions in the second.

**Prevention:** Start all new roles at Sonnet. Upgrade to Opus only if output quality is demonstrably insufficient. Downgrade to Haiku only if the role proves to be purely rule-based in practice. Track decision quality per role.

### Pitfall 9: Chinese-English Spec Inconsistency

**What goes wrong:** Existing agent specs are in Chinese. New role specs might be written in English. Mixed-language specs create cognitive overhead for maintainers and can confuse Claude when referencing other agents' behavior.

**Prevention:** Write new specs in the same language as existing ones (Chinese), or commit to translating all specs to one language. Do not mix.

### Pitfall 10: Forgetting to Update Decision Engine Weights

**What goes wrong:** Adding new upstream roles (CIO, Macro Strategist) that produce signals, but the Decision Engine's composite scoring formula does not incorporate them. The new roles run but their output is ignored by the scoring math.

**Prevention:** For each new role, explicitly define how its output integrates into the existing scoring/decision pipeline. Document this in the role's spec AND in the Decision Engine's spec.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Adding CIO role | Rubber stamp or over-conservative (Pitfall 2) | Calibrate with historical data, narrow scope initially |
| Adding Macro Strategist | Data hallucination (Pitfall 4) | Mandate code execution for data retrieval |
| Adding multiple gatekeepers | Conflicting veto chains (Pitfall 3) | Model combined pass-through rate, non-overlapping concerns |
| Adding EOD Review | Circular reasoning (Pitfall 6) | Frame as observations not directives, confidence decay |
| Adding all roles at once | Agent proliferation tax (Pitfall 1) | Incremental addition, cost/latency tracking |
| Portfolio Strategist | Overlap with Risk Manager | Clear boundary: correlation vs position limits |
| Compliance Officer | Over-engineering for paper trading | Defer to live trading readiness phase |

## Sources

- System analysis: existing agent specs and architecture docs
- [TradingAgents performance analysis](https://arxiv.org/abs/2412.20138) -- multi-agent coordination challenges
- Institutional trading desk best practices from web research
