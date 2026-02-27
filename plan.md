# Agent 架構重組計畫

## 目標
將目前扁平的 `agents/` 目錄重組為類似 TradingAgents 的分類結構，提取可重用的 skill.md 技能檔案，並透過 subagent 機制減少 teammate 數量以提升效率。

---

## 一、新目錄結構

```
agents/
├── analysts/                      # 數據收集型 agents
│   ├── market_analyst.md
│   ├── technical_analyst.md
│   ├── sentiment_analyst.md
│   ├── fundamentals_analyst.md
│   └── symbol_screener.md
├── researchers/                   # 投資辯論 agents
│   ├── bull_researcher.md
│   ├── bear_researcher.md
│   └── research_judge.md
├── risk_mgmt/                     # 風控系統 agents
│   ├── risk_manager.md
│   ├── aggressive_analyst.md
│   ├── conservative_analyst.md
│   ├── neutral_analyst.md
│   └── risk_judge.md
├── trader/                        # 決策 & 執行
│   ├── decision_engine.md
│   ├── position_reviewer.md
│   └── executor.md
├── reporting/                     # 報告
│   └── reporter.md
├── reflection/                    # 反思 & 記憶
│   └── reflection_analyst.md
└── skills/                        # 可重用技能（供所有 agent 參考）
    ├── fetch_market_data.md
    ├── compute_technical_signals.md
    ├── analyze_sentiment.md
    ├── screen_symbols.md
    ├── fetch_fundamentals.md
    ├── assess_risk.md
    ├── review_positions.md
    ├── place_order.md
    ├── send_notification.md
    ├── search_memory.md
    └── manage_shared_state.md
```

---

## 二、Agent 角色分類：Teammate vs Subagent vs Lead 直接執行

### 設計原則
- **Full Teammate** = 需要 LLM 推理、獨立思考、產出文字論述的 agent
- **Subagent (Task tool)** = 純 Python 規則執行，不需要 LLM 推理，用 Task tool spawn 即可
- **Lead 直接執行** = 極簡操作，Lead agent 直接呼叫 Python 函數

### 分類結果

| Agent | 類型 | 理由 |
|-------|------|------|
| Symbol Screener | **Subagent** | 純 Python 規則篩選，不需 LLM |
| Market Analyst | **Subagent** | 純 Python 計算 market_score + regime |
| Technical Analyst | **Subagent** | 純 Python 計算 RSI/MACD/BB/EMA |
| Sentiment Analyst | **Subagent** | 純 Python VADER NLP，不需 LLM |
| Position Reviewer | **Subagent** | 純 Python 4-factor 加權計算 |
| Decision Engine | **Lead 直接執行** | 純 Python 分數聚合，Lead 跑就好 |
| Fundamentals Analyst | **Subagent** | 純 Python yfinance 抓取 |
| Risk Manager | **Subagent** | 純 Python 硬性規則檢查 |
| Executor | **Subagent** | 純 API 呼叫下單 |
| Reporter | **Subagent** | 純 Telegram API 呼叫 |
| **Bull Researcher** | **Teammate** | 需要 LLM 推理產出看多論點 |
| **Bear Researcher** | **Teammate** | 需要 LLM 推理產出看空論點 + 反駁 |
| **Research Judge** | **Teammate** | 需要 LLM 推理裁決 + score_adjustment |
| **Aggressive Analyst** | **Teammate** | 需要 LLM 推理產出激進觀點 |
| **Conservative Analyst** | **Teammate** | 需要 LLM 推理產出保守觀點 |
| **Neutral Analyst** | **Teammate** | 需要 LLM 推理產出平衡觀點 |
| **Risk Judge** | **Teammate** | 需要 LLM 推理裁決 qty_ratio |
| **Reflection Analyst** | **Teammate** | 需要 LLM 推理萃取教訓 |

### 效率提升
- **原本**: 15+ teammates（每個 agent 一個 teammate）
- **重組後**: 最多 8 個 teammates（僅 LLM 辯論/反思 agents），其餘用 subagent 或 Lead 直接執行
- Phase 1 的 3 個 data collection agents 可以用 3 個並行 subagent 取代 3 個 teammate

---

## 三、Skill 技能檔案設計

每個 skill.md 描述一個可重用的工具能力，包含：用途、呼叫方式、輸入/輸出格式。

### 技能清單

| Skill | 檔案名 | 對應 Python 函數 | 使用者 |
|-------|--------|-----------------|--------|
| 取得市場行情 | `fetch_market_data.md` | `task_market_analyst()` | Market Analyst, Position Reviewer |
| 計算技術指標 | `compute_technical_signals.md` | `task_technical_analyst()` | Tech Analyst, Position Reviewer |
| 情緒分析 | `analyze_sentiment.md` | `task_sentiment_analyst()` | Sentiment Analyst |
| 篩選標的 | `screen_symbols.md` | `task_symbol_screener()` | Screener |
| 取得基本面 | `fetch_fundamentals.md` | `task_fundamentals_analyst()` | Fundamentals Analyst |
| 風控評估 | `assess_risk.md` | `task_risk_manager()` | Risk Manager |
| 持倉審查 | `review_positions.md` | `task_position_review()` | Position Reviewer |
| 下單執行 | `place_order.md` | `task_execute_trades()` / `task_execute_exits()` | Executor |
| 發送通知 | `send_notification.md` | `task_send_report()` | Reporter |
| 記憶搜尋 | `search_memory.md` | `SituationMemory.search()` | 辯論 agents, Reflection |
| 共享狀態管理 | `manage_shared_state.md` | `_save_state()` / JSON read | 所有 agents |

---

## 四、需要修改的檔案

### 4.1 移動 agent .md 檔案
- `agents/*.md` → 按上述目錄結構移動到子目錄
- 每個 .md 檔頂部加入 `## 可用技能` 區塊，引用對應的 skill.md

### 4.2 新建 11 個 `agents/skills/*.md` 技能檔
- 每個 skill 檔描述：用途、Python 呼叫方式、輸入參數、輸出格式、使用範例

### 4.3 更新 `src/agents_launcher.py`
- 更新 `AGENT_TEAMS_PROMPT` 以反映新的目錄結構
- 將 Phase 1 agents 改為 subagent 模式（Lead 用 Task tool spawn）
- 將 Phase 0, 1.5, 3, 4, 5 改為 subagent 或 Lead 直接呼叫
- 僅 Phase 2.5, 3.5, 6 保留 full teammate

### 4.4 更新 `CLAUDE.md`
- 更新目錄結構描述
- 新增 skills 區塊說明

### 4.5 更新 agent .md 中的路徑引用
- 所有 agent spec 中引用其他 agent 的路徑需更新

---

## 五、實作步驟

1. **建立新目錄結構** — 建立 `agents/{analysts,researchers,risk_mgmt,trader,reporting,reflection,skills}/` 子目錄
2. **移動 agent spec 檔案** — 將 18 個 .md 從 `agents/` 移到對應子目錄
3. **撰寫 11 個 skill.md** — 在 `agents/skills/` 下建立所有技能檔
4. **更新 agent spec 內容** — 每個 agent .md 加入可用技能引用，更新路徑
5. **重寫 AGENT_TEAMS_PROMPT** — 反映新的 teammate/subagent 分類和目錄結構
6. **更新 CLAUDE.md** — 更新架構說明
7. **驗證** — 確認所有路徑引用正確、`--prompt` 輸出正確

---

## 六、新版 AGENT_TEAMS_PROMPT 架構概覽

```
Phase 0:  Lead spawn subagent → task_symbol_screener()
Phase 1:  Lead spawn 3 個並行 subagents → market + tech + sentiment
Phase 1.5: Lead spawn subagent → task_position_review() + task_execute_exits()
Phase 2:  Lead 直接執行 → task_generate_decisions()
Phase 2.5: Lead spawn subagent (fundamentals) + spawn teammates (bull/bear/judge per symbol)
Phase 3:  Lead spawn subagent → task_risk_manager()
Phase 3.5: Lead spawn teammates (aggressive/conservative/neutral/judge per symbol)
Phase 4:  Lead spawn subagent → task_execute_trades()
Phase 5:  Lead spawn subagent → task_send_report()
Phase 6:  Lead spawn teammates (reflection per trade)
```

只有 Phase 2.5、3.5、6 需要 full teammates（LLM 推理）。
其餘全部由 Lead 直接執行或 spawn 輕量 subagent。
