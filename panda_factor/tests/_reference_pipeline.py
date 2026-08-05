"""現行 pandas 鏈的權威參考實作（golden-master 的產生器）。

這裡逐步複刻 src/factor/single_factor_eval.py:275-298 `run_single_factor_test` 的
呼叫順序，**刻意不做任何「順手修正」** — 包含看起來可疑的部分（例如先 dropna 再
cal_pct_lag，使 shift 跨越被刪除的列）。golden-master 的價值在於固定「現況」，
而非固定「應然」；任何行為修正都必須是獨立、可見的一次變更。

輸出的 artifacts 即為 Phase 1-3 polars 實作的比對基準。
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from panda_factor.analysis.factor import factor
from panda_factor.analysis.factor_func import (
    cal_pct_lag,
    ext_out_3std,
    grouping_factor,
)

RETURN_COLS = [
    "1day_return",
    "3day_return",
    "5day_return",
    "10day_return",
    "20day_return",
    "30day_return",
]


def prepare_factor_frame(
    panel: pd.DataFrame,
    factor_name: str = "test_factor",
) -> pd.DataFrame:
    """前處理：過濾不可交易 → 清 inf/NaN → cal_pct_lag → 逐日 ext_out_3std。

    對應 single_factor_eval.py:272-289。
    """
    lag_cols = [c for c in panel.columns if c.startswith("returns_lag")]
    keep = ["date", "symbol", factor_name, "untradable", *RETURN_COLS, *lag_cols]

    df_factor = panel[[c for c in keep if c in panel.columns]].copy()
    df_factor = df_factor[df_factor["untradable"] == 0]

    df_factor["date"] = pd.to_datetime(df_factor["date"])
    df_factor = df_factor.replace([np.inf, -np.inf], np.nan).dropna(subset=[factor_name])

    if "returns_lag1" not in df_factor.columns:
        df_factor = cal_pct_lag(df_factor)

    df_factor = df_factor.groupby("date", group_keys=False).apply(
        lambda g: ext_out_3std(g.copy(), factor_name, process_inf=True)
    )
    df_factor = df_factor[np.isfinite(df_factor[factor_name])].copy()
    return df_factor


def prepare_factor_frame_pl(
    panel: pd.DataFrame,
    factor_name: str = "test_factor",
) -> pd.DataFrame:
    """與 prepare_factor_frame 相同的前處理，但改用 Phase 1 的 polars 實作。

    僅替換 cal_pct_lag 與 ext_out_3std 兩步；其餘（欄位挑選、過濾、inf/NaN 清理）
    維持 pandas，以便把差異侷限在受測的兩個函式上。回傳 pandas 以銜接下游。
    """
    import polars as pl

    from panda_factor.analysis.factor_func_pl import cal_pct_lag_pl, ext_out_3std_pl

    lag_cols = [c for c in panel.columns if c.startswith("returns_lag")]
    keep = ["date", "symbol", factor_name, "untradable", *RETURN_COLS, *lag_cols]

    df_factor = panel[[c for c in keep if c in panel.columns]].copy()
    df_factor = df_factor[df_factor["untradable"] == 0]
    df_factor["date"] = pd.to_datetime(df_factor["date"])
    df_factor = df_factor.replace([np.inf, -np.inf], np.nan).dropna(subset=[factor_name])

    pdf = pl.from_pandas(df_factor.reset_index(drop=True))
    if "returns_lag1" not in pdf.columns:
        pdf = cal_pct_lag_pl(pdf)
    pdf = ext_out_3std_pl(pdf, factor_name, process_inf=True)

    out = pdf.to_pandas()
    return out[np.isfinite(out[factor_name])].copy()


def run_pandas_chain(
    panel: pd.DataFrame,
    factor_name: str = "test_factor",
    group_count: int = 5,
    period: int = 1,
    predict_direction: int = 1,
    prepare=prepare_factor_frame,
) -> Dict[str, Any]:
    """跑完整現行 pandas 鏈，回傳所有需要納入 golden-master 的中間與最終產物。

    :param prepare: 前處理實作，預設為純 pandas 版；傳入 prepare_factor_frame_pl
        可在下游完全不變的前提下驗證 polars 版是否 drop-in 等價。
    """
    df_factor = prepare(panel, factor_name=factor_name)

    df_cuted, df_benchmark = grouping_factor(
        df=df_factor,
        factor_name=factor_name,
        group_cnt=group_count,
    )

    alpha = factor(name=factor_name, group_number=group_count)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    alpha.start_backtest(df_cuted, df_benchmark)

    return {
        "df_prepared": df_factor,
        "df_cuted": df_cuted,
        "df_benchmark": df_benchmark,
        "df_pnl": alpha.df_pnl,
        "df_ic": alpha.df_ic,
        "df_info": alpha.df_info,
        "df_info2": alpha.df_info2,
        "alpha": alpha,
    }


def run_full_polars_chain(
    panel: pd.DataFrame,
    factor_name: str = "test_factor",
    group_count: int = 5,
    period: int = 1,
    predict_direction: int = 1,
) -> Dict[str, Any]:
    """Phase 1 + 2 + 3 全部採用 polars 實作的完整鏈。"""
    import polars as pl

    from panda_factor.analysis.factor_func_pl import grouping_factor_pl
    from panda_factor.analysis.factor_pl import factor_pl

    df_factor = prepare_factor_frame_pl(panel, factor_name=factor_name)

    cuted_pl, bench_pl = grouping_factor_pl(
        pl.from_pandas(df_factor.reset_index(drop=True)),
        factor_name,
        group_cnt=group_count,
        noise_std=0.0,
    )

    alpha = factor_pl(name=factor_name, group_number=group_count)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    alpha.start_backtest(cuted_pl, bench_pl)

    return {
        "df_prepared": df_factor,
        "df_cuted": cuted_pl.to_pandas(),
        "df_benchmark": bench_pl.to_pandas(),
        "df_pnl": alpha.df_pnl,
        "df_ic": alpha.df_ic,
        "df_info": alpha.df_info,
        "df_info2": alpha.df_info2,
        "alpha": alpha,
    }


def run_chain_polars_grouping(
    panel: pd.DataFrame,
    factor_name: str = "test_factor",
    group_count: int = 5,
    period: int = 1,
    predict_direction: int = 1,
    prepare=prepare_factor_frame,
) -> Dict[str, Any]:
    """與 run_pandas_chain 相同，但分組改用 Phase 2 的 grouping_factor_pl。

    下游 ``factor.start_backtest`` 仍為 pandas 版，透過 to_backtest_contract 銜接 ——
    這正是要驗證的：polars 產物是否滿足 start_backtest 的 index/dtype 相依。
    """
    import polars as pl

    from panda_factor.analysis.factor_func_pl import (
        grouping_factor_pl,
        to_backtest_contract,
    )

    df_factor = prepare(panel, factor_name=factor_name)

    cuted_pl, bench_pl = grouping_factor_pl(
        pl.from_pandas(df_factor.reset_index(drop=True)),
        factor_name,
        group_cnt=group_count,
        noise_std=0.0,
    )
    df_cuted, df_benchmark = to_backtest_contract(cuted_pl, bench_pl)

    alpha = factor(name=factor_name, group_number=group_count)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    alpha.start_backtest(df_cuted, df_benchmark)

    return {
        "df_prepared": df_factor,
        "df_cuted": df_cuted,
        "df_benchmark": df_benchmark,
        "df_pnl": alpha.df_pnl,
        "df_ic": alpha.df_ic,
        "df_info": alpha.df_info,
        "df_info2": alpha.df_info2,
        "alpha": alpha,
    }
