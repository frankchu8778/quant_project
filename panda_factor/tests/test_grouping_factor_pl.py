"""Phase 2 A/B 等價測試：grouping_factor_pl（polars）vs grouping_factor（pandas）。"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import polars as pl
import pytest

from panda_factor.analysis.factor_func import grouping_factor
from panda_factor.analysis.factor_func_pl import (
    BENCHMARK_COLUMNS,
    grouping_factor_pl,
    to_backtest_contract,
)

from conftest import seeded

ATOL = 1e-8
FACTOR = "test_factor"
GROUP_COL = f"{FACTOR}_group"
GROUP_CNT = 5
BENCH_COLS = [dst for _, dst in BENCHMARK_COLUMNS]
RETURN_COLS = [src for src, _ in BENCHMARK_COLUMNS]


@pytest.fixture(scope="module")
def prepared(panel) -> pd.DataFrame:
    """對齊 _reference_pipeline 中 grouping_factor 之前的狀態。"""
    from _reference_pipeline import prepare_factor_frame

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            return prepare_factor_frame(panel, factor_name=FACTOR)


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 主要等價性
# --------------------------------------------------------------------------- #
def test_group_assignment_equivalence(prepared):
    """分組指派必須與 pandas 版逐筆相同。

    pandas 版的 1e-10 噪音無法由參數關閉（factor_func.py:826 寫死），
    polars 版則以 noise_std=0 取得確定性 —— 兩者若一致，正說明該噪音
    確實不影響分箱（與 Phase 0 的實測結論一致）。
    """
    with seeded():
        exp_cuted, _ = grouping_factor(
            df=prepared.copy(), factor_name=FACTOR, group_cnt=GROUP_CNT
        )
    act_cuted, _ = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )

    exp = _sorted(exp_cuted)
    act = _sorted(act_cuted.to_pandas())

    assert len(act) == len(exp), f"留存列數不同: {len(exp)} vs {len(act)}"
    a = act[GROUP_COL].to_numpy().astype(int)
    b = exp[GROUP_COL].to_numpy().astype(int)
    mismatch = int((a != b).sum())
    assert mismatch == 0, f"分組指派不一致 {mismatch}/{len(a)} 筆"


def test_benchmark_equivalence(prepared):
    """df_benchmark 六欄數值與日期集合必須一致。"""
    with seeded():
        _, exp_bm = grouping_factor(
            df=prepared.copy(), factor_name=FACTOR, group_cnt=GROUP_CNT
        )
    _, act_bm_pl = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    _, act_bm = to_backtest_contract(pl.DataFrame(), act_bm_pl)

    assert list(act_bm.index) == list(exp_bm.index), "benchmark 日期集合不同"
    for col in BENCH_COLS:
        a = act_bm[col].to_numpy(dtype=float)
        b = exp_bm[col].to_numpy(dtype=float)
        assert np.array_equal(np.isnan(a), np.isnan(b)), f"{col} 缺值位置不同"
        ok = ~np.isnan(a)
        if ok.any():
            diff = np.max(np.abs(a[ok] - b[ok]))
            assert diff <= ATOL, f"{col} 最大偏離 {diff:.3e}"


def test_row_order_matches_pandas(prepared):
    """輸出列序須與 pandas 版逐列相同（日期遞增、日內維持原序）。

    實作內部用了 semi-join，而 polars 並未保證 join 的保序性；此測試把
    「明確還原列序」這件事釘住，避免日後相依於未定義行為而靜默錯位。
    """
    with seeded():
        exp_cuted, _ = grouping_factor(
            df=prepared.copy(), factor_name=FACTOR, group_cnt=GROUP_CNT
        )
    act_cuted, _ = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    act = act_cuted.to_pandas()

    assert (exp_cuted["symbol"].to_numpy() == act["symbol"].to_numpy()).all(), "symbol 列序不同"
    assert (
        pd.to_datetime(exp_cuted["date"]).to_numpy() == act["date"].to_numpy()
    ).all(), "date 列序不同"


def test_group_sizes_are_balanced(prepared):
    """分組必須真的均分 —— 否則等價測試在兩版都壞掉時也會通過。"""
    cuted, _ = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    counts = cuted[GROUP_COL].value_counts().sort(GROUP_COL)["count"].to_list()
    assert len(counts) == GROUP_CNT, f"組數不是 {GROUP_CNT}: {counts}"
    assert max(counts) - min(counts) <= len(cuted) * 0.02, f"分組明顯不均: {counts}"


# --------------------------------------------------------------------------- #
# 輸出契約（factor.start_backtest 的相依）
# --------------------------------------------------------------------------- #
def test_group_column_is_integer_comparable(prepared):
    """factor.py:305 以 `== n`（整數）篩選分組，欄位型別必須支援。

    polars 的 qcut 回傳 Categorical；直接 cast 成整數會取到 0-based 的
    **類別索引**而非標籤值，且不會報錯。這裡確保實作沒有踩到該陷阱。
    """
    cuted, _ = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    pdf = cuted.to_pandas()

    assert pd.api.types.is_integer_dtype(pdf[GROUP_COL]), (
        f"分組欄型別為 {pdf[GROUP_COL].dtype}，無法與整數比較"
    )
    assert set(pdf[GROUP_COL].unique()) == set(range(1, GROUP_CNT + 1)), (
        f"分組標籤應為 1..{GROUP_CNT}，實得 {sorted(pdf[GROUP_COL].unique())}；"
        f"若為 0..{GROUP_CNT - 1} 即是誤取類別索引"
    )
    for n in range(1, GROUP_CNT + 1):
        assert len(pdf[pdf[GROUP_COL] == n]) > 0, f"以 == {n} 篩選不到任何列"


def test_categorical_cast_trap_is_real():
    """佐證上述陷阱確實存在，說明實作為何要多繞一次字串轉換。"""
    s = pl.Series("x", [10.0, 20.0, 30.0, 40.0])
    cut = s.qcut(2, labels=["1", "2"])
    wrong = cut.cast(pl.Int32).to_list()
    right = cut.cast(pl.Utf8).cast(pl.Int32).to_list()
    assert wrong == [0, 0, 1, 1], f"預期類別索引 0/1，實得 {wrong}"
    assert right == [1, 1, 2, 2], f"預期標籤值 1/2，實得 {right}"


def test_benchmark_contract_is_date_indexed(prepared):
    """factor.py:309 以 .loc[date, f'{period}D_m'] 讀取，需為日期 index。"""
    _, bm_pl = grouping_factor_pl(
        pl.from_pandas(prepared), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    _, bm = to_backtest_contract(pl.DataFrame(), bm_pl)

    assert isinstance(bm.index, pd.DatetimeIndex), f"index 型別為 {type(bm.index)}"
    assert list(bm.columns) == BENCH_COLS
    some_date = bm.index[0]
    assert isinstance(float(bm.loc[some_date, "1D_m"]), float)


# --------------------------------------------------------------------------- #
# 邊界案例
# --------------------------------------------------------------------------- #
def _tiny(values_by_date: dict) -> pd.DataFrame:
    rows = []
    for date, vals in values_by_date.items():
        for i, v in enumerate(vals):
            row = {"date": pd.Timestamp(date), "symbol": f"s{i}", FACTOR: v}
            for k, c in enumerate(RETURN_COLS):
                row[c] = 0.01 * (k + 1) + 0.001 * i
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    "label, data",
    [
        ("正常日", {"2024-01-01": list(np.linspace(0, 1, 20))}),
        ("相異值不足", {"2024-01-01": [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]}),
        ("含單一缺值", {"2024-01-01": [*np.linspace(0, 1, 19), np.nan]}),
        (
            "混合多日",
            {
                "2024-01-01": list(np.linspace(0, 1, 20)),
                "2024-01-02": [1.0, 1.0, 1.0, 1.0],
                "2024-01-03": [*np.linspace(0, 1, 19), np.nan],
            },
        ),
    ],
)
def test_edge_cases_match_pandas(label, data):
    """退化情況下「哪些日子被剔除」必須與 pandas 版完全一致。"""
    df = _tiny(data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            exp_cuted, exp_bm = grouping_factor(
                df=df.copy(), factor_name=FACTOR, group_cnt=GROUP_CNT
            )
    act_cuted_pl, act_bm_pl = grouping_factor_pl(
        pl.from_pandas(df), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    act_cuted = act_cuted_pl.to_pandas()

    exp_dates = sorted(pd.to_datetime(exp_cuted["date"]).unique()) if len(exp_cuted) else []
    act_dates = sorted(pd.to_datetime(act_cuted["date"]).unique()) if len(act_cuted) else []
    assert act_dates == exp_dates, f"[{label}] 留存日期不同"
    assert len(act_cuted) == len(exp_cuted), f"[{label}] 留存列數不同"

    # 被剔除的日子仍必須出現在 benchmark
    assert len(act_bm_pl) == len(exp_bm), f"[{label}] benchmark 日期數不同"


def test_skipped_day_still_in_benchmark():
    """明確固定「日子被剔除但仍留在 benchmark」這項 pandas 行為。"""
    df = _tiny(
        {
            "2024-01-01": list(np.linspace(0, 1, 20)),
            "2024-01-02": [1.0, 1.0, 1.0],  # 相異值不足，會被剔除
        }
    )
    cuted, bm = grouping_factor_pl(
        pl.from_pandas(df), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    assert cuted["date"].n_unique() == 1, "應只留下一天"
    assert bm.height == 2, "benchmark 應保留兩天"


def test_group_cnt_out_of_range_falls_back_to_ten():
    """group_cnt 超出 2..20 時強制改為 10（factor_func.py:784-789）。"""
    df = _tiny({"2024-01-01": list(np.linspace(0, 1, 100))})
    cuted, _ = grouping_factor_pl(
        pl.from_pandas(df), FACTOR, group_cnt=25, noise_std=0.0
    )
    assert cuted[GROUP_COL].n_unique() == 10


def test_all_days_invalid_returns_empty():
    """所有日子都無效時回傳空的 df_cuted，但 benchmark 仍完整。"""
    df = _tiny({"2024-01-01": [1.0, 1.0], "2024-01-02": [2.0, 2.0]})
    cuted, bm = grouping_factor_pl(
        pl.from_pandas(df), FACTOR, group_cnt=GROUP_CNT, noise_std=0.0
    )
    assert cuted.height == 0
    assert GROUP_COL in cuted.columns, "空結果仍須有分組欄，否則下游取欄會 KeyError"
    assert bm.height == 2


# --------------------------------------------------------------------------- #
# 整合：Phase 1 + Phase 2 一起替換
# --------------------------------------------------------------------------- #
def test_full_chain_with_phase1_and_phase2(panel):
    """前處理與分組都換成 polars 後，回測最終產物必須不變。"""
    from _reference_pipeline import (
        prepare_factor_frame,
        prepare_factor_frame_pl,
        run_chain_polars_grouping,
        run_pandas_chain,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            ref = run_pandas_chain(panel)
        with seeded():
            act = run_chain_polars_grouping(panel, prepare=prepare_factor_frame_pl)

    assert len(act["df_cuted"]) == len(ref["df_cuted"])

    a = _sorted(ref["df_cuted"])[GROUP_COL].to_numpy().astype(int)
    b = _sorted(act["df_cuted"])[GROUP_COL].to_numpy().astype(int)
    assert (a == b).all(), f"分組指派不一致（{int((a != b).sum())} 筆）"

    for col in ["ic", "rank_ic", "ir"]:
        x = act["df_ic"][col].to_numpy(dtype=float)
        y = ref["df_ic"][col].to_numpy(dtype=float)
        assert np.array_equal(np.isnan(x), np.isnan(y)), f"df_ic[{col}] 缺值位置不同"
        ok = ~np.isnan(x)
        assert np.max(np.abs(x[ok] - y[ok])) <= ATOL, f"df_ic[{col}] 偏離過大"

    pd.testing.assert_frame_equal(
        act["df_pnl"].astype(float), ref["df_pnl"].astype(float),
        rtol=ATOL, atol=ATOL, check_dtype=False, obj="df_pnl",
    )
    assert act["df_info2"].equals(ref["df_info2"]), "df_info2 指標改變"
