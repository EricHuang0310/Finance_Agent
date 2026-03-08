# Agent Team 審閱修改紀錄

審閱者角色：金融交易室團隊領導（Trading Desk Head）
審閱日期：2026-03-07
策略定位：美股量化動能策略，持倉週期日內至數週
修改目標：使 agents_v2/ 指令集更貼近真實交易室運作標準

---

## 角色完整性比對

| Pipeline Phase | Agent | 對應交易室角色 | 完整度（修改前） | 完整度（修改後） |
|---|---|---|---|---|
| Phase 0 | Symbol Screener | Quant (篩選層) | 60% — 缺流動性品質、sector 分散 | 85% |
| Phase 1 | Market Analyst | Macro Strategist | 50% — 缺跨資產分析、regime 深度 | 85% |
| Phase 1 | Technical Analyst | Quant Analyst | 65% — 缺 ADX、volume 確認、confidence | 90% |
| Phase 1 | Sentiment Analyst | Research Analyst (情緒) | 40% — 缺催化劑識別、noise 過濾 | 75% |
| Phase 1 | Fundamentals Analyst | Research Analyst (基本面) | 45% — 只有原始數據、無分析 | 80% |
| Phase 1.5 | Position Reviewer | PM + Risk (退出) | 70% — 缺時間衰減、事件風險 | 90% |
| Phase 1.8 | Market Regime | Macro Strategist (regime) | — (在 Market Analyst 中) | 85% |
| Phase 2 | Decision Engine | Portfolio Manager | 65% — 缺信號衝突處理、催化劑傳遞 | 85% |
| Phase 2.5 | Bull/Bear/Judge | 投資委員會辯論 | 60% — 缺結構化框架、品質標準 | 85% |
| Phase 3 | Risk Manager | Risk Manager | 55% — 缺 sector 集中度、情境風控、config 不一致 | 90% |
| Phase 4 | Executor | Trader (執行) | 50% — 缺時段限制、流動性、滑價 | 85% |
| Phase 5 | Reporter | Reporting / COO | 55% — 缺風控儀表板、策略健康度 | 80% |
| Phase 6 | Reflection | Performance Analyst | 55% — 缺績效歸因、策略衰減偵測 | 85% |

---

## 修改摘要

### Symbol Screener (`agents_v2/analysts/symbol_screener.md`)
- [新增] 硬性門檻（Hard Filters）機制 — 真實交易室的量化篩選必有最低門檻，不只是排名
- [新增] 日均成交額門檻（$5M） — 避免高價低量或低價高量的假象
- [新增] 交易天數完整性檢查 — 排除停牌、新上市標的
- [新增] Sector 分散度控管（單一 sector ≤ 40%） — 初步避免候選名單過度集中
- [新增] 數據品質檢查章節 — API 失敗、異常值處理
- [新增] 邊界條件與 Fallback 章節 — 定義異常狀況的處理邏輯
- [強化] 評分因子增加權重分配 — 原本無權重說明，現在明確各因子佔比
- [強化] 輸出 schema 增加 `sector_distribution`、`screening_stats` — 供下游 agent 使用

### Market Analyst (`agents_v2/analysts/market_analyst.md`)
- [修正] 角色定位從「數據蒐集」升級為「宏觀策略師」 — 原本只做個股數據拉取，缺乏宏觀視角
- [新增] 跨資產環境掃描（VIX/TLT/UUP） — 真實策略師必須監控股債匯商聯動
- [新增] Regime 輔助確認指標表（VIX 水位、VIX 趨勢、TLT 趨勢、市場寬度） — 原本僅靠 SPY EMA，太單薄
- [新增] Regime 改名 `neutral` → `transitional` — 更精確反映「過渡期」的含義
- [新增] 波動率環境因子（vol_env_score） — 波動率是趨勢交易的重要脈絡
- [新增] `regime_confidence` 欄位 — 下游 agent 可據此調整行為
- [新增] Sector momentum 輸出 — 板塊資金流向是真實策略師的必備分析
- [新增] `alerts` 機制（volume_breakout、regime_change） — 異常事件即時標記
- [新增] 極端行情處理（VIX > 35 強制 risk_off） — 系統性風險預警
- [強化] 個股評分增加成交量因子權重從 0.5 調為 0.35，新增波動率環境因子 0.30

### Technical Analyst (`agents_v2/analysts/technical_analyst.md`)
- [修正] 角色定位明確為「量化分析師」 — 對應交易室 Quant 角色
- [新增] ADX 趨勢強度指標（權重 0.15） — 原本完全缺失，ADX 是判斷趨勢是否存在的關鍵工具
- [新增] 成交量確認因子（權重 0.10） — 量價配合是技術分析的基礎，原本缺失
- [新增] `confidence` 欄位與計算邏輯 — 反映指標間一致程度，低信心度信號會被 Decision Engine 降權
- [新增] MACD histogram 趨勢分析 — histogram 收縮是動能衰竭的領先指標
- [新增] ATR 合理性檢查 — 極低/極高 ATR 的警告機制
- [新增] 數據品質檢查章節 — 不足 50 根、NaN 處理、異常漲跌幅
- [修正] 權重重新分配（RSI/MACD/EMA 各 0.20，BB 0.15，ADX 0.15，Volume 0.10） — 原本四項均 0.25，加入新指標後重新平衡
- [強化] 輸出 schema 增加 `confidence`、`adx`、`macd_histogram_trend`、`volume_confirmation`、`data_quality`

### Sentiment Analyst (`agents_v2/analysts/sentiment_analyst.md`)
- [修正] 角色定位明確為「研究分析員情緒面角色」 — 對應交易室 Research Analyst
- [新增] Catalyst Identification（催化劑識別）框架 — 真實研究分析員的核心職責之一
- [新增] Noise vs Signal 判定表 — 區分有實質影響的新聞與市場噪音
- [新增] 事件日曆整合（earnings date、FOMC、CPI） — 催化劑事件是動量策略的重要風險/機會因素
- [新增] `upcoming_macro_events` 輸出 — 宏觀事件日曆供全 pipeline 參考
- [新增] `key_headlines` 輸出（含 signal/noise 標記） — 供 Bull/Bear 辯論使用
- [新增] 邊界條件（新聞源不可用、新聞數量極少、盤後 staleness） — 定義異常狀況處理
- [新增] 與下游 Agent 的關聯說明 — 明確催化劑標記如何影響 Risk Manager 和辯論 agent

### Fundamentals Analyst (`agents_v2/analysts/fundamentals_analyst.md`)
- [新增] 估值定位分析（pe_vs_sector） — 相對估值比絕對數字更有意義
- [新增] 品質指標（ROE、Operating Margin） — 獲利品質是基本面的重要維度
- [新增] Short Interest 追蹤 — 聰明錢的看空信號，對動能策略有參考價值
- [新增] Red Flags 機制（high_leverage、negative_cash_flow 等） — 結構化的風險標記
- [新增] Highlights 機制（high_growth、high_profitability 等） — 結構化的亮點標記
- [新增] 邊界條件（yfinance 失敗、指標缺失、ETF 處理） — 定義異常狀況
- [強化] Summary 從簡單描述升級為包含比較分析的完整摘要

### Decision Engine (`agents_v2/trader/decision_engine.md`)
- [修正] 角色定位明確為「投資組合經理」，擁有信號衝突裁量權 — 原本僅為分數聚合器
- [新增] 信號衝突處理表 — 定義 tech vs sentiment vs market 矛盾時的優先權規則
- [新增] Confidence 加權機制 — 低信心度技術信號自動降權
- [新增] 催化劑事件傳遞（catalyst_flag） — 從 Sentiment 傳遞到 Risk Manager
- [新增] `transitional` regime 處理（門檻 +0.1，權重 ×0.9） — 原本缺失此過渡狀態
- [新增] `risk_off` regime 下做多門檻提高至 0.6 — 熊市做多需要更強信號
- [新增] `signal_alignment` 和 `regime_conflict` 標記 — 供 Risk Manager 使用
- [新增] `skipped_symbols` 記錄 — 供事後分析為何某些標的被跳過
- [強化] 輸出 schema 增加 `regime_confidence`、`tech_confidence`、`catalyst_flag`

### Executor (`agents_v2/trader/executor.md`)
- [修正] 角色定位從「下單機器」升級為「交易員（Trader）」 — 真實交易員的職責遠超下單
- [新增] 交易時段限制（Timing Rules） — 開盤/收盤前 15 分鐘禁止新建倉，這是交易室基本紀律
- [新增] 流動性預檢（Pre-Trade Liquidity Check） — 基於訂單量 vs 日均量的衝擊評估
- [新增] 滑價預估與追蹤機制 — 預估 slippage + 記錄實際 slippage，供 Reflection 分析
- [新增] 部分成交（Partial Fill）處理邏輯 — 真實交易常見但原本完全未處理
- [新增] `market_session` 欄位 — 記錄執行時的市場時段
- [強化] Kill Switch 明確「無視時段限制」 — 緊急平倉不受任何限制
- [強化] 安全規則增加「不自動重試」 — 避免異常行情下重複下單
- [強化] 輸出 schema 增加 `fill_price`、`estimated_slippage_bps`、`actual_slippage_bps`、`partial_fill`

### Position Reviewer (`agents_v2/trader/position_reviewer.md`)
- [新增] 持有時間衰減因子（權重 0.10） — 動量策略有「保鮮期」，超過典型動能週期的持倉需重新評估
- [新增] 事件風險因子（權重 0.10） — 財報前 gap risk 是真實交易室的重要考量
- [新增] 退出緊急度分級（exit_urgency: high/normal） — 高緊急度平倉優先執行
- [新增] exit_score_breakdown 欄位 — 透明化退出決策的各因子貢獻
- [新增] Regime 切換退出加分 — 市場環境劇變是強退出信號
- [修正] 權重重新分配以容納新因子 — 趨勢反轉 0.30、動能減弱 0.20、ATR 追蹤 0.20、市場 0.10、時間 0.10、事件 0.10
- [修正] `max_positions: 10` 硬編碼 → 引用 config `risk.max_positions` — 與 config 保持一致

### Risk Manager (`agents_v2/risk_mgmt/risk_manager.md`)
- [修正] 硬性規則數值全部改為引用 `config/settings.yaml` — 原本 agent 指令中的 60%/8 個與 config 的 80%/100 個不一致
- [新增] Sector 集中度檢查（單一 sector ≤ 30%，同 sector 同向 ≤ 3 檔） — 避免相關性風險
- [新增] 情境風險檢查（催化劑事件、regime 衝突） — 根據 Decision Engine 傳來的標記動態調整
- [新增] 波動率調整倉位（Volatility-Adjusted Sizing） — 高波動標的自動縮小倉位
- [新增] Kill Switch 恢復邏輯 — 當日不可恢復、次日自動重置、連續觸發警告
- [新增] `daily_loss_limit_hit` 欄位 — 區分「停止新建倉」和「Kill Switch 全平倉」
- [新增] `sector_exposure` 在 risk_summary 中 — 透明化 sector 分佈
- [新增] `sizing_adjustments` 欄位 — 記錄倉位被調整的原因
- [新增] 「縮減」權限 — 原本只有批准/否決，新增倉位縮減選項
- [強化] 事前/事中/事後風控三層架構說明

### Bull Researcher (`agents_v2/researchers/bull_researcher.md`)
- [新增] 結構化論述框架（4 個維度，依優先級排序） — 確保每次辯論涵蓋所有關鍵維度
- [新增] 品質標準（必須引用數字、連結趨勢邏輯、承認不確定性） — 避免泛泛之談
- [新增] `data_cited` 和 `risk_acknowledged` 輸出欄位 — 結構化追蹤論述品質
- [強化] 記憶教訓使用指引更具體 — 如何根據歷史教訓調整論證重點
- [強化] 動量策略定位更明確：核心問題是「為什麼趨勢會繼續？」

### Bear Researcher (`agents_v2/researchers/bear_researcher.md`)
- [新增] 結構化論述框架（5 個維度，含情境分析） — 真實風險查核員的完整分析框架
- [新增] 趨勢衰竭信號維度 — 動量策略最核心的風險
- [新增] 情境分析（Scenario Analysis） — 量化最壞情境的下行空間
- [新增] `reversal_triggers` 和 `downside_estimate` 輸出欄位 — 具體可驗證的反轉觸發條件
- [新增] 品質標準（區分概率和影響、避免萬年空頭） — 提升分析的實用性
- [強化] 記憶教訓使用更具體 — 特別處理「過度強調估值風險」的常見錯誤

### Research Judge (`agents_v2/researchers/research_judge.md`)
- [新增] 結構化評估框架（5 個維度打分表） — 避免主觀裁決，增加可重複性
- [新增] 特殊裁決情境表 — 定義常見衝突情境的處理方式
- [新增] `evaluation_scores` 輸出 — 對 Bull/Bear 各維度的量化評分
- [新增] `deciding_factor` 和 `watch_items` 輸出 — 明確裁決的關鍵因素和後續觀察點
- [強化] 動量策略裁決原則 — 「趨勢正在持續」本身就是看多理由
- [強化] watch_items 會傳遞給 Position Reviewer — 形成閉環

### Reporter (`agents_v2/reporting/reporter.md`)
- [修正] 角色定位升級為「COO / 營運報告主管」 — 不只轉發數據，要提供可操作的摘要
- [新增] Risk Dashboard（風控儀表板） — Kill Switch 距離、回撤、sector 集中度、滑價統計
- [新增] 策略健康度指標 — win rate、profit factor 追蹤，衰減預警
- [新增] 通知優先級分級（🔴最高 → 🟢低） — Kill Switch 警報 > 事件預警 > 一般信號
- [新增] 事件預警通知類型 — 持倉標的即將財報時主動預警
- [新增] Sector 曝險分佈 — 報告中呈現各 sector 佔比
- [新增] 距離 Kill Switch 門檻距離 — 讓使用者知道風險水位
- [新增] 邊界條件（Telegram 失敗重試、無交易活動時仍報告） — 定義異常處理
- [強化] 報告格式要求（300 字限制、emoji 標記、簡潔原則）

### Reflection Analyst (`agents_v2/reflection/reflection_analyst.md`)
- [修正] 角色定位升級為「績效分析師（Performance Analyst）」 — 對應交易室實際角色
- [新增] 績效歸因分析（Performance Attribution）6 維度 — 方向、時機、倉位、退出、執行、外部
- [新增] 信號準確度評估表 — 逐一評估每個信號源（RSI/MACD/EMA/ADX/Market/Sentiment/Regime）
- [新增] 策略衰減偵測（Strategy Decay Detection） — rolling win rate、profit factor 趨勢
- [新增] 執行品質評估 — 比較預估滑價 vs 實際滑價
- [新增] `lesson_decision_engine` 教訓 — 原本遺漏 Decision Engine 的教訓
- [新增] `attribution`、`signal_accuracy`、`strategy_health` 輸出 — 結構化歸因數據
- [強化] 教訓品質標準 — 要求「具體、可操作」而非泛泛之談

---

## 工作流程修改

### 資訊鏈路新增
1. **Sentiment → Decision Engine → Risk Manager**：催化劑標記（`catalyst_flag`）完整傳遞鏈路
2. **Technical → Decision Engine**：`confidence` 值用於加權計算
3. **Market Analyst → Risk Manager**：`sector` 資訊用於集中度檢查
4. **Research Judge → Position Reviewer**：`watch_items` 傳遞供退出評估參考
5. **Executor → Reflection**：`fill_price`、`actual_slippage_bps` 供執行品質分析

### Regime 處理升級
- `neutral` 改名為 `transitional`，增加 `regime_confidence` 欄位
- `transitional` regime 下門檻提高、權重壓抑，增加保守度
- `risk_off` 下做多門檻從 0.5 提高至 0.6
- VIX > 35 強制 `risk_off`（極端行情保護）

### Config 一致性修正
- Risk Manager 的硬性規則全部改為引用 config，不再在 agent 指令中硬編碼
- Position Reviewer 的 `max_positions` 引用 config 而非硬編碼 10

---

## 整體建議（尚未實作但建議未來加入）

### 短期（1-2 週）
1. **相關性矩陣檢查**：在 Risk Manager 中加入持倉間的相關性計算，避免高相關標的同向曝險（需要 pandas 計算 rolling correlation）
2. **Earnings Calendar API 整合**：Sentiment Analyst 目前的 earnings date 是 placeholder，建議整合 yfinance 或 Finnhub 的 earnings calendar
3. **Multi-timeframe 確認**：Technical Analyst 目前僅使用日線，建議加入 1H timeframe 作為進場時機確認

### 中期（1-2 個月）
4. **VIX 即時數據**：Market Analyst 的 VIX 分析需要穩定的數據源，建議透過 VIXY ETF 或 Alpaca 的 options data
5. **Slippage Model 校準**：Executor 的滑價預估模型需要根據歷史數據校準 base_slippage 參數
6. **Strategy Regime Detection**：Reflection Analyst 的策略衰減偵測需要足夠歷史數據（至少 20 筆已完成交易）才能有效運作

### 長期
7. **法遵模組（Compliance Agent）**：Pattern Day Trader 規則檢查、Wash Sale 規則追蹤
8. **交割結算模組（Settlement Agent）**：T+1 交割確認、資金對帳
9. **數據工程模組（Data Engineering Agent）**：API rate limit 監控、數據完整性驗證、failover 機制
