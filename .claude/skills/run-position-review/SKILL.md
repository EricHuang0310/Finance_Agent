---
name: run-position-review
description: Review existing positions for exit signals using 4-factor weighted scoring. Use when user wants to check if any positions should be closed.
user-invocable: true
---

# 技能：持倉健康檢查

> 對所有現有持倉執行 4-factor 退出評估，判斷是否該平倉。

## 執行步驟

用 Bash 工具執行以下 Python 腳本：

```bash
python -c "
from src.agents_launcher import task_market_analyst, task_technical_analyst, task_position_review
import json

# Need market + tech data first for exit scoring
print('Collecting market data for exit analysis...')
task_market_analyst()
task_technical_analyst()

print()
print('=' * 60)
print('  POSITION EXIT REVIEW')
print('=' * 60)

exits = task_position_review()

if not exits:
    print('  No positions need closing.')
else:
    print(f'  {len(exits)} position(s) flagged for exit:')
    for e in exits:
        print(f'    {e[\"symbol\"]:8s} | exit_score={e[\"exit_score\"]:.3f} | reason: {e[\"exit_reason\"]}')
    print()
    print('  Run with task_execute_exits(exits) to close these positions.')
"
```

## 輸出

- 螢幕顯示每個持倉的退出評分和建議
- `shared_state/exit_review.json` — 完整退出分析結果

## 退出評估 4 因子

| 因子 | 權重 | 說明 |
|------|------|------|
| 趨勢反轉 | 0.35 | EMA 排列變化 |
| 動量減弱 | 0.25 | RSI 離開動量區間 |
| ATR 追蹤停損 | 0.25 | 價格跌破 ATR trailing stop |
| 市場環境 | 0.15 | 大盤 regime 轉弱 |

`exit_score >= 0.5` 建議平倉。

## 注意事項

- 此技能**不會自動平倉**，僅產出建議
- 如需執行平倉，需另外呼叫 `task_execute_exits(exits)`
- 需要先有 market + tech 數據（腳本會自動執行）
