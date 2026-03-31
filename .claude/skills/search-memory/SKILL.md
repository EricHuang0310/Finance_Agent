---
name: search-memory
description: Use when discussing BM25 memory search, past trade lessons, situation memory, memory banks (bull/bear/judge), or when needing to understand how the reflection-memory loop works
user-invocable: false
---

# 技能：記憶搜尋

> 使用 BM25 相似度搜尋過去交易的經驗教訓。

## 用途
- 在辯論/風控/反思前，搜尋過去類似情境的教訓
- 為每個 agent 角色提供歷史經驗參考
- 避免重複過去的錯誤

## 記憶庫
系統維護 5 個獨立的 BM25 記憶庫：

| 記憶庫 | 使用者 | 存放內容 |
|--------|--------|---------|
| `bull_memory` | Bull Researcher | 過去看多分析的教訓 |
| `bear_memory` | Bear Researcher | 過去看空分析的教訓 |
| `research_judge_memory` | Research Judge | 過去裁決的教訓 |
| `risk_judge_memory` | Risk Judge | 過去風控決策的教訓 |
| `decision_engine_memory` | Decision Engine | 一般信號聚合的教訓 |

## 搜尋方式
記憶搜尋由 debate helper 自動進行。在準備辯論上下文時，系統會：
1. 將當前情境（技術面、情緒面、市場環境）組成搜尋查詢
2. 用 BM25 匹配最相似的過去 2 筆情境
3. 將教訓放入 `debate_context_{symbol}.json` 的 `past_memories_*` 欄位

```python
# 由 debate helpers 自動呼叫
from src.agents_launcher import task_prepare_debate
context = task_prepare_debate(symbol)
# context["past_memories_bull"] = [lesson1, lesson2]
# context["past_memories_bear"] = [lesson1, lesson2]
# context["past_memories_judge"] = [lesson1, lesson2]
```

## 底層 API
```python
from src.memory.situation_memory import SituationMemory

memory = SituationMemory("bull_memory", "memory_store")
results = memory.search("RSI 65 bullish MACD cross EMA alignment", top_k=2)
# results: [{"matched_situation": "...", "lesson": "...", "score": 0.85}]
```

## 記憶持久化
- 儲存路徑：`memory_store/{name}.json`
- 格式：`{"entries": [{"situation": "...", "lesson": "..."}]}`

## 使用此技能的 Agent
- Bull Researcher, Bear Researcher（透過 `past_memories_bull/bear`）
- Research Judge（透過 `past_memories_judge`）
- Risk Judge（透過 `past_memories_risk`）
- Reflection Analyst（寫入教訓到記憶庫）
