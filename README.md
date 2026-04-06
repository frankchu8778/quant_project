# 量化研究專案
## 目標與背景
這個專案的核心目標是把**台股（日頻 + 分鐘）資料**整理成可回測/可因子研究的資料層，並且能夠「每天增量更新」。
- **日頻資料主軸**：以 TEJ 來源的日資料為主，清洗後輸出成一致 schema，並 dump 成 Qlib 可讀取的資料庫格式（bin）。
- **分鐘資料主軸**：以 FinMind（與部分 Shioaji 測試）抓取分鐘 K 線，使用任務化方式批次下載並能在 Raspberry Pi 上跑完。
- **因子研究主軸**：提供一個 FactorEngine 封裝層，用表達式（alphagen）+ Qlib 資料，快速做因子計算與資料載入。
> 註：資料目錄與產物（如 raw data、processed parquet、分鐘資料等）在 `.gitignore` 中被忽略；Github僅留「程式碼與流程設計」，不把這些資料檔當成版本庫內容。
## 完成項目
### 1) TEJ 日資料：清洗、檢核與公司行為處理
位置：`src/manage_database/TW_stock/check_tej_data_daily.py`
- **資料清洗與欄位統一**：將 TEJ 原始欄位 rename 成統一欄位（open/high/low/close/volume 等），並輸出 parquet 作為「每日可重現」的處理結果。
- **一致性檢核**：
  - 檢查當日股票清單與交易所股票清單差異，必要時用 FinMind 做「第二層複查」避免漏資料。
  - 針對處置/全額交割等狀態產出 `is_disposed`、`is_tradable`。
- **公司行為（除權息/減資）復權因子**：
  - 產出 `adj_factor_price` / `adj_factor_volume`。
  - **減資延後寫入機制**：減資第一天先寫入 `setting_files/capital_reduction_pending.json`，等恢復交易日再把調整因子寫回當日資料，避免停牌期間無日資料造成錯位。
### 2) Master Map（類別欄位編碼）維護，確保 Qlib 特徵可用
位置：`setting_files/*.json`、`src/manage_database/TW_stock/rebuilde_qlib.py`（以及日清洗流程同步邏輯）
- 針對 `exchange / industry / subindustry` 等類別欄位維護 `*_master_map.json`。
- 支援「新類別自動加入」並寫回 JSON，讓後續 dump 到 Qlib 時能維持**穩定編碼**。
- 在 `rebuilde_qlib.py` 中增加對「已是數值編碼」資料的容錯，避免重複分配造成編碼漂移。
### 3) Qlib 資料庫：全量重建 + 每日增量更新（含防呆）
位置：
- 全量重建：`src/manage_database/TW_stock/rebuilde_qlib.py`
- 每日增量：`src/manage_database/TW_stock/daily_update_data.py`
- **全量重建**：從已清洗的 TEJ parquet 彙整成 DataFrame，透過 `DumpDataAllFromDataFrame` dump 成 Qlib bin。
- **每日增量更新**：使用 `DumpDataUpdateFromDataFrame` 只寫入新的一天。
- **防重複寫入**：每日更新前先檢查 `calendars/day.txt`，若該日期已存在就直接中止，避免 calendar/feature 被重複 append。
### 4) 分鐘資料下載：任務化、可在 Pi 上跑、具限速與斷點續跑
位置：
- 任務產生：`src/manage_database/TW_stock/generate_task.py`
- 主機版抓取（並行 + 限速 + Telegram 通知）：`src/manage_database/TW_stock/get_min_finmind.py`
- Raspberry Pi 版（記憶體友善 + 分批 flush parquet）：`src/manage_database/TW_stock/get_min_finmind_pi.py`
我把分鐘資料的抓取做成「可重跑、可切批、可移動到低功耗設備」的流程：
- **任務產生器**：
  - 從 Qlib calendars 與 instruments 讀出「某一天應該抓哪些股票」。
  - 若該日 parquet 已存在就跳過，避免重抓。
  - 產出 `pi_task/YYYY-MM-DD.json`，可直接複製到 Raspberry Pi 執行。
- **Pi 端下載器設計**：
  - 內建 RateLimiter + retry，避免 API 限速/Not ready。
  - 下載過程定期 flush 成暫存 parquet，最後 merge，避免記憶體暴衝。
  - 以「輸出 parquet 是否存在」判斷任務完成，天然支援斷點續跑。
### 5) 因子計算封裝與加速初始化(GPU 加速)
位置：`src/factor_engine/engine.py`、`src/config.py`、`src/my_extensions/*`
- **FactorEngine**：封裝 alphagen expression parser + Qlib StockData，支援：
  - 字串表達式解析（如 `Mean($close, 20)`）→ tensor / DataFrame
  - 載入原始特徵做研究（例如分鐘抓取任務會讀 `$is_tradable` 作為過濾條件）
- **Qlib 快速初始化**：`init_qlib_fast()` 會優先使用 RAMDisk（`/dev/shm/qlib_ram`），在研究/批次運算時降低 I/O 成本。
- **自訂/對齊算子**：
  - `src/my_extensions/custom_ops.py`：新增橫截面 rank、scale、signed power、rolling prod 等研究常用算子。
  - `src/my_extensions/rename_ops.py`：把常見 WQ 命名對齊到 Qlib（例如 `Delay`, `Ts_Rank`），降低搬公式的摩擦。
## 資料流程（我設計的 end-to-end pipeline）
### 日頻（TEJ → processed parquet → Qlib）
1. 取得當日 TEJ 資料（原始檔可能含壓縮/不同編碼）。
2. 執行清洗與檢核（產出 `is_tradable / is_disposed / adj_factor_*`，並同步 master map）。
3. 輸出當日 processed parquet。
4. 用每日增量 dumper 更新 Qlib，並防呆避免重複寫入 calendar。
### 分鐘（Qlib instruments/day → 任務 JSON → FinMind → parquet）
1. 從 Qlib 的 `calendars/day.txt` 與 `instruments/all.txt` 產生日任務。
2. 任務搬到 Raspberry Pi。
3. Pi 端依任務逐日抓取，具限速/重試/flush/斷點續跑。
4. 需要時用 Telegram 發送進度通知（長時間任務可觀測）。
## 設計決策備忘
- **為什麼要 master map？**：Qlib bin 需要數值特徵；對類別欄位用固定編碼才能保證歷史一致性與可重現。
- **怎麼處理減資/停牌造成的時間對齊問題？**：用 pending 機制把「第一天計算、恢復交易日落地」拆開，避免把因子寫到不存在的交易日。
- **如何避免資料重複/污染？**：增量更新前先檢查 calendar；分鐘任務用輸出檔存在性判斷完成，天然 idempotent。
- **如何控制 API 限速與穩定性？**：RateLimiter + retry（針對 Not ready），並行數可調；Pi 端用 flush/merge 控制記憶體峰值。
- **效能怎麼做？**：RAMDisk 優先、n_jobs 合理並行、下載端分批落盤。
## 技術棧摘要
- **語言/環境**：Python >= 3.10（PDM/pyproject 管理）
- **資料處理**：pandas、pyarrow、numpy、duckdb
- **資料源**：TEJ（日）、FinMind（分）、Shioaji（分，測試/備援）
- **量化框架**：Qlib（dump_bin）、alphagen（expression engine）
- **可靠性/運維**：RateLimiter + retry、Telegram 通知、RAMDisk I/O 加速