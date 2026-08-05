"""Phase 3 A/B 等價測試：factor_pl（polars）vs factor（pandas）。"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import polars as pl
import pytest

from panda_factor.analysis.factor import factor
from panda_factor.analysis.factor_func import grouping_factor
from panda_factor.analysis.factor_pl import factor_pl

from conftest import seeded

ATOL = 1e-8
FACTOR = "test_factor"
GROUP_CNT = 5


@pytest.fixture(scope="module")
def cuted_and_benchmark(panel):
    """跑到 grouping_factor 為止，取得 start_backtest 的輸入。"""
    from _reference_pipeline import prepare_factor_frame

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            prep = prepare_factor_frame(panel, factor_name=FACTOR)
        with seeded():
            return grouping_factor(
                df=prep.copy(), factor_name=FACTOR, group_cnt=GROUP_CNT
            )


def _run(cls, cuted, bench, period=1, predict_direction=1, group_cnt=GROUP_CNT):
    alpha = cls(name=FACTOR, group_number=group_cnt)
    alpha.set_backtest_parameters(period=period, predict_direction=predict_direction)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alpha.start_backtest(cuted, bench)
    return alpha


def _assert_frame_close(actual: pd.DataFrame, expected: pd.DataFrame, label: str):
    assert list(actual.columns) == list(expected.columns), (
        f"{label} 欄位順序不同\n  ref={list(expected.columns)}\n  act={list(actual.columns)}"
    )
    assert list(actual.index) == list(expected.index), f"{label} index 不同"
    for col in expected.columns:
        a = pd.to_numeric(actual[col], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(expected[col], errors="coerce").to_numpy(dtype=float)
        assert np.array_equal(np.isnan(a), np.isnan(b)), f"{label}: {col} 缺值位置不同"
        ok = ~np.isnan(a)
        if ok.any():
            diff = np.max(np.abs(a[ok] - b[ok]))
            assert diff <= ATOL, f"{label}: {col} 最大偏離 {diff:.3e}"


# --------------------------------------------------------------------------- #
# 主要等價性
# --------------------------------------------------------------------------- #
def test_df_ic_equivalence(cuted_and_benchmark):
    """43 欄 IC（ic / rank_ic / ir + 20 組 lag）逐欄比對，含欄位順序。"""
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench)
    act = _run(factor_pl, cuted, bench)

    assert act.df_ic.shape == ref.df_ic.shape == (len(ref.df_ic), 43)
    _assert_frame_close(act.df_ic, ref.df_ic, "df_ic")


def test_df_pnl_equivalence(cuted_and_benchmark):
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench)
    act = _run(factor_pl, cuted, bench)
    _assert_frame_close(act.df_pnl, ref.df_pnl, "df_pnl")


def test_df_info_tables_identical(cuted_and_benchmark):
    """df_info / df_info2 是格式化字串表，必須逐格相同。"""
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench)
    act = _run(factor_pl, cuted, bench)
    assert act.df_info.equals(ref.df_info), "df_info 不同"
    assert act.df_info2.equals(ref.df_info2), "df_info2 不同"


@pytest.mark.parametrize("period", [1, 3, 5])
def test_period_selection_equivalence(cuted_and_benchmark, period):
    """period > 1 時的 day_count 取樣邏輯必須一致（factor.py:286-289）。

    day_count 只在「通過相異值數檢查」的日子遞增，且模數判斷發生於遞增之前，
    因此取到的是第 0、period、2*period… 個合格日 —— 不是單純的每 period 天。
    """
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench, period=period)
    act = _run(factor_pl, cuted, bench, period=period)

    assert list(act.df_ic.index) == list(ref.df_ic.index), (
        f"period={period} 取樣日期不同: ref {len(ref.df_ic)} 天 vs act {len(act.df_ic)} 天"
    )
    _assert_frame_close(act.df_ic, ref.df_ic, f"df_ic(period={period})")
    _assert_frame_close(act.df_pnl, ref.df_pnl, f"df_pnl(period={period})")


@pytest.mark.parametrize("predict_direction", [0, 1])
def test_predict_direction_equivalence(cuted_and_benchmark, predict_direction):
    """多空組合的方向推導兩版須一致。"""
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench, predict_direction=predict_direction)
    act = _run(factor_pl, cuted, bench, predict_direction=predict_direction)
    _assert_frame_close(act.df_pnl, ref.df_pnl, f"df_pnl(dir={predict_direction})")
    assert act.df_info2.equals(ref.df_info2)


def test_small_group_count(panel):
    """group_cnt < 4 時 df_info 的 index 組成不同（factor.py:37-46），須同樣相容。"""
    from _reference_pipeline import prepare_factor_frame

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            prep = prepare_factor_frame(panel, factor_name=FACTOR)
        with seeded():
            cuted, bench = grouping_factor(df=prep.copy(), factor_name=FACTOR, group_cnt=3)

    ref = _run(factor, cuted, bench, group_cnt=3)
    act = _run(factor_pl, cuted, bench, group_cnt=3)
    _assert_frame_close(act.df_pnl, ref.df_pnl, "df_pnl(group_cnt=3)")
    assert act.df_info.equals(ref.df_info)


# --------------------------------------------------------------------------- #
# 持倉與換手率（P2）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("period", [1, 3, 5])
def test_df_stock_equivalence(cuted_and_benchmark, period):
    """df_stock 的 index、欄位順序與每格持倉集合須與父類別一致。

    欄位順序特別重要：cal_turnover_rate 與 cal_df_info1 都以位置索引
    （``.iloc[:, n]``）存取，欄序錯了不會報錯，只會把各組數字對調。
    """
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench, period=period)
    act = _run(factor_pl, cuted, bench, period=period)

    assert list(act.df_stock.columns) == list(ref.df_stock.columns), "df_stock 欄位順序不同"
    assert list(act.df_stock.index) == list(ref.df_stock.index), "df_stock index 不同"

    for i in range(0, len(ref.df_stock), 29):
        for n in range(GROUP_CNT):
            a, b = act.df_stock.iloc[i, n], ref.df_stock.iloc[i, n]
            assert isinstance(a, list), f"df_stock 每格應為 list，實得 {type(a).__name__}"
            assert sorted(a) == sorted(b), f"第 {i} 列第 {n} 組持倉不同"


@pytest.mark.parametrize("period", [1, 3, 5])
def test_df_turnover_equivalence(cuted_and_benchmark, period):
    """換手率數值與缺值位置（前 period 列為 NaN）須與父類別一致。"""
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench, period=period)
    act = _run(factor_pl, cuted, bench, period=period)

    assert list(act.df_turnover.columns) == list(ref.df_turnover.columns)
    assert list(act.df_turnover.index) == list(ref.df_turnover.index)

    a = act.df_turnover.astype(float).to_numpy()
    b = ref.df_turnover.astype(float).to_numpy()
    assert np.array_equal(np.isnan(a), np.isnan(b)), "換手率缺值位置不同"
    ok = ~np.isnan(a)
    assert np.max(np.abs(a[ok] - b[ok])) <= ATOL, "換手率數值不同"

    # 前 period 列必為 NaN（factor.py:81 `if i < self.period: continue`）
    assert np.isnan(a[:period]).all(), f"前 {period} 列應為 NaN"
    assert not np.isnan(a[period:]).all(), "period 之後不應全為 NaN，測試將失去鑑別力"


def test_turnover_falls_back_when_stock_set_externally(cuted_and_benchmark):
    """df_stock 由外部指派時應退回父類別實作，而非靜默不計算。"""
    cuted, bench = cuted_and_benchmark
    ref = _run(factor, cuted, bench)

    alpha = factor_pl(name=FACTOR, group_number=GROUP_CNT)
    alpha.set_backtest_parameters(period=1, predict_direction=1)
    alpha.df_stock = ref.df_stock  # 繞過 cal_df_stock，沒有長格式快取
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alpha.cal_turnover_rate()

    assert not alpha.df_turnover.empty, "退回父類別失敗，換手率沒被計算"
    a = alpha.df_turnover.astype(float).to_numpy()
    b = ref.df_turnover.astype(float).to_numpy()
    ok = ~np.isnan(a)
    assert np.max(np.abs(a[ok] - b[ok])) <= ATOL


def test_turnover_rate_definition():
    """釘住換手率定義：|今日持倉 - 前期持倉| / |前期持倉|。"""
    dates = pd.date_range("2024-01-01", periods=3)
    rows = []
    # 第 1 天 group1 = {a,b}；第 2 天 group1 = {b,c} → 換手 |{c}|/|{a,b}| = 0.5
    holdings = {0: ["a", "b"], 1: ["b", "c"], 2: ["c", "d"]}
    for di, d in enumerate(dates):
        for sym in holdings[di]:
            rows.append({"date": d, "symbol": sym, f"{FACTOR}_group": 1})
        for sym in ["x", "y"]:  # 第二組固定不動 → 換手 0
            rows.append({"date": d, "symbol": sym, f"{FACTOR}_group": 2})
    df = pd.DataFrame(rows)

    alpha = factor_pl(name=FACTOR, group_number=2)
    alpha.set_backtest_parameters(period=1, predict_direction=1)
    alpha.cal_df_stock(df)
    alpha.cal_turnover_rate()

    t = alpha.df_turnover.astype(float)
    assert np.isnan(t.iloc[0, 0]), "第一列無前值，應為 NaN"
    assert abs(t.iloc[1, 0] - 0.5) < 1e-12, f"預期 0.5，實得 {t.iloc[1, 0]}"
    assert abs(t.iloc[2, 0] - 0.5) < 1e-12, f"預期 0.5，實得 {t.iloc[2, 0]}"
    assert abs(t.iloc[1, 1] - 0.0) < 1e-12, "持倉未變時換手應為 0"


# --------------------------------------------------------------------------- #
# 介面契約
# --------------------------------------------------------------------------- #
def test_accepts_polars_input(cuted_and_benchmark):
    """polars 輸入應與 pandas 輸入得到相同結果（呼叫端可省去一次轉換）。"""
    cuted, bench = cuted_and_benchmark
    from_pandas = _run(factor_pl, cuted, bench)

    cuted_pl = pl.from_pandas(cuted.reset_index(drop=True))
    bench_pl = pl.from_pandas(bench.reset_index().rename(columns={"index": "date"}))
    from_polars = _run(factor_pl, cuted_pl, bench_pl)

    _assert_frame_close(from_polars.df_ic, from_pandas.df_ic, "df_ic(polars 輸入)")
    assert from_polars.df_info2.equals(from_pandas.df_info2)


def test_outputs_are_date_indexed_pandas(cuted_and_benchmark):
    """df_ic / df_pnl 須為 DatetimeIndex 的 pandas DataFrame。

    cal_df_info1（factor.py:215）以 pd.Grouper(freq='M') 做月度彙總，
    draw_* 則直接把 index 當 x 軸 —— 兩者都相依於此。
    """
    cuted, bench = cuted_and_benchmark
    act = _run(factor_pl, cuted, bench)
    for name, frame in [("df_ic", act.df_ic), ("df_pnl", act.df_pnl)]:
        assert isinstance(frame, pd.DataFrame), f"{name} 不是 pandas DataFrame"
        assert isinstance(frame.index, pd.DatetimeIndex), (
            f"{name}.index 型別為 {type(frame.index)}，cal_df_info1 的月度彙總會失敗"
        )


def test_empty_input_matches_parent(cuted_and_benchmark):
    """空資料時應與父類別一樣安靜返回，不得拋例外。"""
    _, bench = cuted_and_benchmark
    empty = pd.DataFrame(columns=["date", "symbol", FACTOR])
    alpha = factor_pl(name=FACTOR, group_number=GROUP_CNT)
    alpha.set_backtest_parameters(period=1, predict_direction=1)
    alpha.start_backtest(empty, bench)
    assert alpha.df_ic.empty and alpha.df_pnl.empty


# --------------------------------------------------------------------------- #
# 迴歸防護：rank-then-pearson 不可換成 spearman
# --------------------------------------------------------------------------- #
def test_rank_ic_is_rank_then_pearson_not_spearman():
    """釘住 factor.py:295 的實際語意，防止日後被「順手改成 spearman」。

    ``.rank().corr()`` 是各欄先在自己的完整序列上排名（缺值給缺值），Pearson 才做
    pairwise 丟棄；``corr(method='spearman')`` 則是對齊後才排名。有缺值時兩者不同，
    而 returns_lag* 尾端必然有缺值，所以這個差異在真實資料上一定會被觸發。
    """
    from panda_factor.analysis.factor_func_pl import cal_backtest_frames_pl

    rng = np.random.default_rng(5)
    n = 80
    a = rng.normal(size=n)
    b = rng.normal(size=n)
    b[rng.choice(n, 15, replace=False)] = np.nan

    expected = pd.Series(a).rank().corr(pd.Series(b).rank())
    spearman = pd.Series(a).corr(pd.Series(b), method="spearman")
    assert abs(expected - spearman) > 1e-4, "本測試前提不成立：兩種算法在此資料上剛好相同"

    df = pl.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-01")] * n,
            FACTOR: a,
            f"{FACTOR}_group": [(i % GROUP_CNT) + 1 for i in range(n)],
            "1day_return": b,
            **{f"returns_lag{i}": b for i in range(1, 21)},
        }
    )
    bench = pl.DataFrame({"date": [pd.Timestamp("2024-01-01")], "1D_m": [0.01]})

    df_ic, _ = cal_backtest_frames_pl(
        df, FACTOR, group_cnt=GROUP_CNT, period=1, df_benchmark=bench
    )
    got = df_ic["rank_ic"][0]
    assert abs(got - expected) < 1e-12, f"rank_ic 應為 rank-then-pearson，實得 {got}"
    assert abs(got - spearman) > 1e-5, "rank_ic 誤用了 spearman"


# --------------------------------------------------------------------------- #
# 整合：Phase 1 + 2 + 3 全部替換
# --------------------------------------------------------------------------- #
def test_full_polars_chain(panel):
    """三個階段全部換成 polars 後，最終產物必須與全 pandas 鏈一致。"""
    from _reference_pipeline import run_full_polars_chain, run_pandas_chain

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            ref = run_pandas_chain(panel)
        with seeded():
            act = run_full_polars_chain(panel)

    _assert_frame_close(act["df_ic"], ref["df_ic"], "full-chain df_ic")
    _assert_frame_close(act["df_pnl"], ref["df_pnl"], "full-chain df_pnl")
    assert act["df_info"].equals(ref["df_info"]), "full-chain df_info 改變"
    assert act["df_info2"].equals(ref["df_info2"]), "full-chain df_info2 改變"
