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

```
你的 polars DataFrame（已含 factor 欄與未來報酬欄）
   │
   │  ★ polars → pandas 轉換邊界：single_factor_eval.py:275-279 的 .to_pandas()
   ▼
pandas DataFrame
   ├─ factor_func.cal_pct_lag          (factor_func.py:79)   ← fallback，通常不觸發
   ├─ groupby("date").apply(ext_out_3std)  (factor_func.py:473)
   ├─ factor_func.grouping_factor      (factor_func.py:768)
   └─ factor.factor(class)             (factor.py:17)
        ├─ start_backtest              (factor.py:261)
        │    ├─ cal_df_stock           (factor.py:121)
        │    ├─ cal_turnover_rate      (factor.py:66)
        │    ├─ cal_df_info1           (factor.py:162)
        │    └─ cal_df_info2           (factor.py:231)
        └─ draw_pct / draw_ic / draw_ic_dacay  (factor.py:347/426/480)
```

**這條鏈就是 Polars 重構的目標範圍。** 上表以外的 `panda_factor` 模組不在此次範圍內。

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
| 4 呼叫端收斂去重 | ⛔ 不做 | 需修改 `src/`，違反範圍限制 |

**完整鏈實測：3.07s → 0.218s（14.07x）**，63 個測試全過。

| 函式 | pandas | polars | |
|---|---|---|---|
| `cal_pct_lag` | 370.0 ms | 20.8 ms | 17.8x |
| `ext_out_3std` | 269.4 ms | 31.9 ms | 8.5x |
| `grouping_factor` | 226.5 ms | 21.4 ms | 10.6x |
| `cal_df_stock` | 127.4 ms | 23.9 ms | 5.3x |
| `cal_turnover_rate` | 55.4 ms | 15.1 ms | 3.7x |
| `start_backtest`（整體） | 2120.1 ms | 100.5 ms | **21.1x** |

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

`single_factor_eval.py` 使用的三層重複路徑與正常路徑**指向同一個檔案**（實測確認）：

```python
# 兩者等價，都解析到 panda_factor/panda_factor/analysis/factor.py
from panda_factor.analysis.factor import factor
from panda_factor.panda_factor.panda_factor.analysis.factor import factor
```

原因是 editable install 的 finder 把巢狀目錄也註冊進了模組搜尋路徑。**建議統一使用短路徑** `panda_factor.analysis.factor`，避免混淆。

---

## 5. 重構準則

1. **不要動 `P3` 的繪圖與小型彙總表** — 資料量小，且 `IPython.display()` 與 matplotlib 慣例上預期 pandas 物件，硬轉只增加介面轉換成本。
2. **優先消除 Python 層 groupby 迴圈**（P0 兩項），這是效能瓶頸所在，不是 pandas API 本身慢。
3. **可直接複用既有 polars 範式**：`src/factor/single_factor_eval.py` 的 `screen_factor_ic_metrics()` 已用 polars 寫出等價的每日 IC 計算（`group_by("date").agg(pl.corr(...))`），`add_returns_lag()` 已是 `cal_pct_lag` 的 polars 版本。
4. **每次轉換都要對 baseline 比數值** — 見 §3.4，目前沒有測試可依靠。
5. **注意隨機性**：`ext_out_3std` 與 `grouping_factor` 都用 `np.random.normal` 加噪音以避免分箱邊界重複，比對 baseline 時需固定 seed 或容許微小誤差。
