# `src/factor/components` 使用說明

深度單因子回測。三個模組、一條流水線：

```
align_and_adjust.load_aligned_adjusted_daily()   # 原始日線 + 復權價 + 可交易旗標
        ↓  raw
deep_panel.prepare_panel(raw, config)            # 前向報酬、lag 報酬、成交日旗標
        ↓  panel（昂貴，建一次）
deep_eval.DeepFactorTester(panel, config)
        .run_all(factor_df, name=...)            # 每個因子跑一次
        ↓  DeepFactorResult
```

面板與設定共用同一份 `DeepBacktestConfig`。面板建一次可以重複測任意多個因子，
`run_all` 不會修改面板。

> **與快篩的關係**：`src/factor/single_factor_eval.py` 是快篩，允許粗糙，它的結果
> **不能**當成因子有效的結論。本模組承接少數通過快篩的因子做嚴格驗證。兩條路徑
> 刻意分開，不互相 import。

---

## 1. 前處理：把原始日線準備好

`prepare_panel` 的輸入必須有這些欄位（缺一個就報 `原始日線缺少必要欄位 [...]`）：

| 欄位 | 型別 | 意義 |
| --- | --- | --- |
| `symbol` | str | 證券代號，要與因子框同一種寫法 |
| `date` | Date | 交易日 |
| `close_adj` | Float64 | 復權收盤價（可用 `config.price_col` 換成別的價格欄） |
| `untradable` | 0/1 | **因子宇宙**排除旗標。實際含義是全額交割／非主板，**不是停牌** |
| `can_buy` | 0/1 | 當日買得到嗎（漲停時為 0） |
| `can_sell` | 0/1 | 當日賣得掉嗎（跌停時為 0） |

選配欄位：

| 欄位 | 意義 |
| --- | --- |
| `avoid_early` | 減資停牌前最後一個可交易日。有這欄時持有期內踩到就提前出清 |

這三個可交易性概念**永遠不合併成一個布林值**——它們排除的對象不同，混在一起就
分不出「不在宇宙」與「今天買不到」。

專案內的標準取數方式：

```python
from src.factor.components.align_and_adjust import load_aligned_adjusted_daily

raw = load_aligned_adjusted_daily(
    start_time="2022-01-01",
    end_time="2024-12-31",
    qlib_data_path="/dev/shm/qlib_ram",
    instrument="all",
    device="cpu",
)
```

> 這一步需要 `/dev/shm/qlib_ram` 存在。機器重開機後 ramdisk 會消失，症狀是
> `ValueError: can't find a freq from [] that can resample to day!`。
> 先跑 `bash rebuild_data/dump_qlib_to_ramdisk.sh`（需要 sudo）重建。

**Float64 是硬性要求。** `prepare_panel` 會把 Float32 與價格欄一律升成 Float64。
市值量級（mean≈1e6）的因子用 Float32 算 Pearson IC 誤差達 5.8e-04，成交額量級
（mean≈1e9）直接算出 `nan`——變異數走 `E[x²]-E[x]²`，平均值遠大於標準差時發生
災難性抵消。整數旗標不升，它們不以數值身分進入統計。

---

## 2. `DeepBacktestConfig`：所有可用參數

```python
from src.factor.components.deep_panel import DeepBacktestConfig

config = DeepBacktestConfig(
    holding_period=5,
    return_periods=(1, 3, 5, 10, 20),
    max_lag=20,
    group_count=5,
    min_names=20,
    seed=42,
)
```

| 參數 | 預設 | 說明 |
| --- | --- | --- |
| `holding_period` | `1` | 持有期 n（交易日）。一次深度回測只驗證單一持有期 |
| `return_periods` | `(1,3,5,10,20,30)` | 面板要備妥哪些持有期的報酬欄。**必須包含 `holding_period`** |
| `max_lag` | `20` | IC 衰減看到第幾個 lag |
| `group_count` | `5` | 分組數（≥2） |
| `winsorize` | `True` | 是否去極值（只截斷不置中，因子量級不變） |
| `winsorize_std` | `3.0` | 截斷在幾倍標準差 |
| `noise_std` | `1e-10` | 打散同值的噪音，讓 `qcut` 切得出唯一邊界。沿用 panda_factor 口徑 |
| `seed` | `None` | 亂數種子。給定值才有可重現性 |
| `min_coverage` | `0.5` | 因子框與面板的最低覆蓋率，低於此值視為對不上而報錯 |
| `min_names` | `20` | 一天至少要有幾檔才納入統計 |
| `newey_west_lags` | `None` | NW 的 lag 長度。`None` 時為 `0`——統計已在非重疊的換倉日上做（ADR-0003） |
| `fee_rate` | `0.00057` | 手續費率，**買賣皆收**。預設是台股 0.1425% 打 4 折 |
| `tax_rate` | `0.003` | 證券交易稅率，**僅賣出**收取 |
| `slippage_bps` | `20.0` | 滑點，**單邊**基點；買賣各收一次 |
| `extra_cols` | `()` | 除必要欄位外還要留在面板裡的欄位 |
| `price_col` | `"close_adj"` | 用哪個價格欄算報酬 |

衍生屬性：`config.return_col`（= `f"{holding_period}day_return"`）、`config.nw_lags`、
`config.buy_cost_rate`（手續費 + 滑點）、`config.sell_cost_rate`（手續費 + 稅 + 滑點）。
預設下買一單位權重 0.257%、賣一單位 0.557%，來回 0.814%。三個費率都不可為負。

建構時就會擋掉不合法組合，例如 `holding_period` 不在 `return_periods` 裡會直接
拋 `ValueError`——面板不會備妥對應的報酬欄，讓它安靜跑下去只會在後面得到空結果。

**`noise_std` 不要關掉。** 它複製 panda_factor 的 `ext_out_3std` + `grouping_factor`
行為（去極值時加一次、分組前再加一次），拿掉之後大量同值的因子會切不出分組。
只有在測試裡要做跨面板的精確比對時才設 `0.0`。

---

## 3. `prepare_panel`：建面板

```python
from src.factor.components.deep_panel import prepare_panel

panel = prepare_panel(raw, config)   # 純函數，不修改 raw
```

時間軸：**因子在 T 日形成**（只能用到 T 日收盤前的資訊）→ **T+1 收盤進場** →
**名目 T+n+1 收盤出場**。

產出的欄位（在原始欄位之外）：

| 欄位 | 意義 |
| --- | --- |
| `{n}day_return` | `close_adj[出場日] / close_adj[T+1] - 1`，每個 `return_periods` 各一欄 |
| `returns_lag{i}` | 第 i 個交易日之後的單日報酬（T+i+1 進、T+i+2 出），供 IC 衰減用 |
| `entry_can_buy` | 進場日（T+1）的 `can_buy` |
| `{n}day_can_sell` | **實際**出場日的 `can_sell` |
| `{n}day_early_exit` | 這筆持有是否因 `avoid_early` 提前出清 |

兩個刻意的設計決定：

- **跨停牌的報酬照實計算，不設 NA**（ADR-0001）。停牌日在面板中是有列的，位移
  自然落在正確的價格上。設 NA 會產生存活者偏誤——停牌與負報酬高度相關。
- **可交易性判在真正成交的那一天**（ADR-0002），而那兩天都不是 T。面板把位移後的
  旗標一併備妥，評估層只做統計。

`returns_lag{i}` 不套用提前出場——它衡量因子資訊的衰減，不對應一個可交易策略。

---

## 4. `DeepFactorTester`：跑評估

因子框只要三欄：`symbol`、`date`、`value`。

```python
from src.factor.components.deep_eval import DeepFactorTester

tester = DeepFactorTester(panel, config)      # 建構子只驗欄位，不跑統計
result = tester.run_all(factor_df, name="alpha101_005")
```

同一個 tester 可以連續測任意多個因子，彼此不干擾：

```python
results = {c: tester.run_all(fac.select("symbol", "date", pl.col(c).alias("value")), name=c)
           for c in col_names}
comparison = pl.concat([r.summary() for r in results.values()])
```

`run_all` 內部做的事，依序：

1. 正規化因子框（`symbol`→String、`date`→Date、`value`→Float64、去重）
2. 覆蓋率檢查——對不上就報錯，並指出是**日期範圍**還是**代號格式**不合
3. 套進場條件：`untradable == 0` **且** `entry_can_buy == 1`
4. 主樣本再套出場條件：`{n}day_can_sell == 1` 且報酬非空
5. 去極值（加噪音 → 逐日 `clip(μ±kσ)`）
6. 逐日 IC / Rank IC → 顯著性
7. 分組與多空 → 分組前**再**加一次噪音，`qcut(...).over("date")`
8. IC 衰減（固定樣本）

**剔除先於分組**：不可交易的名字在決定分位邊界之前就被拿掉，否則買不到的個股會
把邊界推歪，讓實際可買的名字落到錯的組。

---

## 5. 讀 `DeepFactorResult`

| 屬性 | 內容 |
| --- | --- |
| `name` | 因子名 |
| `config` | 這次用的設定 |
| `coverage` | `CoverageReport`：`factor_rows` / `matched_rows` / `coverage` / `unmatched_dates` / `unmatched_symbols` / `evaluated_rows` |
| `ic_daily` | `date, n, ic, rank_ic` |
| `group_returns` | `date, group, ret, n` |
| `long_short` | `date, ret`（最高組 − 最低組） |
| `cost_daily` | `date, group, buy_weight, sell_weight, cost`；多空那些列的 `group` 為 null |
| `decay` | `lag, ic, rank_ic, n_days, n_obs` |
| `group_stats` | 各組 + 多空的績效表，見下 |
| `metrics` | 見下 |
| `early_exit_count` | 主樣本中提前出清的筆數 |
| `dropped_days` | 因相異值不足而整天被丟掉的天數 |

`metrics` 的鍵：

```
n_days, n_obs
IC_mean, IC_ir, IC_t, IC_p, IC_nw_t, IC_nw_p
Rank_IC_mean, Rank_IC_ir, Rank_IC_t, Rank_IC_p, Rank_IC_nw_t, Rank_IC_nw_p
long_short_mean, long_short_ir, long_short_t, long_short_p, long_short_nw_t, long_short_nw_p
net_long_short_mean, net_long_short_ir, net_long_short_t, net_long_short_p,
net_long_short_nw_t, net_long_short_nw_p
P_rank_ic_gt, P_rank_ic_lt, P_rank_ic_abs_gt, monotonicity
```

鍵集合**與因子無關**：分不出組的因子照樣有 `long_short_*`，值是 `nan`。多個因子的
`summary()` 因此永遠疊得起來。

| 鍵 | 意義 |
| --- | --- |
| `P_rank_ic_gt` / `P_rank_ic_lt` | Rank IC > 0.02 / < -0.02 的交易日比例（嚴格不等式） |
| `P_rank_ic_abs_gt` | 兩者之和，即「有訊號」的天數比例 |
| `monotonicity` | 各組年化報酬與組序的相關係數絕對值，1 為完美單調 |

> panda_factor 的 `P(IC>0.02)` 名字寫 IC、**實際打在 rank_ic 上**（原始碼註解：
> 「P 阈值统计改用 Rank IC」）。這裡沿用它真正的算法，但名字改成不會誤導的。

### `group_stats`：分組績效（panda_factor 口徑）

一組一列，最後一列是多空組合（其 `group` 為 null、`label` 為 `long_short`）。

| 欄位 | 算法 |
| --- | --- |
| `annual_return` | `mean(ret) × 252 / holding_period` |
| `annual_volatility` | `std(ret, ddof=0) × sqrt(252 / holding_period)` |
| `max_drawdown` | **算術**累積（`cumsum`）的最大回撤，不是複利 |
| `sharpe` | `(annual_return - 0.025) / annual_volatility`，算不出來給 0 |
| `monthly_win_rate` | 按自然月加總後為正的月份比例，不是逐日勝率 |
| `mean_return` | 每期平均報酬 |
| `avg_names` | 該組平均檔數 |
| `turnover` | 本期在組內、上期不在的**檔數**比例；多空取兩端平均 |
| `buy_weight` / `sell_weight` | 每次換倉平均動到的**資金**比例 `Σ|Δw|`，恆在 0～1 |
| `cost_annual` | 年化交易成本 = `mean(每次換倉成本) × 252 / holding_period` |
| `net_annual_return` 等五個 `net_*` | 逐次換倉扣掉成本後**重算**的同名指標 |

這幾個算法刻意複製 panda_factor 的細節（包含 `ddof=0`、算術回撤、固定 2.5% 無風險
利率），用途是與既有結果對照，不是因為它們是最好的選擇。

**`turnover` 與 `buy_weight` 不是同一件事，不要互相對照。** 前者數檔數（沿用
panda_factor 口徑，組內檔數變動時會失真、甚至超過 100%），後者數資金，是成本的
唯一計算基礎。留倉股因組內檔數變動而被加減碼的流量計在 `buy_weight`/`sell_weight`
裡：5 檔變 6 檔時是 `1 − 5/6 = 16.7%`，而 `turnover` 會說 `1/5 = 20%`。

**成本是逐次換倉扣在報酬序列上再重算，不是從年化報酬扣一次。** 年化報酬的差是
線性的，夏普、最大回撤、月勝率都不是。多空的成本是**兩腿相加**（`turnover` 那欄
是取平均，口徑不同）；空頭腿目前套用與多頭相同的費率，未計借券成本——本專案不
打算做空。未模型化持有期間內價格漂移造成的權重偏移，因此成本是**下限**。

`sharpe`／`annual_return` 等不帶前綴的欄位一律是**未扣成本**的 gross 值，
與 `net_*` 並列而非被取代。

**未修正的 t 與 Newey-West t 並列輸出，不是取代。** NW 用 Bartlett kernel，
**lag 長度預設為 0**——統計只在換倉日上做，序列已經不重疊，沒有重疊造成的自相關
要修（ADR-0003）。此時 `nw_t` 與 `t` 只差在標準誤的自由度。要檢查因子本身的持續性
造成的自相關，用 `newey_west_lags=` 明確指定。

**IC 缺值就是缺值，不 `fillna(0)`。** 樣本不足（`n < min_names`）的日子在
`ic_daily` 裡直接缺席，不會變成一個「IC 恰好為零」的假觀測。

**沒有任何 benchmark 指標。** 上游的 benchmark 是等權宇宙平均，不是市場指數，
拿它算超額報酬沒有意義。多空報酬本身已經是市場中性的度量。

方法：

```python
result.summary()                    # 單列 DataFrame，多因子可 pl.concat 疊起來比
result.cumulative_ic()              # 累積 IC 曲線
result.cumulative_group_returns()   # 各組累積淨值
result.to_dict()                    # 可直接 json.dump 的字典（NaN 已轉成 null）
result.to_dict(include_series=True) # 另附逐日 IC、分組報酬、多空序列與 cost_daily
```

`to_dict()` 預設不含逐日序列——批次輸出時那會讓 JSON 膨脹到看不動。序列是事後
畫圖的唯一來源（`report_deep_eval_md.py` 只看 JSON），要出圖就得帶上。

繪圖（matplotlib 在方法內才 import，無頭環境安全；`run_all` 本身不畫任何圖）：

```python
result.plot_ic()                # 逐日 IC 柱狀 + 累積線
result.plot_cumulative_ic()
result.plot_group_returns()
result.plot_ic_decay()
fig, axes = result.plot_all()   # 2x2 四格
```

每個方法都吃 `ax=` 參數，可以自己排版。

> 中文字型：預設 DejaVu Sans 沒有中文字，圖上標題會出現缺字警告、字變方框。畫圖前
> 呼叫 `use_cjk_font()`（同模組）即可：系統有 CJK 字型就用系統的，WSL 上沒裝就直接
> 註冊 `/mnt/c/Windows/Fonts/msjh.ttc`。回傳實際用的字型名稱，`None` 代表沒找到。

---

## 6. 錯誤訊息對照

| 訊息 | 原因 |
| --- | --- |
| `原始日線缺少必要欄位 [...]` | `prepare_panel` 的輸入缺欄位 |
| `面板缺少欄位 ...` | 面板與 config 不搭，多半是建面板與跑評估用了不同的 `holding_period` / `max_lag` |
| 覆蓋率錯誤提到**日期** | 因子的日期範圍與面板不重疊 |
| 覆蓋率錯誤提到**代號** | 代號寫法不同（例：`600000` vs `600000.SH` vs `SH600000`） |
| `holding_period=n 不在 return_periods` | 面板不會備妥那一欄，改 config |

---

## 7. 套用到 `alphagen_test.ipynb`

Notebook 現況：cell 11 建 `FactorEngine`，cell 14 產出 `exprs_result`
（pandas：`date`、`symbol`、`*col_names`），cell 16 產出加權的 `df_pool_value`。
以下三格接在後面即可。

### Cell A — 建面板（跑一次，之後所有因子共用）

```python
import polars as pl
from src.factor.components.align_and_adjust import load_aligned_adjusted_daily
from src.factor.components.deep_panel import DeepBacktestConfig, prepare_panel
from src.factor.components.deep_eval import DeepFactorTester

CONFIG = DeepBacktestConfig(
    holding_period=5,
    return_periods=(1, 5, 10, 20),
    max_lag=20,
    group_count=5,
    min_names=20,
    seed=42,
)

raw = load_aligned_adjusted_daily(
    start_time="2022-01-01",
    end_time="2024-12-31",
    qlib_data_path="/dev/shm/qlib_ram",
    instrument="all",
)
panel = prepare_panel(raw, CONFIG)
tester = DeepFactorTester(panel, CONFIG)
print(panel.shape)
```

### Cell B — 把 `exprs_result` 餵進去

```python
# notebook 的 exprs_result 是 pandas 寬表；轉 polars 後逐欄拆成 (symbol, date, value)
wide = pl.from_pandas(exprs_result).with_columns(
    pl.col("date").cast(pl.Date),
    pl.col("symbol").cast(pl.String),
)

results = {}
for col in col_names:
    factor_df = wide.select(
        "symbol", "date", pl.col(col).cast(pl.Float64).alias("value")
    ).drop_nulls("value")
    results[col] = tester.run_all(factor_df, name=col)

table = pl.concat([r.summary() for r in results.values()]).sort(
    pl.col("Rank_IC_mean").abs(), descending=True
)
table
```

> `APPLY_UNTRADABLE_MASK` 在這條路徑上**不需要**先套。面板的 `untradable` 欄位
> 已經做了同一件事，而且是在正確的時點上做的。因子值留著、由評估層剔除，比在
> 因子端遮成 null 更乾淨。

### Cell C — 看單一因子的四張圖

```python
best = table["factor"][0]
fig, axes = results[best].plot_all()
fig.suptitle(best)

print(results[best].coverage)
print("提前出清筆數：", results[best].early_exit_count)
print("相異值不足而丟棄的天數：", results[best].dropped_days)
```

### 合成因子（cell 16 的 `df_pool_value`）

同一個 tester，換一份因子框就好：

```python
pool_factor = pl.from_pandas(df_pool_value).select(
    pl.col("symbol").cast(pl.String),
    pl.col("date").cast(pl.Date),
    pl.col("value").cast(pl.Float64),
)
pool_result = tester.run_all(pool_factor, name="alphagen_pool")
pool_result.summary()
```

---

## 8. 判讀時的注意事項

- **快篩的結論不算數。** `single_factor_eval.py` 的 docstring 自己列了四個樂觀
  偏誤的來源。深度回測的數字比快篩差是正常的，那才是比較接近實況的數字。
- **先看 `coverage`。** 覆蓋率 0.6 的因子，它的 IC 是在六成樣本上算的。
- **統計只在換倉日上做（ADR-0003）。** 交易日曆上每 `holding_period` 個交易日取一
  天，從第一個交易日起算。`holding_period=1` 時等於每一天，行為與過去相同；
  `holding_period > 1` 時樣本數是過去的 1/n，**與舊報表的數字對不上是預期的**。
  持有期越長，`sharpe` 與 `max_drawdown` 越該當成量級而不是估計值（hp=20 只有
  約 36 個觀測值）。抽樣的起點固定為第一個交易日，換起點會得到不同的數字，這是
  非重疊本來就有的性質。
- **判斷因子能不能用要看 `net_*`，不是 `annual_return`。** 預設費率下來回一趟
  0.814%，換手率 47% 的日換倉策略光成本就吃掉每日 0.38%——毛報酬每日 0.05% 完全
  蓋不住。日換倉的損益兩平換手率是 6.7%（就算滑點設為 0 也還要 13.3%），拉長持有期
  是唯一的解，不是把滑點調小。`cost_daily` 可以逐次換倉核對成本怎麼來的。
- **`dropped_days` 不為零** 代表因子在那些天相異值少於 `group_count`，通常是
  離散型或大量同值的因子——分組結果對它意義有限，看 IC 就好。
- **`decay` 的 `n_obs` 每個 lag 都相同**，這是刻意的固定樣本：衰減曲線的形狀不
  應該被「越後面的 lag 樣本越少」污染。
- 全部計算走 polars，不 import panda_factor，只沿用其指標定義以維持可比性。
