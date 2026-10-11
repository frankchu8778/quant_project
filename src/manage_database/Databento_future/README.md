# 美國期貨原始資料庫 (CME, Databento GLBX.MDP3)

**維護者:** [Newt]
**名詞:** 見 `src/manage_database/Databento_future/CONTEXT.md`（商品、合約、選擇權系列、標的期貨、價差、交易日）

## 目錄結構

```
data/us/
├── logs/                              fetch.py 每次執行一個日誌檔
├── raw/
│   ├── futures/bars_1m/root=<商品>/month=<YYYY-MM>/data.parquet          期貨合約 1 分 K
│   ├── futures/contracts/root=<商品>/month=<YYYY-MM>/data.parquet        期貨合約定義
│   ├── futures/spread_bars_1m/root=<商品>/month=<YYYY-MM>/data.parquet   期貨價差 1 分 K
│   ├── futures/spread_contracts/root=<商品>/month=<YYYY-MM>/data.parquet 期貨價差定義
│   ├── options/bars_1m/root=<商品>/month=<YYYY-MM>/data.parquet          月選 1 分 K
│   └── options/contracts/root=<商品>/month=<YYYY-MM>/data.parquet        月選合約定義
└── metadata/
    ├── manifest/root=<商品>/<YYYY-MM>.parquet   每個 (商品, 月份) 的抓取狀態
    └── us.duckdb                                只放 view
```

- 一個 (商品, 月份) 的所有檔案由同一次處理產生；重抓會覆蓋，不會重複。
- `month=` 依 `ts_event` 的 **UTC** 月份切分，只是存檔切法，不代表交易時段。
- 價格照交易所原值（含 CL 2020-04-20 的負價、負履約價），沒有任何調整、換月或拼接。
- 合約以 `(instrument_id, raw_symbol)` 識別；CME 會重新分配 instrument_id，**不要只用 instrument_id join**。
- 選擇權只抓月選（NQ→`NQ`、CL→`LO`、GC→`OG`；目前預設不下載，見下方「更新方式」）；選擇權組合單不存。
- 商品：NQ、CL、GC、ES、SIL（微型白銀）、ZC（玉米）、6E（歐元）、6J（日圓）。微型標普 MES 2019-05 才上市，歷史資料用 ES。

## 注意事項
- 只使用 UTC 時間；`trade_date`（CME 交易日，17:00 CT 之後歸下一日）只在 DuckDB view 裡計算，不在檔案中。
  已知限制：假日提前收盤的時段會標錯（例如 Memorial Day 週日晚～週一中午，CME 歸週二，view 標週一）。
- manifest `status`：`complete`（月份已結束且抓完）、`partial`（當月未結束，重跑會補）、`failed`（看 `error` 欄位與日誌）、
  `running`（正在抓；程式沒在跑卻停在這個狀態，表示上次被硬中斷）。

## 更新方式

```bash
cd ~/quant_project/src/manage_database/Databento_future
export DATABENTO_API_KEY=db-xxxx
PY=~/miniconda3/envs/quant_research/bin/python
$PY fetch.py --products NQ,CL,GC --start 2020-03-01 --end 2020-05-01   # --start/--end 為月初, end 不含
$PY init_duckdb.py
```

- `complete` 且資料檔都在的 (商品, 月份) 會跳過；加 `--force` 才重抓。`failed`、`running`（上次被 kill／關機中斷）會自動重抓。
- `--workers`（預設 8）是每類請求同時發出的數量。三個商品同時跑時，代理偶爾回 504 upstream timeout，程式會自動重試。
- 日誌：`data/us/logs/fetch_<商品>_<開始時間>.log`。檔案內含每個請求的耗時與筆數（DEBUG）、
  超過 120 秒的慢請求、重試、失敗的完整 traceback，以及 Python 崩潰時的 stack。畫面只顯示 INFO 以上。
- Ctrl-C 會立即中斷，正在處理的月份留在 `running`，重跑同指令即接續。
- 下載中的原始回應快取在 `/dev/shm/databento_cache/<商品>/<YYYY-MM>/`，驗證成功即刪；
  失敗或中斷時保留，重跑同指令即接續（WSL 重開機會清空，最多重抓一個月）。
- 新增商品：在 `src/manage_database/Databento_future/products.yaml` 加一筆（期貨 parent 為 `<商品>.FUT`，`options` 列月選系列代碼）。
- 選擇權：`products.yaml` 的 `fetch_options`（`defaults` 為預設值，各商品可覆寫）。目前預設**關閉**，只抓期貨與價差。
  關閉時 manifest 不記選擇權；之後打開，沒有選擇權紀錄的月份會自動重抓；已抓過的選擇權資料不會被刪。

查詢：

```python
import duckdb
con = duckdb.connect("/home/newt/quant_project/data/us/metadata/us.duckdb", read_only=True)
con.sql("SELECT root, month, kind, rows, status FROM manifest ORDER BY ALL")
con.sql("SELECT * FROM fut_bars WHERE root = 'CL' AND trade_date = DATE '2020-04-20'")
```

view：`fut_bars`、`fut_spreads`、`opt_bars`（含 `trade_date`）、`fut_contracts`、`fut_spread_contracts`、`opt_contracts`（已去重）、`manifest`。

## 在另一台電腦下載、再搬回來

資料是以 (商品, 月份) 分檔的，manifest 也是，所以不同台電腦負責不同商品時，檔案路徑不會重疊。

1. 另一台（WSL）`git clone` 本專案、準備好 conda 環境與 `DATABENTO_API_KEY`。
2. 只跑分配給它的商品，例如：
   `$PY fetch.py --products GC --start 2020-03-01 --end 2020-05-01 --data-root ~/us_gc`
3. 把結果複製回本機：`rsync -av <另一台>:~/us_gc/raw/ ~/quant_project/data/us/raw/`，
   `metadata/manifest/` 同樣做法（**不要**複製 `us.duckdb`）。
4. 本機重跑 `$PY init_duckdb.py`（view 用本機絕對路徑）。
