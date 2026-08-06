# CLAUDE.md — PandaFactor 專案上下文

本文件作為 **Pandas → Polars 重構**的共用上下文依據。內容全部由實際讀取原始碼與實跑指令驗證而來，未經推測。

---

## 1. 專案架構摘要

PandaFactor 是一個 monorepo，由多個各自帶 `setup.py`、可獨立 `pip install -e .` 的 Python 套件組成。持久層統一為 **MongoDB**。

### 1.1 套件清單與職責

| 套件 | 職責 | 對外進入點 |
|---|---|---|
| `panda_common` | 設定載入（`config.py` + `config.yaml`）、MongoDB singleton handler、logger | 無（被所有套件依賴） |
| `panda_data` | **資料讀取層**：從 MongoDB 讀行情與因子，回傳 `pd.DataFrame` | `panda_data.init()` → `get_factor()` / `get_market_data()` / `get_factor_by_name()` |
| `panda_data_hub` | **資料清洗與排程**：對接 Tushare / RiceQuant / 迅投等資料源，清洗後寫入 MongoDB | `_main_auto_.py`（常駐排程）、`_main_clean_.py`（一次性清洗） |
| `panda_factor` | **因子計算與分析**：因子定義、算子庫、分組回測、IC 分析 | `panda_factor.analysis.factor.factor`（class）、`panda_factor/__main__.py` |
| `panda_factor_server` | **對外 HTTP API**：FastAPI，掛載因子路由與前端靜態檔 | `panda_factor_server/__main__.py:app`（uvicorn, port 8111） |
| `panda_llm` | LLM 服務（OpenAI 協議相容，預設 DeepSeek），被主 server 以 `/llm` 掛載 | `panda_llm/server.py` |
| `panda_web` | Vue 靜態前端產物，由 server mount 於 `/factor` | `panda_web/main.py`（獨立 port 8080） |

> `server/` 目錄是**失效的遺留副本**（僅 3 個檔案、無 `__init__.py`、無 `setup.py`，且 import 的 `server.models.common`、`server.services.user_factor_service` 都不存在）。不要參考、不要修改。

### 1.2 依賴方向

```
panda_factor_server ──► panda_factor ──► panda_data ──► panda_common ──► MongoDB
        │                                                    ▲
        └──► panda_llm                                       │
                                            panda_data_hub ──┘（寫入端）
```

`panda_factor/setup.py` 刻意移除了對 `panda_data` 的宣告依賴（註解寫「移除循环依赖」），但 `panda_factor/analysis/factor_func.py` 內部仍 `import panda_data` — 這是隱性依賴，重構時需留意。

---

## 2. 核心資料流（Data Pipeline）

### 2.1 生產路徑（Server / 排程）

```
外部資料源 (Tushare / RiceQuant / 迅投 / TEJ)
   │  panda_data_hub/data/*_cleaner.py、factor/*_factor_clean_pro.py
   │  panda_data_hub/task/*_scheduler.py（每晚定時，見 config.yaml 的 UPDATE_TIME）
   ▼
MongoDB  ← panda_common/handlers/database_handler.py（pymongo singleton）
   │  panda_data/factor/factor_reader.py、market_data/*_reader.py
   ▼
pd.DataFrame
   │  panda_factor/generate/*（因子定義與算子）
   │  panda_factor/analysis/*（分組、IC、回測）
   ▼
panda_factor_server/routes/user_factor_pro.py → services/user_factor_service.py
   ▼
JSON → panda_web（Vue 前端）
```

### 2.2 研究路徑（Notebook / 單因子驗證）— **本次重構的主戰場**

外層專案 `/home/newt/quant_project/src/factor/single_factor_eval.py` **繞過** `panda_data` 與 MongoDB，自行用 polars 準備資料，只借用 `panda_factor` 的回測引擎：

**現況（重構完成後）** —— 全程 polars，中途沒有 pandas 邊界：

```
你的 polars DataFrame（已含 factor 欄與未來報酬欄）
   │
   ├─ prepare_factor_frame            (single_factor_eval.py)  ← 單一 lazy plan
   │    ├─ select / filter / inf→null / drop_nulls
   │    ├─ cal_pct_lag_pl             (factor_func_pl.py)  ← fallback，通常不觸發
   │    └─ ext_out_3std_pl            (factor_func_pl.py)  ← .over("date") 取代逐日 apply
   ├─ grouping_factor_pl              (factor_func_pl.py)  ← qcut().over("date")
   └─ factor_pl(class)                (factor_pl.py)
        ├─ start_backtest
        │    ├─ cal_df_stock          ← partition_by，覆寫父類別
        │    ├─ cal_turnover_rate     ← list.set_difference，覆寫父類別
        │    ├─ cal_backtest_frames_pl ← 單一 group_by 算完 IC/PNL/日期資格
        │    ▼ ★ 唯一的 polars → pandas 邊界（此後都是每日一列或每組一列的小表）
        │    ├─ cal_df_info1          (factor.py:162)  ← 沿用 pandas
        │    └─ cal_df_info2          (factor.py:231)  ← 沿用 pandas
        └─ draw_pct / draw_ic / draw_ic_dacay  (factor.py:347/426/480)  ← 沿用 pandas
```

`cal_df_info1/2` 與 `draw_*` **刻意保留 pandas**：輸入是 300 列的 `df_pnl` 與 7×12 的
彙總表，`cal_df_info1` 還相依於 `pd.Grouper(freq='M')` 需要 DatetimeIndex，而
`display()` 與 matplotlib 本就預期 pandas 物件 —— 硬轉只會增加介面成本。
即便如此，這兩個函式現在已占全鏈 11%（11.4ms／102.5ms），是最大的非 polars 殘留。

---

## 3. 環境設定與執行指令

### 3.1 環境

專案實際使用的是 **conda env `quant_research`**（不是 base，base 沒有 polars）：

```bash
conda activate quant_research
# 或直接指定：/home/newt/miniconda3/envs/quant_research/bin/python
```

| 項目 | 版本 |
|---|---|
| Python | 3.10.19 |
| pandas | 2.1.4（外層 `pyproject.toml` 釘住 `pandas<2.2`） |
| polars | 1.42.1（`pyproject.toml`：`polars>=1.42.1`） |
| numpy | 1.26.4 |
| scipy / statsmodels | 1.15.3 / 0.14.6 |
| pyarrow | 22.0.0（polars ↔ pandas 轉換需要） |
| pymongo | 3.11.0 |
| pytest | 9.0.2 |

外層 `/home/newt/quant_project` 用 **PDM** 管理（`pyproject.toml` + `pdm.lock`），但 `pdm` 未在 PATH 上；實務上是直接用 conda env。

全部 6 個 panda 套件皆已 **editable install** 進 `quant_research`：
`panda_common` / `panda_data` / `panda_data_hub` / `panda_factor` / `panda_factor_server` / `panda_llm`（另有 `pyqlib` editable）。
→ **改 `panda_factor/` 底下的原始碼會立即生效，不需重新安裝。**

若需重裝：
```bash
cd panda_factor/panda_common && pip install -e .   # 依序 panda_common → panda_data → panda_factor → ...
```

### 3.2 設定檔

`panda_factor/panda_common/panda_common/config.yaml`
- MongoDB：`127.0.0.1:27017`，`MONGO_TYPE: replica_set`，`MONGO_REPLICA_SET: rs0`，DB `panda`
- 環境變數會覆寫 yaml 的同名 key（`config.py:load_config()`）
- **注意**：`config.py` 會把 `USER` 這個 key 用系統環境變數 `$USER` 覆寫掉（實測會變成 `newt`）

### 3.3 服務啟動

```bash
python -m panda_factor_server            # API + 前端，port 8111
python panda_data_hub/panda_data_hub/_main_auto_.py   # 資料清洗排程常駐
```
Docker：`Dockerfile.server` → `uvicorn panda_factor_server.__main__:app --host 0.0.0.0 --port 8111`

### 3.4 測試 — golden-master 回歸安全網（Phase 0 建立）

專案原本**零測試覆蓋**。為了 Polars 重構，已於 `panda_factor/tests/` 建立 golden-master
回歸測試，作為 Phase 1-3 唯一的正確性基準。

```bash
cd /home/newt/quant_project/panda_factor
python -m pytest                    # 10 passed，約 15s
python -m pytest --update-baseline  # 重新產生基準（僅在行為變更確屬刻意時）
```

**組成**

| 檔案 | 作用 |
|---|---|
| `tests/conftest.py` | `seeded()` 固定全域 RNG；`panel` fixture |
| `tests/generate_fixture.py` | `build_panel()` 合成面板（200 檔 × 300 日）；`panel_fingerprint()` |
| `tests/_reference_pipeline.py` | 現行 pandas 鏈的權威複刻（對齊 `single_factor_eval.py:275-298`）；`prepare=` 參數可換成 polars 前處理做整合比對 |
| `tests/test_golden_baseline.py` | 快照比對 + 可重現性 + 噪音量級驗證 |
| `tests/test_factor_func_pl.py` | Phase 1 A/B 等價測試（pandas vs polars） |
| `tests/test_grouping_factor_pl.py` | Phase 2 A/B 等價測試 |
| `tests/test_factor_pl.py` | Phase 3 A/B 等價測試 |
| `tests/baseline/` | 基準產物（240KB） |
| `tests/fixtures/panel_fingerprint.csv` | 面板指紋（8KB） |

**設計要點**
- 面板 fixture **不進版控**，由 `np.random.default_rng` 固定種子即時生成（NEP 19 保證位元流穩定），並由 `test_fixture_is_stable` 主動驗證該前提
- `df_cuted` 不存全量（12.5MB），改存逐欄統計指紋 —— 其受追蹤欄位都會流進 `df_ic`/`df_pnl`，故為冗餘
- 數值比對容差 `atol=rtol=1e-8`
- ⚠️ `--update-baseline` 會覆寫基準。**不要用它讓失敗的測試變綠** —— 那等於把安全網關掉

**RNG 實測結論（重要，影響重構容差）**
`ext_out_3std`(factor_func.py:487) 與 `grouping_factor`(factor_func.py:826) 加入 1e-10
量級噪音以避免 qcut 分箱邊界重複，且**皆未設種子**。實測：
- 固定種子 → 整條鏈逐位元重現
- **即使完全不設種子**，分組指派、`df_pnl`、`rank_ic`、`df_info2` 全部完全一致；僅原始 float `ic`/`ir` 漂移約 1e-10

→ **polars 版不需要複製噪音的抽樣序列**，只需在 1e-8 容差內符合語意即可。這比原先預估寬鬆許多。

---

## 4. Pandas 使用場景與依賴關係

### 4.1 全庫 pandas 分布

| 套件 | 有 `import pandas` 的檔案數 | 說明 |
|---|---|---|
| `panda_factor` | 12 | **核心，用量最重** |
| `panda_data_hub` | 13 | 各資料源清洗邏輯 |
| `panda_data` | 8 | 讀取層，所有對外 API 回傳 `pd.DataFrame` |
| `panda_common` | 1 | `utils/stock_utils.py` |
| `panda_factor_server` / `panda_llm` / `panda_web` | 0 | 純服務層，只轉發呼叫 |

目前**全庫沒有任何 `import polars`** — polars 只存在於外層 `src/factor/` 的研究程式碼中。

### 4.2 重構目標鏈的 pandas 使用細節

| 檔案:行 | 函式 | pandas 使用場景 | 重構優先度 |
|---|---|---|---|
| `factor_func.py:768` | `grouping_factor` | Python `for date, group in df.groupby('date')` 逐日迴圈 → 每日 `pd.qcut` 分箱 → `pd.concat` 合併；另建 benchmark 平均報酬表 | **P0** |
| `factor.py:277-312` | `start_backtest` 的每日 IC 迴圈 | `for date, group in df.groupby('date')`，逐日算 `.corr()`(Pearson IC)、`.rank().corr()`(Rank IC)，加 21 組 lag 版本，dict 累積後 `pd.DataFrame(ic_dict).T` | **P0** |
| `factor_func.py:473` | `ext_out_3std` | 被呼叫端以 `groupby("date", group_keys=False).apply(...)` 逐組呼叫；內部做 3-sigma clip + 加噪音 | **P1** |
| `factor_func.py:79` | `cal_pct_lag` | `groupby('symbol')['1day_return'].transform(shift)` 跑 21 次 | **P1**（建議「消除」而非轉換） |
| `factor.py:121` | `cal_df_stock` | 巢狀 groupby（date × group），cell 存 symbol list，`pd.DataFrame(dict).T` 形成不規則寬表 | **P2**（需重新設計資料形狀） |
| `factor.py:66` | `cal_turnover_rate` | 雙層 Python for 迴圈 + `.iloc` 純量存取 + Python `set` 差集，完全未向量化 | **P2**（瓶頸是演算法而非 pandas） |
| `factor.py:162/231/347/426/480` | `cal_df_info1/2`、`draw_*` | 小型彙總表（列數 ≈ 分組數）格式化 + matplotlib 繪圖 | **P3（建議跳過）** |

### 4.2b Polars 重構進度

| Phase | 狀態 | 產出 |
|---|---|---|
| 0 安全網 | ✅ 完成 | `tests/`，golden-master baseline |
| 1 `cal_pct_lag` / `ext_out_3std` | ✅ 完成 | `factor_func_pl.py`（**12.2x**） |
| 2 `grouping_factor` | ✅ 完成 | `grouping_factor_pl` + `to_backtest_contract`（**10.6x**） |
| 3 `start_backtest` IC/PNL 迴圈 | ✅ 完成 | `cal_backtest_frames_pl` + `factor_pl` 子類別 |
| P2 `cal_df_stock` / `cal_turnover_rate` | ✅ 完成 | `factor_pl` 覆寫（`list.set_difference` 向量化） |
| 4 呼叫端收斂 | ✅ 完成 | `single_factor_eval.run_single_factor_test` 全鏈改走 `*_pl` |
| 5 既有 polars 實作二次優化 | ✅ 完成 | 見下方「§4.2c」 |

**完整鏈實測：2.03s → 0.103s（19.8x）**，63 個測試全過。

| 函式 | pandas | polars | |
|---|---|---|---|
| `cal_pct_lag` | 370.0 ms | 20.8 ms | 17.8x |
| `ext_out_3std` | 269.4 ms | 9.6 ms | 28.1x |
| `grouping_factor` | 209.8 ms | 13.5 ms | 15.5x |
| `cal_df_stock` | 127.4 ms | 12.2 ms | 10.4x |
| `cal_turnover_rate` | 55.4 ms | 10.4 ms | 5.3x |
| `start_backtest`（整體） | 2016.7 ms | 62.8 ms | **32.1x** |

### 4.2c 二次優化：既有 polars 實作中找出的四處浪費

Phase 1-3 的 `*_pl` 實作雖已消除 Python 迴圈，實測（59k 列面板）仍有四處明顯浪費。
**每一項都是靠量測發現的，不是靠讀程式碼推測** —— 其中兩處與直覺相反：

| 位置 | 問題 | 修法 | 效果 |
|---|---|---|---|
| `ext_out_3std_pl` | 逐日 mean/std 被算 **4 次**：`clip` 與 `process_inf` 各自引用同一個 `over()` Expr，而 **polars 的 CSE 不會合併重複的 window 運算式**（`explain()` 可見它原封不動出現多次） | mu/sigma 先物化成暫時欄，再由兩處共用；整段併為單一 lazy plan | 25.1 → 9.6 ms |
| `grouping_factor_pl` | `with_row_index` + semi-join 占本函式**四成**耗時，但在本流程中**一列都濾不掉** —— 呼叫端已先 `drop_nulls(factor)`，故每日 `_null_cnt` 恆為 0、相異值數遠大於 `group_cnt` | 全部日期有效時走快速路徑：跳過 join，連列序還原欄都不需要，排序也降為單鍵 | 21.4 → 13.5 ms |
| `cal_backtest_frames_pl` | 對 59k 列掃 **3 趟**（`qualifying_dates_pl` 的 `n_unique`、IC、PNL）外加一次 semi-join | 併成單一 `group_by`：逐日聚合彼此獨立，「先全算再篩日期」與「先篩再算」結果相同 | 23.4 → 18.4 ms |
| `factor_pl.cal_df_stock` | `pivot` 是主成本（7.2ms）；`to_pandas()` 後再逐格 `ndarray.tolist()` 又多一趟往返 | `partition_by` 逐組取出（附日期對齊守衛，不成立時退回 pivot）；`Series.to_list()` 直接建 DataFrame | 19.5 → 12.2 ms |

另修掉 `factor_pl.start_backtest` 為了判斷「是否為空」而 `df.to_pandas()` 物化整份
59k 列 df_cuted 的浪費 —— pandas 與 polars 都有 `.columns`，列數各用 `len()`／`.height`。

**兩個與直覺相反的量測結果，值得記下**：
1. **小表上不要用 lazy。** 把 `cal_backtest_frames_pl` 尾段（每日一列、約 300 列）改成
   lazy 反而從 21.4ms **變慢到 24.9ms** —— 查詢計畫最佳化的固定成本超過它能省下的
   物化成本。該減少的是「操作次數」，不是「eager 換 lazy」。故改用
   「合格布林值的 `cum_sum() - 1`」直接算出日期編號，把
   `filter → with_row_index → filter` 三步壓成 `with_columns → filter` 兩步。
2. **噪音不能拿掉。** 曾考慮設 `noise_std=0` 以換取全程 lazy（免去為噪音取得 height），
   但實測 polars `qcut` 遇到重複分位邊界會拋 `DuplicateError`（pandas 拋 `ValueError`）。
   那個 1e-10 噪音正是用來打散平手值的，對整數型或四捨五入過的因子是**必要**的。
   另注意：pandas 版靠 `except ValueError` 靜默跳過該日，`grouping_factor_pl` 改為
   事前條件判斷，故 `DuplicateError` 會往外拋而非被吞掉。

仍為 pandas 且**刻意不動**的只剩 `cal_df_info1/2` 與 `draw_*` —— 小型彙總表（列數 ≈ 分組數）
與 matplotlib 繪圖，轉換只增加介面成本。

**使用方式**（呼叫端遷移時）：
```python
from panda_factor.analysis.factor_pl import factor_pl   # 取代 factor
alpha = factor_pl(name=factor_name, group_number=5)      # 其餘 API 完全相同
alpha.set_backtest_parameters(period=1, predict_direction=1)
alpha.start_backtest(df_cuted, df_benchmark)             # 可餵 pandas 或 polars
```
`factor_pl` 覆寫 `start_backtest`、`cal_df_stock`、`cal_turnover_rate` 三個方法；
`df_pnl`/`df_ic`/`df_stock`/`df_turnover`/`df_info`/`df_info2` 的型別與內容均與父類別一致
（仍為 DatetimeIndex 的 pandas DataFrame），`draw_*` 照常可用。

⚠️ `df_stock` / `df_turnover` 的**欄位順序**是隱性契約：`cal_turnover_rate` 與
`cal_df_info1`（factor.py:171/176/182）都以位置索引 `.iloc[:, n]` 存取，欄序錯了
不會報錯，只會把各組的數字對調。`factor_pl` 明確以 `group1..groupN` 重排。

`factor_func_pl.py` 為 **additive**：既有 `factor_func.py` 完全未改動，呼叫端可逐一遷移。

**使用 polars 版時務必注意的語意差異**（已寫在模組 docstring）：
- **NaN vs null** —— pandas 一律視 NaN 為缺值；polars 區分兩者且 NaN 具傳染性，
  `pl.Series([1.0, nan, 3.0]).mean()` 回傳 NaN 而非 2.0。polars 原生運算（如 `0/0`）
  產生的是真 NaN，會讓整個日期截面的 mean/std 變 NaN、使 clip 邊界失效而靜默不裁切。
  故 `ext_out_3std_pl` 在聚合前一律呼叫 `nan_to_null()` 正規化。
- **列序** —— pandas 的 `groupby('symbol').transform(shift)` 依現有列序位移，未先排序；
  polars 版明確依 (symbol, date) 排序後再位移並還原列序。輸入已依日期排序時兩者相同。

- **Rank IC ≠ Spearman** —— `factor.py:295/298` 寫的是 `.rank().corr()`，即**各欄先在自己的
  完整序列上排名，再取 Pearson**。這與 `corr(method='spearman')`（對齊後才排名）在含缺值時
  **不等價**，實測差異可達 7e-3。`returns_lag*` 尾端必然有缺值，所以此差異一定會被觸發。
  polars 版須寫成 `pl.corr(pl.col(a).rank(), pl.col(b).rank())`，**不可**改用 spearman。
  另 `ir` 用的是 `group.shape[0]`，即**含缺值列**的總列數。
- **Categorical cast** —— polars `qcut` 回傳 Categorical，**直接 `.cast(pl.Int32)` 取到的是
  0-based 類別索引而非標籤值，且不會報錯**，只會靜默產生 off-by-one 的分組。必須
  `.cast(pl.Utf8).cast(pl.Int64)`。`factor.py:305` 以 `== n` 比較整數，踩到即全盤錯誤。

實測效能（58,908 列 × 300 日 × 200 檔）：
`cal_pct_lag` 370ms → 20.8ms（17.8x）、`ext_out_3std` 269ms → 31.9ms（8.5x）、
`grouping_factor` 226ms → 21.4ms（10.6x）

**`grouping_factor` 一項未被記載的既有行為**（已在 `grouping_factor_pl` 如實複製）：
某日因子只要含**任何一個缺值**，該日就會被整日剔除。成因是 factor_func.py:826-828 把長度為
「非缺值筆數」的 qcut 結果指派回長度為「全部筆數」的 DataFrame，觸發 ValueError 後被
:830 的 `except ValueError` 捕捉而跳過。被剔除的日子**仍會留在 `df_benchmark`** 中，
因此 df_benchmark 的日期數可能多於 df_cuted。

### 4.3 隱性 pandas 依賴（容易漏掉）

- **`analysis/factor.py` 本身沒有 `import pandas`**，它透過 `from panda_factor.analysis.factor_func import *`（factor.py:4）間接取得 `pd`。純文字搜尋 `import pandas` **不會**列出 `factor.py`，但它大量使用 `pd.DataFrame`。
- `factor_func.py` 頂層 `import panda_data`，載入時會觸發 `panda_common` 設定載入（會印出 config log）。
- `factor.py` 頂層 import `panda_common.handlers.database_handler`，即使只做本地回測也會拉進 MongoDB 相關模組。

### 4.4 Import 路徑陷阱

**三層重複路徑已失效**（2026-08 實測更正，早前記載為「兩者等價」是錯的）：

```python
from panda_factor.analysis.factor import factor                          # ✅ 可用
from panda_factor.panda_factor.panda_factor.analysis.factor import factor  # ❌ ModuleNotFoundError
```

editable install 的 finder 只有一條對應：
`MAPPING = {'panda_factor': '<repo>/panda_factor/panda_factor/panda_factor'}`
（見 site-packages/`__editable___panda_factor_0_1_finder.py`），並未把巢狀目錄註冊成
可 import 的子模組。**一律使用短路徑** `panda_factor.analysis.*`。

`single_factor_eval.py` 已改用短路徑。**尚未修正**、仍會在 import 期就拋
`ModuleNotFoundError` 的檔案：
- `src/factor/alphagen_pool_analyzer.py:15-16`（模組層 import）
- `src/factor/alphagen_test.py:231-232`（函式內 import）

### 4.5 測試資料未進版控

`panda_factor/tests/` 只有 `.py` 進版控。`tests/baseline/`（golden-master 基準，240KB）
與 `tests/fixtures/panel_fingerprint.csv` 被 gitignore 掉了，但**不是刻意的** ——
是被兩條資料檔通用規則順帶掃到：

```
.gitignore:1               *.parquet   → tests/baseline/*.parquet
panda_factor/.gitignore:2  *.csv       → tests/baseline/*.csv、tests/fixtures/*.csv
```

後果：全新 clone 或 git worktree 中 `pytest` 會有 8 個測試因找不到基準檔而失敗
（其餘 55 個仍會跑）。要在別處跑測試需先從既有工作目錄複製這兩個目錄，或以
`--update-baseline` 重新產生 —— 但後者是拿當下行為當基準，會失去「與歷史行為比對」
的意義，僅適用於初次建立。

→ **若要讓安全網真正可攜**，應以 `git add -f panda_factor/tests/baseline/` 破例納入
（240KB，屬於測試基準而非資料產物）。此決定尚未執行，留待決策。

`tests/conftest.py` 會把**所在 repo** 的套件目錄插到 `sys.path` 最前面，確保測到的是
同一份原始碼而非 editable install 記錄的絕對路徑（setuptools 的 editable finder 是
`sys.meta_path.append()`，排在 `PathFinder` 之後，故 `sys.path` 勝出）。沒有這段，
在 worktree 中跑測試會靜默地測到另一份程式碼。

---

## 5. 重構準則

1. **不要動 `P3` 的繪圖與小型彙總表** — 資料量小，且 `IPython.display()` 與 matplotlib 慣例上預期 pandas 物件，硬轉只增加介面轉換成本。
2. **優先消除 Python 層 groupby 迴圈**（P0 兩項），這是效能瓶頸所在，不是 pandas API 本身慢。
3. **可直接複用既有 polars 範式**：`src/factor/single_factor_eval.py` 的 `screen_factor_ic_metrics()` 已用 polars 寫出等價的每日 IC 計算（`group_by("date").agg(pl.corr(...))`），`add_returns_lag()` 已是 `cal_pct_lag` 的 polars 版本。
4. **每次轉換都要對 baseline 比數值** — 見 §3.4，目前沒有測試可依靠。
5. **注意隨機性**：`ext_out_3std` 與 `grouping_factor` 都用 `np.random.normal` 加噪音以避免分箱邊界重複，比對 baseline 時需固定 seed 或容許微小誤差。
