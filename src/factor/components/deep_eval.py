"""深度單因子回測：可交易性檢驗、IC、顯著性、分組、IC 衰減。

與 ``single_factor_eval.py``（快篩）並存、職責分開。快篩允許粗糙，其結果不得作為
因子有效性的結論；本模組承接少數通過快篩的因子，做嚴格驗證。

嚴格的具體含義是三件事：

1. **可交易性在真正成交的那一天判定**——進場日看 ``can_buy``、出場日看 ``can_sell``，
   任一端不通過該檔當日整筆從截面剔除，且**剔除先於分組**（ADR-0002）。
2. **報酬跨越停牌照實計算**，不設 NA（ADR-0001）。
3. **統計只在換倉日上做**——交易日曆上每 ``holding_period`` 天取一天，相鄰兩列的
   持有區間不重疊，序列因此對應單一帳戶走過的路徑（ADR-0003）。未修正的 t 與
   Newey-West t 仍並列輸出，且 IC 缺值就是缺值，不 ``fillna(0)``。

全部計算走 polars，不 import panda_factor，只沿用其指標定義以維持可比性。

昂貴的面板建一次、多個因子重複測::

    tester = DeepFactorTester(panel, config)
    result_a = tester.run_all(factor_a, name="alpha101_005")
    result_b = tester.run_all(factor_b, name="alpha191_026")

術語一律以 CONTEXT.md 為準。規格見 GitHub issue #1。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence

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
    #: 逐次換倉的成交權重與交易成本：date, group, buy_weight, sell_weight, cost。
    #: 多空那些列的 group 為 null，其成本是兩腿相加。第一次換倉為 0。
    cost_daily: pl.DataFrame
    #: 分組績效（panda_factor 口徑）：group, label, annual_return, annual_volatility,
    #: max_drawdown, sharpe, monthly_win_rate, mean_return, avg_names, turnover，
    #: 加上成本欄 buy_weight, sell_weight, cost_annual 與扣後的 net_* 並列指標。
    #: 最後一列是多空組合，其 group 為 null。
    group_stats: pl.DataFrame
    #: 匯總指標（Rank_IC / ICIR / t / Newey-West t / 門檻比例 / 單調性 ...）
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

    def to_dict(self, *, include_series: bool = False) -> dict:
        """可直接 ``json.dump`` 的結果字典。

        ``include_series=True`` 會附上逐日 IC 與分組報酬；預設不附，因為那會讓
        單一因子的 JSON 膨脹到數百 KB，批次輸出時很快就沒法看。
        """

        def clean(x):
            """NaN/Inf 不是合法的 JSON 數值，一律轉成 null。"""
            if isinstance(x, float) and not np.isfinite(x):
                return None
            return x

        out = {
            "name": self.name,
            "holding_period": self.config.holding_period,
            "group_count": self.config.group_count,
            "coverage": {
                "coverage": clean(self.coverage.coverage),
                "factor_rows": self.coverage.factor_rows,
                "matched_rows": self.coverage.matched_rows,
                "evaluated_rows": self.coverage.evaluated_rows,
                "unmatched_dates": self.coverage.unmatched_dates,
                "unmatched_symbols": self.coverage.unmatched_symbols,
            },
            "metrics": {k: clean(v) for k, v in self.metrics.items()},
            "group_stats": [
                {k: clean(v) for k, v in row.items()}
                for row in self.group_stats.to_dicts()
            ],
            "decay": [
                {k: clean(v) for k, v in row.items()} for row in self.decay.to_dicts()
            ],
            "early_exit_count": self.early_exit_count,
            "dropped_days": self.dropped_days,
        }
        if include_series:
            out["ic_daily"] = [
                {**row, "date": row["date"].isoformat()}
                for row in self.ic_daily.to_dicts()
            ]
            out["long_short_daily"] = [
                {"date": row["date"].isoformat(), "ret": clean(row["ret"])}
                for row in self.long_short.to_dicts()
            ]
            # 驗收條件要求手算單日成本對得上，沒有這條序列只能對年化數字
            out["cost_daily"] = [
                {
                    **{k: clean(v) for k, v in row.items() if k != "date"},
                    "date": row["date"].isoformat(),
                }
                for row in self.cost_daily.to_dicts()
            ]
        return out

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

        # 換倉日網格。定義在**面板的交易日曆**上而不是因子自己的日期上，因此同一份
        # 面板下所有因子共用同一組換倉日，彼此可比。
        calendar = panel.select("date").unique().sort("date")["date"].to_list()
        self._rebalance_dates = calendar[:: config.holding_period]

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

        # 只留換倉日（ADR-0003）。每一列因此對應一次真實換倉，前後不共用持有區間；
        # 分組報酬加總起來就是單一帳戶走過的路徑，而不是 n 個平行帳戶的平均。
        # holding_period=1 時每個交易日都是換倉日，這個過濾是恆等的。
        joined = joined.filter(pl.col("date").is_in(self._rebalance_dates))

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
        group_returns, long_short, dropped_days, roster = self._grouping(main, rng)
        decay = self._decay(decay_base)
        cost_daily = self._cost_daily(roster, group_returns["date"])
        cost_daily = pl.concat(
            [cost_daily, self._long_short_cost(cost_daily)], how="vertical_relaxed"
        ).sort("date", "group", nulls_last=True)
        group_stats = self._group_stats(group_returns, long_short, roster, cost_daily)

        metrics: Dict[str, float] = {
            "n_days": float(ic_daily.height),
            "n_obs": float(main.height),
            **_series_stats(ic_daily["ic"], "IC", cfg.nw_lags),
            **_series_stats(ic_daily["rank_ic"], "Rank_IC", cfg.nw_lags),
            **_threshold_stats(ic_daily["rank_ic"]),
        }
        # 即使多空序列是空的也要把鍵放進去（值為 nan）。metrics 的鍵集合必須與因子
        # 無關，否則把多個因子的 summary() 疊起來時欄位對不齊，會炸在 concat。
        ls_ret = (
            long_short["ret"]
            if long_short.height
            else pl.Series("ret", [], dtype=pl.Float64)
        )
        metrics.update(_series_stats(ls_ret, "long_short", cfg.nw_lags))
        # 扣成本後的多空序列。鍵集合同樣必須與因子無關，空序列也要出現。
        ls_net = (
            long_short.sort("date")
            .join(cost_daily.filter(pl.col("group").is_null()), on="date", how="left")
            .select((pl.col("ret") - pl.col("cost").fill_null(0.0)).alias("ret"))["ret"]
            if long_short.height
            else pl.Series("ret", [], dtype=pl.Float64)
        )
        metrics.update(_series_stats(ls_net, "net_long_short", cfg.nw_lags))

        by_group = group_stats.filter(pl.col("group").is_not_null()).sort("group")
        metrics["monotonicity"] = _monotonicity(by_group["annual_return"].to_list())

        early = int(main.filter(pl.col(self._early_col)).height) if main.height else 0

        return DeepFactorResult(
            name=name,
            config=cfg,
            coverage=coverage,
            ic_daily=ic_daily,
            group_returns=group_returns,
            long_short=long_short,
            cost_daily=cost_daily,
            decay=decay,
            group_stats=group_stats,
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
    ) -> tuple[pl.DataFrame, pl.DataFrame, int, pl.DataFrame]:
        """分組與多空價差。剔除已在上游完成，這裡的截面只含買賣得掉的股票。

        第四個回傳值是分組名冊（date, symbol, group），換手率由它算出。
        """
        g = self.config.group_count
        empty_groups = pl.DataFrame(
            schema={"date": pl.Date, "group": pl.Int64, "ret": pl.Float64, "n": pl.UInt32}
        )
        empty_ls = pl.DataFrame(schema={"date": pl.Date, "ret": pl.Float64})
        empty_roster = pl.DataFrame(
            schema={"date": pl.Date, "symbol": pl.String, "group": pl.Int64}
        )
        if not main.height:
            return empty_groups, empty_ls, 0, empty_roster

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
            return empty_groups, empty_ls, dropped, empty_roster

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

        roster = work.select("date", "symbol", "group")
        return group_returns, long_short, dropped, roster

    def _group_stats(
        self,
        group_returns: pl.DataFrame,
        long_short: pl.DataFrame,
        roster: pl.DataFrame,
        cost_daily: pl.DataFrame,
    ) -> pl.DataFrame:
        """各分組與多空組合的績效表（panda_factor 口徑）+ 扣成本後的並列指標。

        ``group`` 欄為組別編號，多空組合那一列的 ``group`` 是 null。

        ``net_*`` 是**逐次換倉扣掉成本之後**重算的同一組指標，與 gross 並列而非
        取代——年化報酬的差是線性的，但夏普、最大回撤、月勝率不是，從年化報酬扣
        一次算不出正確的值。
        """
        period = self.config.holding_period
        turnover = self._turnover(roster)
        turnover_map = dict(zip(turnover["group"].to_list(), turnover["turnover"].to_list()))
        scale = TRADING_DAYS / period

        def with_cost(rets: pl.DataFrame, group) -> dict:
            """一條報酬序列的 net 指標與成交權重。成本對不上的日子當成 0。"""
            part = cost_daily.filter(
                pl.col("group").is_null() if group is None else pl.col("group") == group
            )
            joined = (
                rets.join(part, on="date", how="left")
                .with_columns(
                    pl.col("cost").fill_null(0.0),
                    pl.col("buy_weight").fill_null(0.0),
                    pl.col("sell_weight").fill_null(0.0),
                )
                .sort("date")
            )
            net = joined.select((pl.col("ret") - pl.col("cost")).alias("net"))["net"]
            perf = _performance(joined["date"], net, period)
            return {
                "buy_weight": float(joined["buy_weight"].mean()),
                "sell_weight": float(joined["sell_weight"].mean()),
                "cost_annual": float(joined["cost"].mean() * scale),
                **{f"net_{k}": v for k, v in perf.items() if k != "n_periods"},
            }

        rows = []
        for group in sorted(group_returns["group"].unique().to_list()) if group_returns.height else []:
            part = group_returns.filter(pl.col("group") == group).sort("date")
            rows.append(
                {
                    "group": int(group),
                    "label": f"group{int(group) + 1}",
                    **_performance(part["date"], part["ret"], period),
                    "mean_return": float(part["ret"].mean()),
                    "avg_names": float(part["n"].mean()),
                    "turnover": float(turnover_map.get(group, float("nan"))),
                    **with_cost(part.select("date", "ret"), int(group)),
                }
            )

        if long_short.height:
            ls = long_short.sort("date")
            g = self.config.group_count
            # 多空的換手率取兩端的平均，與 panda_factor 一致
            ends = [turnover_map.get(0, float("nan")), turnover_map.get(g - 1, float("nan"))]
            rows.append(
                {
                    "group": None,
                    "label": "long_short",
                    **_performance(ls["date"], ls["ret"], period),
                    "mean_return": float(ls["ret"].mean()),
                    "avg_names": float("nan"),
                    "turnover": float(np.nanmean(ends)) if np.any(np.isfinite(ends)) else float("nan"),
                    **with_cost(ls.select("date", "ret"), None),
                }
            )

        if not rows:
            return pl.DataFrame(
                schema={
                    "group": pl.Int64, "label": pl.String, "annual_return": pl.Float64,
                    "annual_volatility": pl.Float64, "max_drawdown": pl.Float64,
                    "sharpe": pl.Float64, "monthly_win_rate": pl.Float64,
                    "n_periods": pl.Float64, "mean_return": pl.Float64,
                    "avg_names": pl.Float64, "turnover": pl.Float64,
                    "buy_weight": pl.Float64, "sell_weight": pl.Float64,
                    "cost_annual": pl.Float64, "net_annual_return": pl.Float64,
                    "net_annual_volatility": pl.Float64, "net_max_drawdown": pl.Float64,
                    "net_sharpe": pl.Float64, "net_monthly_win_rate": pl.Float64,
                }
            )
        return pl.DataFrame(rows)

    def _cost_daily(
        self, roster: pl.DataFrame, dates: pl.Series
    ) -> pl.DataFrame:
        """逐次換倉的成交權重與交易成本：date, group, buy_weight, sell_weight, cost。

        成交權重是**實際動到的資金比例**，不是換手的檔數比例。等權前提下每檔的
        目標權重是 1/n，逐檔比較本期與上期的權重::

            buy_weight  = Σ max(w_now - w_prev, 0)
            sell_weight = Σ max(w_prev - w_now, 0)

        兩者恆落在 0 到 1 之間。留倉股因組內檔數變動而被加減碼的流量也計在內——
        100 萬買 5 檔改成 6 檔時，原本 5 檔各賣一點去補的那些錢是真的付了手續費，
        而數檔數的換手率會把它算成 0。

        未模型化持有期間內價格漂移造成的權重偏移（實際上還要再平衡一次），因此
        算出來的成本是**下限**。

        第一次換倉沒有上一期可比，成本為 0；建倉本身的成本不計，攤在整個樣本上
        可以忽略。網格上的洞（該次換倉被整天丟棄）同樣為 0。
        """
        cfg = self.config
        schema = {
            "date": pl.Date, "group": pl.Int64,
            "buy_weight": pl.Float64, "sell_weight": pl.Float64, "cost": pl.Float64,
        }
        if not roster.height:
            return pl.DataFrame(schema=schema)

        idx = pl.DataFrame(
            {"date": self._rebalance_dates}, schema={"date": pl.Date}
        ).with_row_index("day_idx")

        cur = (
            roster.join(idx, on="date", how="inner")
            .select("day_idx", "symbol", "group")
            .with_columns(
                (1.0 / pl.len().over("day_idx", "group")).alias("w")
            )
        )
        # 上一期的權重往後推一格，就能與本期在同一個 day_idx 上逐檔比對
        prev = cur.with_columns(pl.col("day_idx") + 1).rename({"w": "w_prev"})

        # 兩期任一有部位的個股都要出現，否則整批換掉的部分會漏算
        paired = cur.join(
            prev, on=["day_idx", "symbol", "group"], how="full", coalesce=True
        ).with_columns(
            pl.col("w").fill_null(0.0), pl.col("w_prev").fill_null(0.0)
        )
        # 只留兩期都在的換倉：少了這一步，第一次換倉會被算成 buy_weight=1
        both = (
            cur.select("day_idx", "group").unique()
            .join(prev.select("day_idx", "group").unique(), on=["day_idx", "group"])
        )
        paired = paired.join(both, on=["day_idx", "group"], how="semi")

        weights = (
            paired.group_by("day_idx", "group")
            .agg(
                (pl.col("w") - pl.col("w_prev")).clip(lower_bound=0.0).sum().alias("buy_weight"),
                (pl.col("w_prev") - pl.col("w")).clip(lower_bound=0.0).sum().alias("sell_weight"),
            )
            .join(idx, on="day_idx", how="inner")
            .drop("day_idx")
        )

        # 沒有上一期可比的換倉日補 0，讓成本序列與報酬序列在同一組日期上對齊
        grid = (
            pl.DataFrame({"date": dates}, schema={"date": pl.Date})
            .unique()
            .join(weights.select("group").unique(), how="cross")
        )
        return (
            grid.join(weights, on=["date", "group"], how="left")
            .with_columns(
                pl.col("buy_weight").fill_null(0.0),
                pl.col("sell_weight").fill_null(0.0),
            )
            .with_columns(
                (
                    pl.col("buy_weight") * cfg.buy_cost_rate
                    + pl.col("sell_weight") * cfg.sell_cost_rate
                ).alias("cost")
            )
            .select("date", "group", "buy_weight", "sell_weight", "cost")
            .sort("date", "group")
        )

    def _long_short_cost(self, cost_daily: pl.DataFrame) -> pl.DataFrame:
        """多空組合的成本：兩腿**相加**，不取平均。

        多空是同時持有兩個各自滿倉的組合，兩邊的手續費都真的付了。既有的
        ``turnover`` 欄位仍維持 panda_factor 取平均的口徑（那是名冊換手率，
        只供對照），不要拿它跟這裡的數字比。

        空頭腿套用與多頭腿相同的費率——不做空，因此不含借券費與保證金成本。
        """
        g = self.config.group_count
        out = cost_daily.filter(pl.col("group").is_in([0, g - 1]))
        if not out.height:
            return cost_daily.head(0)
        return (
            out.group_by("date")
            .agg(
                pl.col("buy_weight").sum(),
                pl.col("sell_weight").sum(),
                pl.col("cost").sum(),
            )
            .with_columns(pl.lit(None, dtype=pl.Int64).alias("group"))
            .select("date", "group", "buy_weight", "sell_weight", "cost")
        )

    def _turnover(self, roster: pl.DataFrame) -> pl.DataFrame:
        """各組的平均換手率：本期在組內、上期不在的比例（panda_factor 口徑）。

        分母是**上一期**的組內檔數，因此組別大小變動時不會被稀釋。比較的對象是
        上一個換倉日的名冊。
        """
        empty = pl.DataFrame(schema={"group": pl.Int64, "turnover": pl.Float64})
        if not roster.height:
            return empty

        # 序號打在**換倉日網格**上而不是名冊自己的日期上：某個換倉日若因相異值
        # 不足被整天丟棄（``dropped_days``），網格上會留下一個洞，位移之後那一次
        # 換倉自然對不到上一期而被排除——不會把隔了兩期的兩張名冊誤當成相鄰。
        idx = pl.DataFrame(
            {"date": self._rebalance_dates}, schema={"date": pl.Date}
        ).with_row_index("day_idx")
        cur = roster.join(idx, on="date", how="inner").select("day_idx", "symbol", "group")
        # 把上一期的名冊往後推一格，就能與本期在同一個 day_idx 上比對
        prev = cur.with_columns(pl.col("day_idx") + 1)

        stayed = (
            cur.join(prev, on=["day_idx", "symbol", "group"], how="semi")
            .group_by("day_idx", "group")
            .agg(pl.len().alias("stayed"))
        )
        counts = cur.group_by("day_idx", "group").agg(pl.len().alias("n_now"))
        prev_counts = prev.group_by("day_idx", "group").agg(pl.len().alias("n_prev"))

        daily = (
            counts.join(prev_counts, on=["day_idx", "group"], how="inner")
            .join(stayed, on=["day_idx", "group"], how="left")
            .with_columns(pl.col("stayed").fill_null(0))
            .with_columns(
                ((pl.col("n_now") - pl.col("stayed")) / pl.col("n_prev")).alias("turnover")
            )
        )
        return (
            daily.group_by("group")
            .agg(pl.col("turnover").mean().alias("turnover"))
            .sort("group")
        )

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


# ---------------------------------------------------------------------------
# 分組績效（panda_factor 口徑）
# ---------------------------------------------------------------------------
#
# 這一段刻意複製 panda_factor 的算法細節，即使有些做法不是我會挑的，因為它的用途
# 是與既有結果對照。逐項說明差異：
#
# - 最大回撤走**算術累加**（cumsum）而非複利累乘，量級與報酬序列同單位。
# - 年化波動用母體標準差（ddof=0）——panda_factor 呼叫 np.std，預設就是 ddof=0。
# - 夏普扣固定 2.5% 無風險利率，算不出來時給 0 而不是 nan。
# - 勝率按**自然月**加總後計算，不是逐日勝率。
#
# 一律不算 benchmark 衍生的指標（超額年化、跟蹤誤差、資訊比率、超額勝率）：
# 上游的 benchmark 是宇宙內等權平均而非市場指數。

#: 年化基準交易日數。
TRADING_DAYS = 252
#: 夏普比率使用的無風險利率，沿用 panda_factor 的固定值。
RISK_FREE_RATE = 0.025
#: Rank IC 的門檻，用於統計勝負天數比例。
IC_THRESHOLD = 0.02


def _max_drawdown(rets: np.ndarray) -> float:
    """算術累積報酬的最大回撤（panda_factor 口徑，非複利）。"""
    if rets.size == 0:
        return float("nan")
    cum = np.cumsum(rets)
    return float(np.max(np.maximum.accumulate(cum) - cum))


def _monthly_win_rate(dates: pl.Series, rets: pl.Series) -> float:
    """按自然月加總後為正的月份比例。"""
    if rets.len() == 0:
        return float("nan")
    monthly = (
        pl.DataFrame({"date": dates, "ret": rets})
        .group_by(pl.col("date").dt.truncate("1mo"))
        .agg(pl.col("ret").sum())
    )
    return float((monthly["ret"] > 0).sum() / monthly.height)


def _performance(dates: pl.Series, rets: pl.Series, period: int) -> Dict[str, float]:
    """單一報酬序列的績效指標。"""
    values = rets.drop_nulls()
    if values.len() == 0:
        return {
            k: float("nan")
            for k in ("annual_return", "annual_volatility", "max_drawdown",
                      "sharpe", "monthly_win_rate", "n_periods")
        }

    arr = values.to_numpy().astype(float)
    scale = TRADING_DAYS / period
    annual_return = float(arr.mean() * scale)
    annual_vol = float(arr.std(ddof=0) * np.sqrt(scale))

    sharpe = (annual_return - RISK_FREE_RATE) / annual_vol if annual_vol else float("inf")
    if not np.isfinite(sharpe):
        sharpe = 0.0  # panda_factor 的處理：算不出來就給 0

    return {
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "max_drawdown": _max_drawdown(arr),
        "sharpe": float(sharpe),
        "monthly_win_rate": _monthly_win_rate(dates, rets),
        "n_periods": float(values.len()),
    }


def _monotonicity(annual_returns: Sequence[float]) -> float:
    """分組年化報酬與組序的相關係數絕對值。1 代表完美單調。"""
    arr = np.asarray(annual_returns, dtype=float)
    if arr.size < 2 or not np.all(np.isfinite(arr)) or np.std(arr) == 0:
        return float("nan")
    return float(abs(np.corrcoef(arr, np.arange(1, arr.size + 1))[0, 1]))


def _threshold_stats(rank_ic: pl.Series, threshold: float = IC_THRESHOLD) -> Dict[str, float]:
    """Rank IC 超過 ±threshold 的天數比例。

    panda_factor 的 ``P(IC>0.02)`` 名字寫 IC、算的是 rank_ic（原始碼註解：
    「P 阈值统计改用 Rank IC」）。這裡沿用它實際的算法，並把名字改成不會誤導的。
    """
    values = rank_ic.drop_nulls()
    n = values.len()
    if n == 0:
        return {
            "P_rank_ic_gt": float("nan"),
            "P_rank_ic_lt": float("nan"),
            "P_rank_ic_abs_gt": float("nan"),
        }
    gt = float((values > threshold).sum() / n)
    lt = float((values < -threshold).sum() / n)
    return {
        "P_rank_ic_gt": gt,
        "P_rank_ic_lt": lt,
        "P_rank_ic_abs_gt": gt + lt,
    }


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
