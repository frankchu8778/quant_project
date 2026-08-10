"""深度單因子回測：可交易性檢驗、IC、顯著性、分組、IC 衰減。

與 ``single_factor_eval.py``（快篩）並存、職責分開。快篩允許粗糙，其結果不得作為
因子有效性的結論；本模組承接少數通過快篩的因子，做嚴格驗證。

嚴格的具體含義是三件事：

1. **可交易性在真正成交的那一天判定**——進場日看 ``can_buy``、出場日看 ``can_sell``，
   任一端不通過該檔當日整筆從截面剔除，且**剔除先於分組**（ADR-0002）。
2. **報酬跨越停牌照實計算**，不設 NA（ADR-0001）。
3. **統計量對自相關做修正**——未修正的 t 與 Newey-West t 並列輸出，且 IC 缺值
   就是缺值，不 ``fillna(0)``。

全部計算走 polars，不 import panda_factor，只沿用其指標定義以維持可比性。

昂貴的面板建一次、多個因子重複測::

    tester = DeepFactorTester(panel, config)
    result_a = tester.run_all(factor_a, name="alpha101_005")
    result_b = tester.run_all(factor_b, name="alpha191_026")

術語一律以 CONTEXT.md 為準。規格見 GitHub issue #1。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import polars as pl

from src.factor.components.deep_panel import DeepBacktestConfig

#: 因子框的三個欄位。
FACTOR_COLS: tuple[str, ...] = ("symbol", "date", "value")

#: 評估時內部使用的因子欄名，取一個不會與面板撞名的名字。
_FACTOR = "_factor_value"
#: 未經噪音與去極值的原始因子值。相異值的判定必須打在它身上——噪音會讓每個值都不同。
_RAW = "_factor_raw"
_GROUPED = "_factor_grouped"


# ---------------------------------------------------------------------------
# 結果物件
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageReport:
    """因子框與面板 join 之後的覆蓋情形。"""

    #: 因子框的列數
    factor_rows: int
    #: 因子框中能在面板找到對應 (symbol, date) 的列數
    matched_rows: int
    #: matched_rows / factor_rows
    coverage: float
    #: 因子框有、面板沒有的相異日期數
    unmatched_dates: int
    #: 因子框有、面板沒有的相異代號數
    unmatched_symbols: int
    #: 通過宇宙與可交易性檢驗、實際進入統計的列數
    evaluated_rows: int


@dataclass(frozen=True)
class DeepFactorResult:
    """單一因子的深度回測結果。可在程式裡取值，不只是印出來的表。

    刻意不含任何 benchmark 衍生指標——benchmark 是宇宙內等權平均而非市場指數，
    會隨宇宙定義改變，且在多空價差中本來就相消。判讀依據是多空價差本身。
    """

    name: str
    config: DeepBacktestConfig
    coverage: CoverageReport
    #: 逐日 IC：date, n, ic, rank_ic。樣本不足的日子缺席，不是 0。
    ic_daily: pl.DataFrame
    #: 逐日分組報酬：date, group, ret, n
    group_returns: pl.DataFrame
    #: 逐日多空價差：date, ret
    long_short: pl.DataFrame
    #: IC 衰減：lag, ic, rank_ic, n_days, n_obs。所有 lag 共用固定樣本。
    decay: pl.DataFrame
    #: 匯總指標（Rank_IC / ICIR / t / Newey-West t / ...）
    metrics: Dict[str, float]
    #: 提前出場（avoid_early）的發生次數
    early_exit_count: int
    #: 相異值不足以支撐分組數而整天丟棄的交易日數
    dropped_days: int

    # --- 取值 ---------------------------------------------------------

    def summary(self) -> pl.DataFrame:
        """單列匯總表，方便把多個因子的結果堆起來橫向比較。"""
        return pl.DataFrame(
            {"factor": self.name, **{k: [v] for k, v in self.metrics.items()}}
        )

    def cumulative_ic(self) -> pl.DataFrame:
        """累積 IC（逐日 Rank IC 的累加）。"""
        return self.ic_daily.select(
            "date",
            pl.col("ic").cum_sum().alias("cum_ic"),
            pl.col("rank_ic").cum_sum().alias("cum_rank_ic"),
        )

    def cumulative_group_returns(self) -> pl.DataFrame:
        """各分組的累積報酬（寬表：date + 每組一欄 + long_short）。"""
        wide = self.group_returns.pivot(
            on="group", index="date", values="ret"
        ).sort("date")
        group_cols = [c for c in wide.columns if c != "date"]
        wide = wide.with_columns(
            [((1.0 + pl.col(c).fill_null(0.0)).cum_prod() - 1.0).alias(c) for c in group_cols]
        )
        ls = self.long_short.sort("date").select(
            "date",
            ((1.0 + pl.col("ret").fill_null(0.0)).cum_prod() - 1.0).alias("long_short"),
        )
        return wide.join(ls, on="date", how="left")

    # --- 繪圖（#8）----------------------------------------------------
    # 繪圖與計算分離：結果物件持有數據，繪圖是對結果物件的操作，
    # run_all 不會自動繪圖。matplotlib 延後 import，無頭環境不受影響。

    def plot_ic(self, ax=None):
        """IC 時序。"""
        ax = _new_ax(ax)
        d = self.ic_daily.sort("date")
        ax.bar(d["date"].to_list(), d["rank_ic"].to_list(), width=1.0, color="#4878a8")
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_title(f"{self.name} — Rank IC 時序")
        ax.set_ylabel("Rank IC")
        return ax

    def plot_cumulative_ic(self, ax=None):
        """累積 IC。"""
        ax = _new_ax(ax)
        d = self.cumulative_ic().sort("date")
        ax.plot(d["date"].to_list(), d["cum_rank_ic"].to_list(), label="累積 Rank IC")
        ax.plot(d["date"].to_list(), d["cum_ic"].to_list(), label="累積 IC", alpha=0.6)
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.legend()
        ax.set_title(f"{self.name} — 累積 IC")
        return ax

    def plot_group_returns(self, ax=None):
        """分組累積報酬。多空兩端的分離程度看這張。"""
        ax = _new_ax(ax)
        d = self.cumulative_group_returns().sort("date")
        dates = d["date"].to_list()
        for col in [c for c in d.columns if c not in ("date", "long_short")]:
            ax.plot(dates, d[col].to_list(), label=f"group {col}")
        if "long_short" in d.columns:
            ax.plot(
                dates, d["long_short"].to_list(),
                label="多空價差", color="black", linewidth=2.0,
            )
        ax.axhline(0.0, color="grey", linewidth=0.8)
        ax.legend()
        ax.set_title(f"{self.name} — 分組累積報酬")
        return ax

    def plot_ic_decay(self, ax=None):
        """IC 衰減。固定樣本，只套進場條件。"""
        ax = _new_ax(ax)
        d = self.decay.sort("lag")
        ax.bar(d["lag"].to_list(), d["rank_ic"].to_list(), color="#4878a8")
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_xlabel("lag（交易日）")
        ax.set_ylabel("平均 Rank IC")
        ax.set_title(f"{self.name} — IC 衰減")
        return ax

    def plot_all(self):
        """四張圖畫在同一個 figure 上，回傳 (fig, axes)。"""
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(16, 9))
        self.plot_ic(axes[0][0])
        self.plot_cumulative_ic(axes[0][1])
        self.plot_group_returns(axes[1][0])
        self.plot_ic_decay(axes[1][1])
        fig.tight_layout()
        return fig, axes


def _new_ax(ax):
    if ax is not None:
        return ax
    import matplotlib.pyplot as plt

    _, ax = plt.subplots(figsize=(10, 4))
    return ax


# ---------------------------------------------------------------------------
# 統計
# ---------------------------------------------------------------------------


def _newey_west_se(x: np.ndarray, lags: int) -> float:
    """序列平均值的 Newey-West（Bartlett kernel）標準誤。

    S = gamma_0 + 2 * sum_{j=1..L} (1 - j/(L+1)) * gamma_j，var(mean) = S / n。

    IC 序列中缺席的日子被當成不存在（相鄰觀測視為相鄰），這是 HAC 用在有缺口的
    序列上的標準做法；缺口佔比很高時修正會偏保守。
    """
    n = x.size
    if n < 2:
        return float("nan")
    centred = x - x.mean()
    s = float(np.dot(centred, centred) / n)
    for j in range(1, min(lags, n - 1) + 1):
        gamma = float(np.dot(centred[j:], centred[:-j]) / n)
        s += 2.0 * (1.0 - j / (lags + 1.0)) * gamma
    if not np.isfinite(s) or s <= 0:
        return float("nan")
    return float(np.sqrt(s / n))


def _t_and_p(mean: float, se: float, dof: int) -> tuple[float, float]:
    from scipy.stats import t as student_t

    if not np.isfinite(se) or se <= 0 or dof < 1:
        return float("nan"), float("nan")
    stat = mean / se
    return float(stat), float(2.0 * student_t.sf(abs(stat), dof))


def _series_stats(values: pl.Series, prefix: str, nw_lags: int) -> Dict[str, float]:
    """一條 IC 序列的平均、ICIR、未修正 t 與 Newey-West t。"""
    x = values.drop_nulls().to_numpy().astype(np.float64)
    n = x.size
    if n == 0:
        keys = ("mean", "ir", "t", "p", "nw_t", "nw_p")
        return {f"{prefix}_{k}": float("nan") for k in keys}

    mean = float(x.mean())
    std = float(x.std(ddof=1)) if n > 1 else float("nan")
    ir = mean / std if np.isfinite(std) and std > 0 else float("nan")

    plain_se = std / np.sqrt(n) if np.isfinite(std) and std > 0 else float("nan")
    t_stat, p_val = _t_and_p(mean, plain_se, n - 1)
    nw_t, nw_p = _t_and_p(mean, _newey_west_se(x, nw_lags), n - 1)

    return {
        f"{prefix}_mean": mean,
        f"{prefix}_ir": float(ir),
        f"{prefix}_t": t_stat,
        f"{prefix}_p": p_val,
        f"{prefix}_nw_t": nw_t,
        f"{prefix}_nw_p": nw_p,
    }


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------


class DeepFactorTester:
    """深度回測。建構子接下面板（昂貴，建一次），``run_all`` 一次測一個因子。

    面板在整個過程中不被修改，因此同一個 tester 可以安全地重複測多個因子。
    """

    def __init__(self, panel: pl.DataFrame, config: DeepBacktestConfig) -> None:
        self.config = config
        self._validate_panel(panel)

        n = config.holding_period
        self._return_col = config.return_col
        self._can_sell_col = f"{n}day_can_sell"
        self._early_col = f"{n}day_early_exit"
        self._lag_cols = [f"returns_lag{i}" for i in range(config.max_lag + 1)]

        # 一次性預先計算：宇宙過濾 + 進場條件。統計不在這裡跑。
        # select 產生新的 frame，傳入的面板不被修改。
        keep = [
            "symbol", "date",
            self._return_col, self._can_sell_col, self._early_col,
            "entry_can_buy", "untradable",
            *self._lag_cols,
        ]
        self._base = (
            panel.select(keep)
            .filter((pl.col("untradable") == 0) & (pl.col("entry_can_buy") == 1))
            .drop("untradable", "entry_can_buy")
        )
        # 覆蓋率以整張面板為分母，宇宙外的列也算「對得上」
        self._panel_keys = panel.select("symbol", "date")
        self._panel_dates = set(panel["date"].unique().to_list())
        self._panel_symbols = set(panel["symbol"].unique().to_list())

    # --- 驗證 ---------------------------------------------------------

    def _validate_panel(self, panel: pl.DataFrame) -> None:
        cfg = self.config
        required = [
            "symbol", "date", "untradable", "entry_can_buy",
            cfg.return_col,
            f"{cfg.holding_period}day_can_sell",
            f"{cfg.holding_period}day_early_exit",
            *[f"returns_lag{i}" for i in range(cfg.max_lag + 1)],
        ]
        missing = [c for c in required if c not in panel.columns]
        if missing:
            raise ValueError(
                f"面板缺少欄位 {missing}；請以相同的 config 呼叫 prepare_panel "
                f"（holding_period={cfg.holding_period}, max_lag={cfg.max_lag}）"
            )

    # --- 主流程 -------------------------------------------------------

    def run_all(self, factor_df: pl.DataFrame, name: str = "factor") -> DeepFactorResult:
        """測一個因子。``factor_df`` 為 (symbol, date, value) 三欄的因子框。"""
        cfg = self.config
        factor = self._normalise_factor(factor_df)
        cov = self._check_coverage(factor, name)

        rng = np.random.default_rng(cfg.seed)

        # 噪音按列位置配發，因此列序必須是決定性的——join 的輸出順序不保證穩定，
        # 少了這個 sort，同一份輸入跑兩次會拿到不同的分組。
        joined = (
            self._base.join(factor, on=["symbol", "date"], how="inner")
            .filter(pl.col(_FACTOR).is_not_null() & pl.col(_FACTOR).is_finite())
            .sort(["date", "symbol"])
            .with_columns(pl.col(_FACTOR).alias(_RAW))
        )

        # IC 衰減的固定樣本：只套進場條件，且要求所有 lag 都有值——樣本必須在
        # 每個 lag 上完全一致，否則衰減曲線會混入樣本數變化的效果（#7）。
        decay_base = joined.drop_nulls(subset=self._lag_cols)
        decay_base = self._winsorize(decay_base, rng)

        # 主樣本：再加上出場日的 can_sell 與報酬非空
        main = joined.filter(
            (pl.col(self._can_sell_col) == 1) & pl.col(self._return_col).is_not_null()
        )
        main = self._winsorize(main, rng)

        coverage = CoverageReport(
            factor_rows=cov.factor_rows,
            matched_rows=cov.matched_rows,
            coverage=cov.coverage,
            unmatched_dates=cov.unmatched_dates,
            unmatched_symbols=cov.unmatched_symbols,
            evaluated_rows=main.height,
        )

        ic_daily = self._daily_ic(main)
        group_returns, long_short, dropped_days = self._grouping(main, rng)
        decay = self._decay(decay_base)

        metrics: Dict[str, float] = {
            "n_days": float(ic_daily.height),
            "n_obs": float(main.height),
            **_series_stats(ic_daily["ic"], "IC", cfg.nw_lags),
            **_series_stats(ic_daily["rank_ic"], "Rank_IC", cfg.nw_lags),
        }
        if long_short.height:
            metrics["long_short_mean"] = float(long_short["ret"].mean())
            metrics.update(_series_stats(long_short["ret"], "long_short", cfg.nw_lags))
        else:
            metrics["long_short_mean"] = float("nan")

        early = int(main.filter(pl.col(self._early_col)).height) if main.height else 0

        return DeepFactorResult(
            name=name,
            config=cfg,
            coverage=coverage,
            ic_daily=ic_daily,
            group_returns=group_returns,
            long_short=long_short,
            decay=decay,
            metrics=metrics,
            early_exit_count=early,
            dropped_days=dropped_days,
        )

    # --- 因子框與覆蓋率 -----------------------------------------------

    def _normalise_factor(self, factor_df: pl.DataFrame) -> pl.DataFrame:
        missing = [c for c in FACTOR_COLS if c not in factor_df.columns]
        if missing:
            raise ValueError(
                f"因子框缺少欄位 {missing}；需要 (symbol, date, value) 三欄"
            )
        return factor_df.select(
            pl.col("symbol").cast(pl.String),
            pl.col("date").cast(pl.Date),
            # 未標準化的因子（市值、成交額量級）在 Float32 下會讓截面相關失去
            # 有效位數甚至變成 nan，一律升 Float64。
            pl.col("value").cast(pl.Float64).alias(_FACTOR),
        ).unique(subset=["symbol", "date"], keep="first", maintain_order=True)

    def _check_coverage(self, factor: pl.DataFrame, name: str) -> CoverageReport:
        rows = factor.height
        if rows == 0:
            raise ValueError(f"因子 {name!r} 的因子框是空的")

        matched = factor.join(self._panel_keys, on=["symbol", "date"], how="semi").height
        cov = matched / rows

        f_dates = set(factor["date"].unique().to_list())
        f_syms = set(factor["symbol"].unique().to_list())
        bad_dates = len(f_dates - self._panel_dates)
        bad_syms = len(f_syms - self._panel_symbols)

        report = CoverageReport(
            factor_rows=rows,
            matched_rows=matched,
            coverage=cov,
            unmatched_dates=bad_dates,
            unmatched_symbols=bad_syms,
            evaluated_rows=0,
        )
        if cov < self.config.min_coverage:
            raise ValueError(_coverage_message(name, report, self.config.min_coverage))
        return report

    # --- 前處理 -------------------------------------------------------

    def _noise(self, height: int, rng: np.random.Generator) -> pl.Series:
        """打散同值用的噪音。沿用 panda_factor 的 1e-10 量級。

        1e-10 相對於任何真實因子值都小到不影響排序，只影響平手的情形——沒有它，
        大量同值的因子（台股常見）會讓 qcut 切不出唯一的分組邊界。
        """
        return pl.Series(rng.normal(0.0, self.config.noise_std, height))

    def _winsorize(self, df: pl.DataFrame, rng: np.random.Generator) -> pl.DataFrame:
        """每日截面 3 倍標準差截斷。只截斷不置中，因子量級不變。"""
        if not df.height:
            return df
        # 去極值時加一次噪音（與 panda_factor 的 ext_out_3std 同）
        df = df.with_columns(pl.col(_FACTOR) + self._noise(df.height, rng))
        if not self.config.winsorize:
            return df
        k = self.config.winsorize_std
        mu = pl.col(_FACTOR).mean().over("date")
        sigma = pl.col(_FACTOR).std().over("date")
        return df.with_columns(
            pl.when(sigma.is_null() | (sigma == 0))
            .then(pl.col(_FACTOR))
            .otherwise(pl.col(_FACTOR).clip(mu - k * sigma, mu + k * sigma))
            .alias(_FACTOR)
        )

    # --- IC -----------------------------------------------------------

    def _daily_ic(self, main: pl.DataFrame) -> pl.DataFrame:
        """逐日截面 IC。樣本不足的日子在序列中缺席，不填 0。"""
        if not main.height:
            return pl.DataFrame(
                schema={"date": pl.Date, "n": pl.UInt32, "ic": pl.Float64, "rank_ic": pl.Float64}
            )
        return (
            main.group_by("date")
            .agg(
                pl.len().alias("n"),
                pl.corr(_FACTOR, self._return_col).alias("ic"),
                pl.corr(_FACTOR, self._return_col, method="spearman").alias("rank_ic"),
            )
            .filter(pl.col("n") >= self.config.min_names)
            .sort("date")
        )

    # --- 分組（#5）----------------------------------------------------

    def _grouping(
        self, main: pl.DataFrame, rng: np.random.Generator
    ) -> tuple[pl.DataFrame, pl.DataFrame, int]:
        """分組與多空價差。剔除已在上游完成，這裡的截面只含買賣得掉的股票。"""
        g = self.config.group_count
        empty_groups = pl.DataFrame(
            schema={"date": pl.Date, "group": pl.Int64, "ret": pl.Float64, "n": pl.UInt32}
        )
        empty_ls = pl.DataFrame(schema={"date": pl.Date, "ret": pl.Float64})
        if not main.height:
            return empty_groups, empty_ls, 0

        # 相異值不足以支撐分組數的日子整天丟棄，不做降級——三檔股票切成五組是
        # 假的分位數。相異值要在加噪音**之前**判定，否則噪音會讓每個值都不同。
        day_stats = main.group_by("date").agg(
            pl.len().alias("n"),
            pl.col(_RAW).n_unique().alias("n_unique"),
        )
        ok_dates = day_stats.filter(
            (pl.col("n") >= max(self.config.min_names, g))
            & (pl.col("n_unique") >= g)
        ).select("date")
        dropped = day_stats.height - ok_dates.height

        work = main.join(ok_dates, on="date", how="semi")
        if not work.height:
            return empty_groups, empty_ls, dropped

        # 分組前再加一次噪音（與 panda_factor 的 grouping_factor 同）
        work = work.with_columns(
            (pl.col(_FACTOR) + self._noise(work.height, rng)).alias(_GROUPED)
        )
        work = work.with_columns(
            pl.col(_GROUPED)
            .qcut(g, labels=[str(i) for i in range(g)], allow_duplicates=True)
            .over("date")
            .cast(pl.String)
            .cast(pl.Int64)
            .alias("group")
        )

        group_returns = (
            work.group_by("date", "group")
            .agg(pl.col(self._return_col).mean().alias("ret"), pl.len().alias("n"))
            .sort("date", "group")
        )

        wide = group_returns.pivot(on="group", index="date", values="ret")
        top, bottom = str(g - 1), "0"
        if top in wide.columns and bottom in wide.columns:
            long_short = wide.select(
                "date", (pl.col(top) - pl.col(bottom)).alias("ret")
            ).sort("date")
        else:
            long_short = empty_ls

        return group_returns, long_short, dropped

    # --- IC 衰減（#7）-------------------------------------------------

    def _decay(self, decay_base: pl.DataFrame) -> pl.DataFrame:
        """各 lag 的 IC。樣本由進場條件決定並在所有 lag 上保持一致。"""
        schema = {
            "lag": pl.Int64, "ic": pl.Float64, "rank_ic": pl.Float64,
            "n_days": pl.Int64, "n_obs": pl.Int64,
        }
        if not decay_base.height:
            return pl.DataFrame(schema=schema)

        daily = (
            decay_base.group_by("date")
            .agg(
                pl.len().alias("n"),
                *[pl.corr(_FACTOR, c).alias(f"ic_{c}") for c in self._lag_cols],
                *[
                    pl.corr(_FACTOR, c, method="spearman").alias(f"rank_{c}")
                    for c in self._lag_cols
                ],
            )
            .filter(pl.col("n") >= self.config.min_names)
        )
        if not daily.height:
            return pl.DataFrame(schema=schema)

        n_days = daily.height
        n_obs = int(daily["n"].sum())
        rows = []
        for i, col in enumerate(self._lag_cols):
            rows.append(
                {
                    "lag": i,
                    "ic": _mean_or_nan(daily[f"ic_{col}"]),
                    "rank_ic": _mean_or_nan(daily[f"rank_{col}"]),
                    "n_days": n_days,
                    "n_obs": n_obs,
                }
            )
        return pl.DataFrame(rows, schema=schema)


def _mean_or_nan(s: pl.Series) -> float:
    v = s.drop_nulls()
    return float(v.mean()) if v.len() else float("nan")


def _coverage_message(name: str, r: CoverageReport, threshold: float) -> str:
    if r.unmatched_dates and not r.unmatched_symbols:
        cause = f"日期範圍對不上（{r.unmatched_dates} 個日期不在面板中）"
    elif r.unmatched_symbols and not r.unmatched_dates:
        cause = f"代號格式對不上（{r.unmatched_symbols} 個代號不在面板中）"
    elif r.unmatched_dates and r.unmatched_symbols:
        cause = (
            f"日期與代號都有對不上的部分"
            f"（{r.unmatched_dates} 個日期、{r.unmatched_symbols} 個代號不在面板中）"
        )
    else:
        cause = "日期與代號個別都在面板中，但兩者的組合不在——請檢查因子的交易日曆"
    return (
        f"因子 {name!r} 與面板的覆蓋率 {r.coverage:.3f} 低於門檻 {threshold}："
        f"{r.matched_rows:,}/{r.factor_rows:,} 列對得上。{cause}。"
    )
