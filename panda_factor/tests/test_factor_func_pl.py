"""Phase 1 A/B 等價測試：factor_func_pl（polars）vs factor_func（pandas）。

兩版在**同一份輸入**上並行計算並逐欄比對。這是 additive 策略的核心價值 ——
不需要信任 baseline 快照，直接以現行 pandas 實作為準繩。
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import polars as pl
import pytest

from panda_factor.analysis.factor_func import cal_pct_lag, ext_out_3std
from panda_factor.analysis.factor_func_pl import (
    cal_pct_lag_pl,
    ext_out_3std_pl,
    nan_to_null,
)

ATOL = 1e-8
FACTOR = "test_factor"
LAG_COLS = [f"returns_lag{i}" for i in range(0, 21)]


# --------------------------------------------------------------------------- #
# 共用輸入
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def base_frame(panel) -> pd.DataFrame:
    """對齊 _reference_pipeline.prepare_factor_frame 中 cal_pct_lag 之前的狀態。"""
    cols = [
        "date", "symbol", FACTOR, "untradable",
        "1day_return", "3day_return", "5day_return",
        "10day_return", "20day_return", "30day_return",
    ]
    df = panel[cols].copy()
    df = df[df["untradable"] == 0]
    df["date"] = pd.to_datetime(df["date"])
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[FACTOR])
    return df.reset_index(drop=True)


def _assert_cols_close(got: pd.DataFrame, exp: pd.DataFrame, cols, label: str):
    """逐欄比對，NaN 位置也必須一致。"""
    for col in cols:
        a = pd.to_numeric(got[col], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(exp[col], errors="coerce").to_numpy(dtype=float)

        na_a, na_b = np.isnan(a), np.isnan(b)
        mismatched = int((na_a != na_b).sum())
        assert mismatched == 0, f"{label}: {col} 的 NaN 位置不一致（{mismatched} 筆）"

        both = ~na_a
        if both.any():
            diff = np.max(np.abs(a[both] - b[both]))
            assert diff <= ATOL, f"{label}: {col} 最大偏離 {diff:.3e} > {ATOL:.0e}"


# --------------------------------------------------------------------------- #
# cal_pct_lag
# --------------------------------------------------------------------------- #
def test_cal_pct_lag_equivalence(base_frame):
    """21 個 returns_lag 欄必須與 pandas 版逐值相同。"""
    expected = cal_pct_lag(base_frame.copy())
    actual = cal_pct_lag_pl(pl.from_pandas(base_frame)).to_pandas()

    assert len(actual) == len(expected)
    _assert_cols_close(actual, expected, LAG_COLS, "cal_pct_lag")


def test_cal_pct_lag_preserves_row_order(base_frame):
    """輸出列序必須與輸入相同（下游以位置對齊，順序改變會靜默錯位）。"""
    actual = cal_pct_lag_pl(pl.from_pandas(base_frame)).to_pandas()
    pd.testing.assert_series_equal(
        actual["symbol"], base_frame["symbol"], check_names=False
    )
    pd.testing.assert_series_equal(
        actual["date"], base_frame["date"], check_names=False
    )


def test_cal_pct_lag_shifts_within_symbol(base_frame):
    """lag 位移不可跨標的洩漏：每檔最後 i 列的 returns_lag{i} 必為缺值。"""
    actual = cal_pct_lag_pl(pl.from_pandas(base_frame))
    tail = (
        actual.sort(["symbol", "date"])
        .group_by("symbol", maintain_order=True)
        .tail(1)
    )
    for i in (1, 5, 20):
        assert tail[f"returns_lag{i}"].is_null().all() or bool(
            tail[f"returns_lag{i}"].is_nan().fill_null(True).all()
        ), f"returns_lag{i} 在標的邊界發生跨標的洩漏"


# --------------------------------------------------------------------------- #
# ext_out_3std
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lagged_frame(base_frame) -> pd.DataFrame:
    return cal_pct_lag(base_frame.copy())


def _pandas_ext(df: pd.DataFrame, noise_std: float, process_inf: bool) -> pd.DataFrame:
    """複刻呼叫端的 groupby-apply 用法（single_factor_eval.py:286）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return df.groupby("date", group_keys=False).apply(
            lambda g: ext_out_3std(
                g.copy(), FACTOR, noise_std=noise_std, process_inf=process_inf
            )
        )


@pytest.mark.parametrize("process_inf", [False, True])
def test_ext_out_3std_equivalence(lagged_frame, process_inf):
    """關噪音（noise_std=0）以取得確定性，比對去極值後的因子值。"""
    expected = _pandas_ext(lagged_frame, noise_std=0.0, process_inf=process_inf)
    actual = ext_out_3std_pl(
        pl.from_pandas(lagged_frame), FACTOR, noise_std=0.0, process_inf=process_inf
    ).to_pandas()

    expected = expected.sort_values(["date", "symbol"]).reset_index(drop=True)
    actual = actual.sort_values(["date", "symbol"]).reset_index(drop=True)
    _assert_cols_close(actual, expected, [FACTOR], f"ext_out_3std(inf={process_inf})")


def test_ext_out_3std_default_noise_within_tolerance(lagged_frame):
    """使用預設 1e-10 噪音時，兩版差異仍須落在容差內。"""
    expected = _pandas_ext(lagged_frame, noise_std=1e-10, process_inf=True)
    actual = ext_out_3std_pl(
        pl.from_pandas(lagged_frame), FACTOR, process_inf=True
    ).to_pandas()

    expected = expected.sort_values(["date", "symbol"]).reset_index(drop=True)
    actual = actual.sort_values(["date", "symbol"]).reset_index(drop=True)
    _assert_cols_close(actual, expected, [FACTOR], "ext_out_3std(預設噪音)")


def test_ext_out_3std_actually_clips(lagged_frame):
    """去極值必須真的生效 —— 否則上面的等價測試在兩版都不動時也會通過。"""
    before = lagged_frame[FACTOR].to_numpy()
    after = ext_out_3std_pl(
        pl.from_pandas(lagged_frame), FACTOR, noise_std=0.0
    )[FACTOR].to_numpy()

    changed = np.nansum(np.abs(after - before) > 1e-12)
    assert changed > 0, "沒有任何值被 clip，測試失去鑑別力"


# --------------------------------------------------------------------------- #
# 邊界案例
# --------------------------------------------------------------------------- #
def _tiny(values_by_date: dict) -> pd.DataFrame:
    rows = []
    for date, vals in values_by_date.items():
        for i, v in enumerate(vals):
            rows.append({"date": pd.Timestamp(date), "symbol": f"s{i}", FACTOR: v})
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    "label, data",
    [
        ("單列日", {"2024-01-01": [5.0]}),
        ("常數日", {"2024-01-01": [2.0, 2.0, 2.0, 2.0]}),
        ("含缺值", {"2024-01-01": [1.0, np.nan, 3.0, 100.0]}),
        ("全缺值", {"2024-01-01": [np.nan, np.nan]}),
        ("兩列日", {"2024-01-01": [1.0, 9.0]}),
        ("多日混合", {"2024-01-01": [1.0, 2.0, 50.0], "2024-01-02": [np.nan, 4.0, 5.0]}),
    ],
)
def test_ext_out_3std_edge_cases(label, data):
    """std 為 NaN（單列/常數）、全缺值等退化情況兩版行為必須一致。"""
    df = _tiny(data)
    expected = _pandas_ext(df, noise_std=0.0, process_inf=True)
    actual = ext_out_3std_pl(
        pl.from_pandas(df), FACTOR, noise_std=0.0, process_inf=True
    ).to_pandas()

    expected = expected.sort_values(["date", "symbol"]).reset_index(drop=True)
    actual = actual.sort_values(["date", "symbol"]).reset_index(drop=True)
    _assert_cols_close(actual, expected, [FACTOR], f"邊界[{label}]")


def test_native_polars_nan_does_not_poison_cross_section():
    """polars 原生 NaN（如 0/0）不得汙染整個截面。

    這是 pandas → polars 最容易靜默出錯之處：polars 區分 NaN 與 null，
    且 NaN 具傳染性，未正規化時單一 NaN 會讓當日 mean/std 變成 NaN、
    使 clip 邊界失效，整個截面原封不動地通過。
    """
    # 30 個常態點 + 1 個遠離群值 + 1 個原生 NaN。
    # 常態點數量足夠，離群值才不會自己把 std 撐大到 3σ 邊界之外而躲過 clip。
    n = 30
    num = [1.0 + 0.01 * i for i in range(n)] + [500.0, 0.0]
    den = [1.0] * (n + 1) + [0.0]  # 最後一列 0/0 → 原生 NaN
    df = pl.DataFrame(
        {
            "date": ["d1"] * (n + 2),
            "symbol": [f"s{i}" for i in range(n + 2)],
            "num": num,
            "den": den,
        }
    ).with_columns((pl.col("num") / pl.col("den")).alias(FACTOR))

    assert df[FACTOR].is_nan().sum() == 1, "前提不成立：未產生原生 NaN"

    out = ext_out_3std_pl(df, FACTOR, noise_std=0.0)
    outlier = out[FACTOR].to_numpy()[n]
    assert outlier < 500.0, "極端值未被 clip —— NaN 汙染使邊界失效"

    # 對照組：證明本測試有鑑別力 —— 少了 NaN 正規化，同樣的資料會整片躲過 clip
    naive = df.with_columns(
        pl.col(FACTOR).clip(
            pl.col(FACTOR).mean().over("date") - 3.0 * pl.col(FACTOR).std().over("date"),
            pl.col(FACTOR).mean().over("date") + 3.0 * pl.col(FACTOR).std().over("date"),
        )
    )
    assert naive[FACTOR].to_numpy()[n] == 500.0, (
        "未正規化版本竟然也 clip 了，本測試無法證明正規化的必要性"
    )


def test_polars_prep_is_drop_in_equivalent_in_full_chain(panel):
    """整合驗證：把前處理換成 polars 版後，完整鏈的最終產物必須不變。

    單元等價不等於管線等價 —— 例如列序改變或 NaN/null 表述差異，都可能在單元測試
    通過後才於下游 grouping_factor / start_backtest 產生偏移。
    """
    from conftest import seeded
    from _reference_pipeline import (
        prepare_factor_frame_pl,
        run_pandas_chain,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            ref = run_pandas_chain(panel)
        with seeded():
            hybrid = run_pandas_chain(panel, prepare=prepare_factor_frame_pl)

    assert len(hybrid["df_cuted"]) == len(ref["df_cuted"]), "留存列數改變"

    grp = f"{FACTOR}_group"
    a = ref["df_cuted"].sort_values(["date", "symbol"])[grp].to_numpy()
    b = hybrid["df_cuted"].sort_values(["date", "symbol"])[grp].to_numpy()
    assert (a == b).all(), f"分組指派不一致（{int((a != b).sum())} 筆）"

    for col in ["ic", "rank_ic", "ir"]:
        _assert_cols_close(hybrid["df_ic"], ref["df_ic"], [col], "full-chain df_ic")

    pd.testing.assert_frame_equal(
        hybrid["df_pnl"].astype(float),
        ref["df_pnl"].astype(float),
        rtol=ATOL, atol=ATOL, check_dtype=False, obj="full-chain df_pnl",
    )
    assert hybrid["df_info2"].equals(ref["df_info2"]), "df_info2 指標改變"


def test_nan_to_null_only_touches_float_columns():
    """nan_to_null 不得動到非浮點欄。"""
    df = pl.DataFrame(
        {"s": ["a", "b"], "i": [1, 2], "f": [float("nan"), 2.0]}
    )
    out = nan_to_null(df, ["s", "i", "f"])
    assert out["s"].to_list() == ["a", "b"]
    assert out["i"].to_list() == [1, 2]
    assert out["f"].null_count() == 1
