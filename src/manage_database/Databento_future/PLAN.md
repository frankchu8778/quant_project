# 美國期貨多商品原始資料管線 (NQ / CL / GC，含月選)

> 名詞依 `CONTEXT.md`（本目錄）：商品、合約、選擇權系列、標的期貨、價差、交易日。

## Context

目前 `fetch_nq_1m.py` 只能抓 NQ，商品和選擇權系列都寫死在程式裡，
輸出也散在當前目錄的實驗資料夾（`data_nq/`、`data_nq_202004/`、`data_nq_202004_v2/`）。
使用者要做 5～10 檔商品的趨勢跟蹤，先用 **NQ、CL、GC** 三檔，用 2020-03 ～ 2020-04 跑一次驗證。
研究主體是期貨；選擇權只當期貨的補充資料，所以只抓**月選**。

資料帳號是多人共用，所以管線以**商品**為單位封裝：給一個商品就抓完它的期貨、期貨價差、月選，
可以把不同商品分給不同台電腦（都是 WSL）下載，最後把資料夾複製回來合併。

**這次範圍只到原始資料**：抓取、存檔、DuckDB 查詢。換月、主力連續合約、價格調整等，
等之後拼接主力合約時再設計，這次不做。

## 已確認的決定
- 區間：`2020-03-01` ～ `2020-05-01`（不含）
- 粒度：期貨、價差、選擇權都只抓 `ohlcv-1m`
- 選擇權：每個商品只抓一個月選系列（NQ→`NQ`、CL→`LO`、GC→`OG`）；週選、月底選不抓
- 封裝單位：商品。商品之間不合併請求，互不影響
- 資料根目錄：預設 `/home/newt/quant_project/data/us/`（`/data` 已在 `.gitignore`），可用 `--data-root` 改
- 快取放記憶體（`/dev/shm`），每個（商品, 月份）驗證後即刪
- 設定檔用 YAML（環境是 Python 3.10，沒有 `tomllib`；`yaml` 已安裝）
- raw 檔只存交易所原始欄位；**交易日**不寫進檔案，在 DuckDB view 裡計算
- 時間一律 UTC；`month=` 分區依 `ts_event` 的 UTC 月份（只是存檔切法，不代表交易時段）

## 資料夾結構

```
data/us/
├── README.md                       ← 仿 data/crypto/README.md：結構、UTC、更新方式、多台電腦分工
├── raw/
│   ├── futures/bars_1m/root=NQ/month=2020-03/data.parquet
│   ├── futures/contracts/root=NQ/month=2020-03/data.parquet
│   ├── futures/spread_bars_1m/root=NQ/month=2020-03/data.parquet
│   ├── futures/spread_contracts/root=NQ/month=2020-03/data.parquet
│   ├── options/bars_1m/root=NQ/month=2020-03/data.parquet
│   └── options/contracts/root=NQ/month=2020-03/data.parquet
└── metadata/
    ├── manifest/root=NQ/month=2020-03.parquet   一個（商品, 月份）一個小檔
    └── us.duckdb                                只放 view
```

一個（商品, 月份）的所有檔案由同一次處理產生；重抓同月就覆蓋，不會重複。
manifest 也按（商品, 月份）分檔，所以多台電腦各自跑完後，直接把 `data/us/` 複製（rsync）過來即可，
路徑不重疊、不需要合併程式；複製後在本機重跑 `init_duckdb.py`（view 用本機絕對路徑）。

manifest 欄位：`root, month, kind, rows, contracts, fetched_at, status, error`，
每個（商品, 月份）檔內每個 kind（futures / spreads / options）一列。

### 快取（放記憶體，每個（商品, 月份）驗證後即刪）
- 預設位置 `/dev/shm/databento_cache/<root>/<YYYY-MM>/`，可用 `--cache-dir` 改。
- 啟動時檢查 `/dev/shm` 剩餘空間，不足 2 GB 就停下並提示。
- 寫入 Parquet（`.part` → 改名）→ 讀回核對筆數與合約數 → 寫 manifest → **刪除該快取資料夾**。
  失敗或中斷時保留快取，重跑同指令即接續。

## 程式結構（都在 `src/manage_database/Databento_future/`）

| 檔案 | 內容 |
|---|---|
| `products.yaml` | 商品設定（見下） |
| `databento_client.py` | 從 `fetch_nq_1m.py` 搬出：`get_range`（重試、rate limit、快取、`stype_in`）、`_wait_for_reset`、`_parse_jsonl`、`_ts`、`_px`、`_clean_definitions`、`_sample_days` |
| `fetch.py` | CLI：`--products NQ,CL,GC --start --end [--force] [--cache-dir] [--data-root]`；核心是 `fetch_product(root, month)`，多個商品就逐一呼叫 |
| `init_duckdb.py` | 建立 `metadata/us.duckdb` 與 view |
| `test_pipeline.py` | 純函式的 pytest（與 `src/alphas/test_*.py` 一樣放在同目錄） |

`fetch_nq_1m.py` 和 `data_nq*` 實驗資料夾先保留，新管線驗證通過、使用者確認後再刪。

### `products.yaml`

```yaml
defaults:
  dataset: GLBX.MDP3

products:
  NQ:
    name: E-mini Nasdaq-100
    options:
      NQ: 季選 + 序列月選（第三個週五到期）
  CL:
    name: WTI Crude Oil
    options:
      LO: 月選
  GC:
    name: Gold
    options:
      OG: 月選
```

`options` 只決定**要請求哪些選擇權系列**和人看的說明；選擇權合約屬於哪個商品由標的期貨決定（見流程第 6 步）。
換月規則、合約月份循環等，等之後做主力合約時再加進設定檔。

## 抓取流程（`fetch_product(root, month)`）

每個（商品, 月份）`[m, m+1)` 一次處理，**同一商品的期貨和選擇權 parent 合併成一次請求**（例如 `NQ.FUT,NQ.OPT`）：

1. 讀 manifest：`complete` 跳過（除非 `--force`）；`partial`、`failed`、不存在則處理。
2. definition：起始日 + 每個星期一各抓 1 天快照；合併失敗時逐一請求的退回機制保留。
3. `ohlcv-1m`：整個月 1 次請求。
4. 補漏：K 線裡出現、快照裡沒有的 `(instrument_id, symbol)`，用 instrument_id 補抓定義，
   **補回來的定義只保留 `(instrument_id, raw_symbol)` 確實出現在 K 線中的那幾筆**。
   原因：CME 會重新分配 instrument_id，以 id 查整個月會把同一 id 的舊身分也抓回來
   （實例：v2 的 id 345301 4/10 前是 `2SFJ0 P1100` 瑞郎選擇權，4/29 起才是 `QNEM0 C9710`）。
5. 對接：以 `(instrument_id, symbol)` join；依 instrument_class 分成三類：
   - 期貨合約（F）→ `futures/bars_1m`、`futures/contracts`
   - 期貨價差（期貨 parent 裡的 S，或 `-`／`UD:` 代碼且對不到定義者）→ `futures/spread_bars_1m`、`futures/spread_contracts`
   - 選擇權合約（C / P）→ `options/bars_1m`、`options/contracts`
   - 選擇權組合單（選擇權 parent 裡的 `UD:`／T 等）→ 丟棄，印出筆數
   - 對不到定義的單一合約保留並警告（合約資訊為 null）。
6. 選擇權的商品歸屬：用 `underlying` 對本月期貨合約表的 `raw_symbol`，取該期貨的 `asset` 當作商品；
   與 `products.yaml` 寫的商品不一致、或對不到標的期貨時發警告。
7. 依 `ts_event` 排序，各類先寫 `.part` 再改名；讀回核對後寫 manifest
   （月份已結束 → `complete`，否則 `partial`），然後刪快取。

錯誤處理：
- 429 等額度重置；5xx／斷線最多重試 8 次（維持現狀）。
- 其他 4xx **不再回傳空結果**，改為拋錯：該（商品, 月份）的 manifest 記 `status=failed`，
  `error` 存 HTTP 狀態碼與回應內容，不寫 Parquet、不刪快取，重跑時接續。
- 只有請求成功且確實回傳 0 筆時才記 `complete, rows=0`，且不產生 Parquet 檔。

價格一律照交易所原值存（含 CL 2020-04-20 的負價、負履約價），不做任何調整。

**回應上限**：此代理每次回應最多 10 萬筆，超過的直接截掉、不報錯（實跑發現 CL 2020-03 期貨只回到 3/5）。
所有請求經 `get_all()`：回應剛好 10 萬筆就把時間區間切半重抓，切到 1 小時仍滿則報錯。

請求數：期貨與選擇權 K 線分開請求（才能分辨對不到定義的 `UD:` 屬於期貨價差還是選擇權組合單）。
NQ 每月約 8 次；CL 期貨含價差每月約 80 萬根，切半後每月 K 線約 20 多次請求。

## DuckDB（`init_duckdb.py`）

在 `data/us/metadata/us.duckdb` 建 view（路徑用本機絕對路徑，資料搬到別台後重跑即可）：
- `fut_bars`、`opt_bars`、`fut_spreads`：`read_parquet('.../raw/{kind}/.../**/*.parquet', hive_partitioning=true)`，
  並加上 `trade_date` = `(ts_event 轉 America/Chicago + 7 小時).date()`。
  已知限制：假日提前收盤的時段會標錯（例如 Memorial Day 週日晚到週一中午的時段，CME 歸週二，此規則標週一）；
  要修只改 view，不用重抓。
- `fut_contracts`、`opt_contracts`：以 `(instrument_id, raw_symbol)` 去重，保留 `ts_recv` 最新的一筆
- `manifest`

不建 `opt_with_underlying`；選擇權要做成什麼補充指標，確定後再設計。

## 驗證

1. `pytest src/manage_database/Databento_future/test_pipeline.py`：
   `_sample_days`、`_px` 保留負價、補漏過濾（重現 2SF 案例：同 id 兩個身分只留 K 線中出現的那個）、
   選擇權由標的期貨決定商品、非重試型 4xx 會拋錯而不是回傳空、
   快取在驗證成功後刪除、失敗時保留且 manifest 為 `failed`。
2. 實跑：`fetch.py --products NQ,CL,GC --start 2020-03-01 --end 2020-05-01`，再跑 `init_duckdb.py`。
3. **NQ 回歸比對**（新管線 2020-04 vs `data_nq_202004_v2/`）：
   - 期貨 1 分 K：逐欄完全相同。
   - 選擇權 1 分 K：只比 v2 中 `asset == "NQ"` 的部分，逐欄完全相同。
   - 合約表：只差 `2SFJ0 P1100` 一筆（以及新管線沒抓的週選／月底選系列）。
   - 期貨價差：v2 沒存，只確認有資料。
   - 有任何其他差異即算失敗，要查出原因。
4. **CL / GC 檢查**：
   - 選擇權的 `underlying` 都對得到 CL*/GC* 期貨，沒有歸屬警告。
   - CL 2020-04-20 的 CLK0 應出現負價（約 -37），確認沒被轉成 null 或錯誤值。
   - 用 DuckDB 查各商品 × 月份的筆數與合約數、`trade_date` 分布（週六應為 0）。
5. 重跑 `fetch.py` 同樣參數：manifest 顯示 `complete`，不發任何請求；跑完後 `/dev/shm/databento_cache/` 應為空。
6. 撰寫 `data/us/README.md`，含「在另一台電腦下載、再搬回來」一節。
