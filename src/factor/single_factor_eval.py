"""單因子驗證：前置報酬計算 + 分組/IC 回測封裝。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from IPython.display import display

# 一律使用短路徑 panda_factor.analysis.*。原本的三層重複路徑
# （panda_factor.panda_factor.panda_factor.analysis）已不再可解析，實測會拋
# ModuleNotFoundError；editable install 的 finder 只把 'panda_factor' 對應到
# 套件根目錄，並未註冊巢狀目錄。
from panda_factor.analysis.factor_func_pl import (
    cal_pct_lag_pl,
    ext_out_3std_pl,
    grouping_factor_pl,
)
from panda_factor.analysis.factor_pl import factor_pl
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


def prepare_factor_frame(
    df: pl.DataFrame,
    factor_name: str,
    return_cols: Optional[Iterable[str]] = None,
    max_lag: int = 20,
) -> pl.DataFrame:
    """回測前處理：挑欄 → 濾不可交易 → 清 inf → 補 lag → 逐日 3-sigma 去極值。

    全程留在 polars。前四步合成單一 lazy plan 只 collect 一次，讓投影下推把不需要的
    欄位在讀取階段就砍掉；去極值則以 ``.over("date")`` 視窗運算取代原本
    ``groupby("date").apply()`` 的逐日 Python 迴圈。

    與原 pandas 版的對應關係（語意刻意保持一致）：
    - ``replace([inf, -inf], nan)`` → ``is_infinite()`` 轉 null，同樣作用於所有浮點欄
      （非浮點欄不可能有 inf，故省略不影響結果）
    - ``dropna(subset=[factor_name])`` → ``drop_nulls(subset=[factor_name])``
    - ``np.isfinite(...)`` 過濾 → ``is_finite()``；polars 對 null 回傳 null 而 filter
      會一併丟棄，因此連 NaN 與 null 的處理都與 pandas 相同（已實測確認）

    :returns: 可直接餵給 :func:`grouping_factor_pl` 的 polars DataFrame
    """
    if factor_name not in df.columns:
        raise ValueError(f"df 缺少因子欄 {factor_name!r}")
    for required in ("date", "symbol"):
        if required not in df.columns:
            raise ValueError(f"df 缺少 {required!r} 欄（分組與持倉統計都需要）")

    if return_cols is None:
        return_cols = [name for name, _, _ in DEFAULT_RETURN_WINDOWS]

    lag_cols = [c for c in df.columns if c.startswith("returns_lag")]
    keep = ["date", "symbol", factor_name, "untradable", *return_cols, *lag_cols]
    keep = [c for c in dict.fromkeys(keep) if c in df.columns]

    schema = df.schema
    float_cols = [c for c in keep if schema[c] in (pl.Float32, pl.Float64)]

    lf = df.lazy().select(keep)
    # untradable 為選用欄；原版無條件 filter，欄位不存在時會拋 ColumnNotFoundError
    if "untradable" in keep:
        lf = lf.filter(pl.col("untradable") == 0)
    if schema["date"] == pl.Utf8:
        lf = lf.with_columns(pl.col("date").str.to_datetime())
    lf = lf.with_columns(
        [
            pl.when(pl.col(c).is_infinite()).then(None).otherwise(pl.col(c)).alias(c)
            for c in float_cols
        ]
    ).drop_nulls(subset=[factor_name])

    work = lf.collect()

    # 通常不觸發：prepare_eval_returns 已備妥 returns_lag0..max_lag
    if "returns_lag1" not in work.columns:
        work = cal_pct_lag_pl(work, max_lag=max_lag)

    work = ext_out_3std_pl(work, factor_name, process_inf=True)
    return work.filter(pl.col(factor_name).is_finite())


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

    整條鏈全部走 polars 實作（``*_pl``），不再有中途轉 pandas 的邊界：
    前處理 → ``grouping_factor_pl`` → ``factor_pl.start_backtest``。
    只有最終的小型彙總表（``df_info`` / ``df_info2``，列數 ≈ 分組數）與 matplotlib
    繪圖仍是 pandas —— 那是刻意保留的，資料量小且 ``display()`` 與 matplotlib
    本就預期 pandas 物件，硬轉只會增加介面成本。
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

    df_factor = prepare_factor_frame(df, factor_name, return_cols)
    df_cuted, df_benchmark = grouping_factor_pl(
        df_factor,
        factor_name=factor_name,
        group_cnt=group_count,
    )

    alpha = factor_pl(name=factor_name, group_number=group_count)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    # factor_pl 直接吃 polars，不需要 to_backtest_contract 轉換
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
