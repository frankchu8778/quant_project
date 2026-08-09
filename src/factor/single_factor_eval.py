"""單因子**快篩**：前置報酬計算 + 分組/IC 回測封裝。

**這是快篩，不是深度回測。允許粗糙，其結果不得作為因子有效性的結論。**

用途是在大量因子上以最低成本刷一遍、篩掉明顯無效者。通過快篩的少數因子必須改用
``src/factor/components/deep_panel.py`` 與其評估模組重跑，才能得出結論。

與深度回測的具體差異（都是會讓快篩結果偏樂觀的方向）：

- **只過濾因子宇宙（untradable），不檢查 can_buy / can_sell。** 進場日鎖漲停買不到、
  出場日鎖跌停賣不掉的部位照樣算進來。因子值越極端的股票越容易撞上漲跌停，而那正是
  多空組合的兩端。
- **不處理減資造成的提前出場。** 部位就這樣掛在停牌期間，出場日取名目日期。
- **t 統計量未對自相關修正，且缺值先 fillna(0)。** 重疊持有期讓日 IC 高度自相關，
  未修正的 t 被系統性放大；fillna(0) 又額外壓低序列標準差。``passes_ic_screen`` 預設的
  ``t_abs=2.0`` 在 5 日重疊報酬下等效於 t > 0.67，形同虛設——請把它當成排序用的分數，
  不是顯著性門檻。
- **經由 panda_factor 的 grouping_factor 分組**，該函數內部的 unable_trade 過濾被註解掉、
  樣本不足的日子靜默跳過、且加了未設種子的隨機噪音。

深度回測的完整規格見 GitHub issue #1；相關決策見 docs/adr/。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from IPython.display import display
from panda_factor.panda_factor.panda_factor.analysis.factor import factor
from panda_factor.panda_factor.panda_factor.analysis.factor_func import (
    cal_pct_lag,
    ext_out_3std,
    grouping_factor,
)
from scipy.stats import ttest_1samp

# (名稱, 賣出日相對 T+1 的偏移, 進場日偏移)
# 例：1day_return = close[T+2]/close[T+1]-1
DEFAULT_RETURN_WINDOWS: Tuple[Tuple[str, int, int], ...] = (
    ("1day_return", 2, 1),
    ("3day_return", 4, 1),
    ("5day_return", 6, 1),
    ("10day_return", 11, 1),
    ("20day_return", 21, 1),
    ("30day_return", 31, 1),
)


def add_forward_returns(
    df: pl.DataFrame,
    price_col: str = "close_adj",
    windows: Sequence[Tuple[str, int, int]] = DEFAULT_RETURN_WINDOWS,
    overwrite: bool = False,
) -> pl.DataFrame:
    """
    在原始 df 寫入未來報酬欄位。
    因子在 T 日形成，T+1 收盤進場，T+n+1 收盤出場。
    """
    if price_col not in df.columns:
        raise ValueError(f"df 缺少價格欄位 {price_col!r}")

    need = [name for name, _, _ in windows if overwrite or name not in df.columns]
    if not need:
        return df

    exprs = []
    for name, end_lead, start_lead in windows:
        if name not in need:
            continue
        exprs.append(
            (
                pl.col(price_col).shift(-end_lead).over("symbol")
                / pl.col(price_col).shift(-start_lead).over("symbol")
                - 1
            ).alias(name)
        )
    return df.sort(["symbol", "date"]).with_columns(exprs)


def add_returns_lag(
    df: pl.DataFrame,
    source_col: str = "1day_return",
    max_lag: int = 20,
    overwrite: bool = False,
) -> pl.DataFrame:
    """把 1day_return 往前推 0..max_lag 天，寫成 returns_lag{i}（等同 cal_pct_lag）。"""
    if source_col not in df.columns:
        raise ValueError(f"df 缺少 {source_col!r}，請先呼叫 add_forward_returns")

    exprs = []
    for i in range(0, max_lag + 1):
        col = f"returns_lag{i}"
        if not overwrite and col in df.columns:
            continue
        exprs.append(pl.col(source_col).shift(-i).over("symbol").alias(col))
    if not exprs:
        return df
    return df.sort(["symbol", "date"]).with_columns(exprs)


def prepare_eval_returns(
    df: pl.DataFrame,
    price_col: str = "close_adj",
    windows: Sequence[Tuple[str, int, int]] = DEFAULT_RETURN_WINDOWS,
    max_lag: int = 20,
) -> pl.DataFrame:
    """一次補齊驗證用的未來報酬與 lag 報酬。"""
    df = add_forward_returns(df, price_col=price_col, windows=windows)
    df = add_returns_lag(df, source_col="1day_return", max_lag=max_lag)
    return df


def screen_factor_ic_metrics(
    df: pl.DataFrame,
    factor_name: str,
    return_col: str = "1day_return",
    min_names: int = 5,
    winsorize: bool = True,
) -> Dict[str, Any]:
    """
    快速計算單因子 IC 篩選指標（不跑分組／換手／lag IC）。

    回傳欄位對齊 panda_factor.df_info2 口徑：
    - Rank_IC / Rank_IC_IR：來自每日 Spearman（Rank IC）
    - t統計量：來自每日 Pearson IC（與 start_backtest 相同，缺值填 0 後做單樣本 t）
    """
    if factor_name not in df.columns:
        raise ValueError(f"df 缺少因子欄 {factor_name!r}")
    if return_col not in df.columns:
        raise ValueError(f"df 缺少報酬欄 {return_col!r}")

    cols = ["date", factor_name, return_col]
    if "untradable" in df.columns:
        cols.append("untradable")
    work = df.select(cols)
    if "untradable" in work.columns:
        work = work.filter(pl.col("untradable") == 0)

    work = work.with_columns(
        pl.when(pl.col(factor_name).is_infinite())
        .then(None)
        .otherwise(pl.col(factor_name))
        .alias(factor_name)
    ).drop_nulls(subset=[factor_name, return_col])

    if winsorize and work.height:
        mu = pl.col(factor_name).mean().over("date")
        sigma = pl.col(factor_name).std().over("date")
        work = work.with_columns(
            pl.col(factor_name).clip(mu - 3.0 * sigma, mu + 3.0 * sigma).alias(factor_name)
        )

    daily = (
        work.group_by("date")
        .agg(
            pl.len().alias("n"),
            pl.corr(factor_name, return_col).alias("ic"),
            pl.corr(factor_name, return_col, method="spearman").alias("rank_ic"),
        )
        .filter(pl.col("n") >= min_names)
        .sort("date")
    )
    if daily.height == 0:
        return {
            "factor": factor_name,
            "n_days": 0,
            "Rank_IC": np.nan,
            "Rank_IC_IR": np.nan,
            "t統計量": np.nan,
            "p-value": np.nan,
            "IC_mean": np.nan,
        }

    rank_ic = daily["rank_ic"].drop_nulls()
    ic = daily["ic"].fill_null(0.0)
    rank_ic_mean = float(rank_ic.mean()) if rank_ic.len() else np.nan
    rank_ic_std = float(rank_ic.std()) if rank_ic.len() > 1 else np.nan
    if rank_ic_std and np.isfinite(rank_ic_std) and rank_ic_std != 0:
        rank_ic_ir = rank_ic_mean / rank_ic_std
    else:
        rank_ic_ir = np.nan

    ic_arr = ic.to_numpy()
    if len(ic_arr) > 1:
        t_stat, p_value = ttest_1samp(ic_arr, popmean=0)
    else:
        t_stat, p_value = np.nan, np.nan

    return {
        "factor": factor_name,
        "n_days": int(daily.height),
        "Rank_IC": rank_ic_mean,
        "Rank_IC_IR": float(rank_ic_ir) if np.isfinite(rank_ic_ir) else np.nan,
        "t統計量": float(t_stat) if np.isfinite(t_stat) else np.nan,
        "p-value": float(p_value) if np.isfinite(p_value) else np.nan,
        "IC_mean": float(ic.mean()) if ic.len() else np.nan,
    }


def passes_ic_screen(
    metrics: Dict[str, Any],
    rank_ic_abs: float = 0.02,
    rank_ic_ir_abs: float = 0.5,
    t_abs: float = 2.0,
) -> bool:
    """是否同時通過 Rank_IC / Rank_IC_IR / t 門檻。"""
    try:
        rank_ic = abs(float(metrics["Rank_IC"]))
        rank_ic_ir = abs(float(metrics["Rank_IC_IR"]))
        t_stat = abs(float(metrics["t統計量"]))
    except (TypeError, ValueError, KeyError):
        return False
    return (
        np.isfinite(rank_ic)
        and np.isfinite(rank_ic_ir)
        and np.isfinite(t_stat)
        and rank_ic > rank_ic_abs
        and rank_ic_ir > rank_ic_ir_abs
        and t_stat > t_abs
    )


def _metric_as_float(value: Any) -> float:
    """panda_factor 統計值可能是字串 / 空字串，統一轉成 float。"""
    if value is None:
        return float("nan")
    if isinstance(value, (float, int, np.floating, np.integer)):
        value = float(value)
        return value if np.isfinite(value) else float("nan")
    text = str(value).replace("%", "").strip()
    if text == "" or text.lower() == "nan":
        return float("nan")
    return float(text)


def _resolve_df_info2_key(df_info2: pd.DataFrame, *candidates: str) -> str:
    """在 df_info2.index 找第一個存在的候選鍵（相容簡繁體）。"""
    index = df_info2.index
    for key in candidates:
        if key in index:
            return key
    raise KeyError(
        f"df_info2 缺少任一候選鍵 {candidates}，現有 index={list(index)}"
    )


def extract_df_info2_metrics(alpha, factor_name: str) -> Dict[str, float]:
    """
    從 panda_factor 回測物件讀取篩選用指標。

    注意：上游 index 可能是簡體「t统计量」或繁體「t統計量」。
    """
    info2 = alpha.df_info2
    rank_ic_key = _resolve_df_info2_key(info2, "Rank_IC")
    rank_ic_ir_key = _resolve_df_info2_key(info2, "Rank_IC_IR")
    t_key = _resolve_df_info2_key(info2, "t統計量", "t統計量")
    return {
        "Rank_IC": _metric_as_float(info2.at[rank_ic_key, factor_name]),
        "Rank_IC_IR": _metric_as_float(info2.at[rank_ic_ir_key, factor_name]),
        "t統計量": _metric_as_float(info2.at[t_key, factor_name]),
    }


def run_single_factor_test(
    df: pl.DataFrame,
    factor_name: str = "test_factor",
    group_count: int = 5,
    period: int = 1,
    predict_direction: int = 1,
    return_cols: Optional[Iterable[str]] = None,
    show_plots: bool = True,
):
    """
    對 df 中的單一因子做去極值、五分組、IC 回測，並在 cell 內顯示結果。
    假設 df 已有未來報酬欄（見 prepare_eval_returns）。
    """
    if factor_name not in df.columns:
        raise ValueError(f"請先建立 df['{factor_name}']")

    if return_cols is None:
        return_cols = [name for name, _, _ in DEFAULT_RETURN_WINDOWS]
    return_cols = list(return_cols)
    missing_ret = [c for c in return_cols if c not in df.columns]
    if missing_ret:
        raise ValueError(
            f"df 缺少報酬欄 {missing_ret}，請先呼叫 prepare_eval_returns(df)"
        )

    lag_cols = [c for c in df.columns if c.startswith("returns_lag")]
    keep = ["date", "symbol", factor_name, "untradable", *return_cols, *lag_cols]

    df_factor = (
        df.select([c for c in keep if c in df.columns])
        .filter(pl.col("untradable") == 0)
        .to_pandas()
    )
    df_factor["date"] = pd.to_datetime(df_factor["date"])
    df_factor = df_factor.replace([np.inf, -np.inf], np.nan).dropna(subset=[factor_name])

    if "returns_lag1" not in df_factor.columns:
        df_factor = cal_pct_lag(df_factor)

    df_factor = df_factor.groupby("date", group_keys=False).apply(
        lambda g: ext_out_3std(g.copy(), factor_name, process_inf=True)
    )
    df_factor = df_factor[np.isfinite(df_factor[factor_name])].copy()
    df_cuted, df_benchmark = grouping_factor(
        df=df_factor,
        factor_name=factor_name,
        group_cnt=group_count,
    )

    alpha = factor(name=factor_name, group_number=group_count)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    alpha.start_backtest(df_cuted, df_benchmark)

    print("多空分組統計")
    display(alpha.df_info)
    print("IC 統計")
    display(alpha.df_info2)

    if show_plots:
        alpha.draw_pct()
        plt.show()
        alpha.draw_ic(0)
        plt.show()
        alpha.draw_ic(1)
        plt.show()
        alpha.draw_ic_dacay()
        plt.show()

    return alpha
