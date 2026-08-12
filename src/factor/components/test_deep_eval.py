"""深度單因子回測的行為測試。

斷言只打在 `DeepFactorTester.run_all` 的輸出上，不碰私有 helper——它們的簽章在
後續重構中一定會變，綁死等於每次重構都要改測試。

風格沿用 src/alphas/test_*.py：手刻小 polars DataFrame、純 pytest function、
不使用 fixture。
"""

from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 無頭環境

import numpy as np
import polars as pl
import pytest

from src.factor.components.deep_eval import DeepFactorTester
from src.factor.components.deep_panel import DeepBacktestConfig, prepare_panel

SYMS = ["A", "B", "C", "D", "E", "F"]
NDAYS = 14


def _dates(n: int = NDAYS) -> list[date]:
    return [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]


def _raw(
    *,
    symbols: list[str] | None = None,
    n_days: int = NDAYS,
    closes: dict[str, list[float]] | None = None,
    can_buy: dict[str, list[int]] | None = None,
    can_sell: dict[str, list[int]] | None = None,
    untradable: dict[str, list[int]] | None = None,
    avoid_early: dict[str, list[int]] | None = None,
) -> pl.DataFrame:
    """手刻原始日線。預設每檔各自一條溫和上漲、彼此不同的價格序列。"""
    symbols = symbols if symbols is not None else SYMS
    days = _dates(n_days)
    rows = []
    for s_i, sym in enumerate(symbols):
        series = (closes or {}).get(
            sym, [100.0 + s_i * 10 + i * (1.0 + s_i * 0.3) for i in range(n_days)]
        )
        for i, d in enumerate(days):
            rows.append(
                {
                    "symbol": sym,
                    "date": d,
                    "close_adj": float(series[i]),
                    "untradable": (untradable or {}).get(sym, [0] * n_days)[i],
                    "can_buy": (can_buy or {}).get(sym, [1] * n_days)[i],
                    "can_sell": (can_sell or {}).get(sym, [1] * n_days)[i],
                    "avoid_early": (avoid_early or {}).get(sym, [0] * n_days)[i],
                }
            )
    return pl.DataFrame(rows)


def _cfg(**kwargs) -> DeepBacktestConfig:
    """測試用的小 config：門檻放寬、噪音預設關掉以便做精確斷言。"""
    defaults = dict(
        holding_period=1,
        return_periods=(1, 3),
        max_lag=2,
        group_count=2,
        min_names=2,
        min_coverage=0.5,
        noise_std=0.0,
        seed=1234,
    )
    defaults.update(kwargs)
    return DeepBacktestConfig(**defaults)


def _panel(cfg: DeepBacktestConfig, **raw_kwargs) -> pl.DataFrame:
    return prepare_panel(_raw(**raw_kwargs), cfg)


def _factor(panel: pl.DataFrame, values: dict[str, float] | None = None) -> pl.DataFrame:
    """因子框。預設每檔一個固定值（跨日不變），方便推理分組。"""
    if values is None:
        values = {sym: float(i) for i, sym in enumerate(SYMS)}
    return panel.select(
        "symbol",
        "date",
        pl.col("symbol").replace_strict(values, default=None).alias("value"),
    )


def _random_factor(panel: pl.DataFrame, seed: int = 7) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    return panel.select(
        "symbol", "date", pl.Series("value", rng.normal(size=panel.height))
    )


def _n_on(result, day: date) -> int:
    """某一天進入 IC 統計的檔數。"""
    row = result.ic_daily.filter(pl.col("date") == day)
    return int(row["n"][0]) if row.height else 0


# =========================================================================
# #4 建構子、面板不變、多因子重複測
# =========================================================================


def test_panel_is_not_modified_by_tester() -> None:
    """面板昂貴、建一次重複用，tester 全程不得改動它。"""
    cfg = _cfg()
    panel = _panel(cfg)
    before = panel.clone()
    tester = DeepFactorTester(panel, cfg)
    tester.run_all(_random_factor(panel), name="a")
    tester.run_all(_random_factor(panel, seed=99), name="b")
    assert panel.equals(before)


def test_two_factors_on_one_tester_do_not_interfere() -> None:
    """連續測兩個因子，結果互不影響——第二次的結果與單獨測時相同。"""
    cfg = _cfg()
    panel = _panel(cfg)
    f_a, f_b = _random_factor(panel, seed=1), _random_factor(panel, seed=2)

    shared = DeepFactorTester(panel, cfg)
    shared.run_all(f_a, name="a")
    b_after_a = shared.run_all(f_b, name="b")

    b_alone = DeepFactorTester(panel, cfg).run_all(f_b, name="b")
    assert b_after_a.ic_daily.equals(b_alone.ic_daily)
    assert b_after_a.group_returns.equals(b_alone.group_returns)


def test_constructor_rejects_panel_built_with_a_different_config() -> None:
    """建構子只做驗證，但驗證要擋住對不上的面板，而不是等統計時炸開。"""
    panel = _panel(_cfg(holding_period=1, return_periods=(1, 3), max_lag=2))
    with pytest.raises(ValueError, match="面板缺少欄位"):
        DeepFactorTester(panel, _cfg(holding_period=3, max_lag=20))


# =========================================================================
# #4 覆蓋率
# =========================================================================


def test_coverage_is_reported() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    result = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    assert result.coverage.factor_rows == panel.height
    assert result.coverage.coverage == pytest.approx(1.0)
    assert result.coverage.evaluated_rows > 0


def test_symbol_mismatch_raises_and_names_the_cause() -> None:
    """代號格式對不上時當場報錯，而不是靜默用剩下的樣本算 IC。"""
    cfg = _cfg()
    panel = _panel(cfg)
    bad = _factor(panel).with_columns(pl.col("symbol") + ".TW")
    with pytest.raises(ValueError, match="代號"):
        DeepFactorTester(panel, cfg).run_all(bad, name="f")


def test_date_mismatch_raises_and_names_the_cause() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    bad = _factor(panel).with_columns(pl.col("date") + pl.duration(days=400))
    with pytest.raises(ValueError, match="日期"):
        DeepFactorTester(panel, cfg).run_all(bad, name="f")


def test_coverage_just_above_threshold_is_accepted() -> None:
    """門檻之上不報錯——覆蓋率檢查是防呆，不是嚴格對齊要求。"""
    cfg = _cfg(min_coverage=0.5)
    panel = _panel(cfg)
    good = _factor(panel)
    # 混入約三成對不上的代號：覆蓋率掉到 0.7，仍在 0.5 門檻之上
    bogus = good.head(good.height * 3 // 7).with_columns(
        ("Z" + pl.col("symbol")).alias("symbol")
    )
    mixed = pl.concat([good, bogus])

    result = DeepFactorTester(panel, cfg).run_all(mixed, name="f")

    assert cfg.min_coverage < result.coverage.coverage < 1.0
    assert result.coverage.unmatched_symbols > 0
    # 對不上的部分不進入統計，能對上的照常算完
    assert result.coverage.matched_rows == good.height
    assert result.ic_daily.height > 0


# =========================================================================
# #4 可交易性（ADR-0002）
# =========================================================================


def test_untradable_symbol_never_enters_any_cross_section() -> None:
    """因子宇宙的排除是全稱的：untradable=1 的個股不出現在任何一天。"""
    cfg = _cfg()
    panel = _panel(cfg, untradable={"F": [1] * NDAYS})
    base = _panel(cfg, symbols=[s for s in SYMS if s != "F"])

    r_with = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    r_without = DeepFactorTester(base, cfg).run_all(_factor(base), name="f")

    assert r_with.coverage.evaluated_rows == r_without.coverage.evaluated_rows
    assert r_with.ic_daily["n"].to_list() == r_without.ic_daily["n"].to_list()


def test_limit_up_on_entry_day_removes_that_name_from_that_day() -> None:
    """進場日（T+1）鎖漲停買不到，該檔當天整筆從截面剔除。"""
    cfg = _cfg(holding_period=1)
    days = _dates()
    blocked = [1] * NDAYS
    blocked[4] = 0  # T+1 = day4 → 影響因子形成日 T = day3
    panel = _panel(cfg, can_buy={"F": blocked})

    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    assert _n_on(r, days[3]) == len(SYMS) - 1
    assert _n_on(r, days[2]) == len(SYMS)  # 其餘日子不受影響


def test_limit_down_on_exit_day_removes_that_name_from_that_day() -> None:
    """出場日（持有期 1 時為 T+2）鎖跌停賣不掉，同樣整筆剔除。"""
    cfg = _cfg(holding_period=1)
    days = _dates()
    blocked = [1] * NDAYS
    blocked[5] = 0  # T+2 = day5 → 影響 T = day3
    panel = _panel(cfg, can_sell={"F": blocked})

    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    assert _n_on(r, days[3]) == len(SYMS) - 1
    assert _n_on(r, days[2]) == len(SYMS)


def test_tradability_is_judged_on_the_execution_day_not_the_formation_day() -> None:
    """T 日買不到不影響 T——判定綁在真正成交的那一天（ADR-0002）。"""
    cfg = _cfg(holding_period=1)
    days = _dates()
    blocked = [1] * NDAYS
    blocked[3] = 0  # 只有 T 當天買不到
    panel = _panel(cfg, can_buy={"F": blocked})

    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    assert _n_on(r, days[3]) == len(SYMS)      # T 日的旗標不參與判定
    assert _n_on(r, days[2]) == len(SYMS) - 1  # 受影響的是 T-1（其進場日為 day3）


# =========================================================================
# #5 分組與多空價差
# =========================================================================


def test_result_carries_group_returns_and_long_short() -> None:
    cfg = _cfg(group_count=3)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")

    assert set(r.group_returns["group"].unique().to_list()) == {0, 1, 2}
    assert r.long_short.height == r.ic_daily.height
    assert "ret" in r.long_short.columns


def test_removal_precedes_grouping_so_boundaries_ignore_untradable_names() -> None:
    """先剔除再分組：買不到的個股不得參與決定分位數邊界（ADR-0002）。

    讓 F 在每一天的進場日都買不到，其分組結果必須與「F 根本不存在」完全相同。
    若實作成先分組再剔除，F 的因子值會把邊界往外推，這個斷言就會失敗。
    """
    cfg = _cfg(group_count=2, noise_std=0.0)
    panel = _panel(cfg, can_buy={"F": [0] * NDAYS})
    base = _panel(cfg, symbols=[s for s in SYMS if s != "F"])

    r_with = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")
    r_without = DeepFactorTester(base, cfg).run_all(_factor(base), name="f")

    assert r_with.group_returns.equals(r_without.group_returns)
    assert r_with.long_short.equals(r_without.long_short)


def test_days_with_too_few_distinct_values_are_dropped_whole() -> None:
    """三檔股票切不出五組——相異值不足的日子整天丟棄，不做降級。"""
    cfg = _cfg(group_count=4, min_names=2)
    panel = _panel(cfg)
    days = _dates()
    flat_day = days[5]
    factor = _factor(panel).with_columns(
        pl.when(pl.col("date") == flat_day).then(1.0).otherwise(pl.col("value")).alias("value")
    )

    r = DeepFactorTester(panel, cfg).run_all(factor, name="f")
    assert r.dropped_days >= 1
    assert flat_day not in r.group_returns["date"].to_list()
    # 只丟該天，其餘照常
    assert days[4] in r.group_returns["date"].to_list()


def test_factor_with_many_ties_still_groups_without_error() -> None:
    """台股因子常整批同值；1e-10 的噪音就是為了讓 qcut 切得出唯一邊界。"""
    cfg = _cfg(group_count=2, noise_std=1e-10)
    panel = _panel(cfg)
    half_zero = {sym: (0.0 if i < 3 else float(i)) for i, sym in enumerate(SYMS)}
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel, half_zero), name="f")
    assert r.group_returns.height > 0
    assert set(r.group_returns["group"].unique().to_list()) == {0, 1}


def test_same_seed_reproduces_identical_results() -> None:
    cfg = _cfg(noise_std=1e-10, seed=99)
    panel = _panel(cfg)
    factor = _random_factor(panel)
    tester = DeepFactorTester(panel, cfg)

    first, second = tester.run_all(factor, "f"), tester.run_all(factor, "f")
    assert first.ic_daily.equals(second.ic_daily)
    assert first.group_returns.equals(second.group_returns)
    assert first.metrics == second.metrics


def test_no_benchmark_metrics_anywhere_in_the_result() -> None:
    """benchmark 是宇宙內等權平均而非市場指數，留著只會被誤讀成大盤。"""
    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), name="f")

    names = (
        list(r.metrics)
        + r.ic_daily.columns
        + r.group_returns.columns
        + r.long_short.columns
        + r.decay.columns
        + list(vars(r))
    )
    assert not [n for n in names if "bench" in n.lower()]


# =========================================================================
# #4 去極值與顯著性
# =========================================================================


def test_winsorize_can_be_switched_off_and_changes_the_result() -> None:
    """去極值是參數不是寫死的行為；關掉之後極端值的貢獻會顯示出來。"""
    panel_cfg = _cfg()
    panel = _panel(panel_cfg)
    outlier = {sym: float(i) for i, sym in enumerate(SYMS)}
    outlier["F"] = 1e6
    factor = _factor(panel, outlier)

    # 只有 6 檔時單一離群值的 z 上限是 (n-1)/sqrt(n) ≈ 2.04，3 倍標準差永遠切不到，
    # 因此這裡把門檻壓到 1 倍，讓截斷真的發生。
    on = DeepFactorTester(panel, _cfg(winsorize=True, winsorize_std=1.0)).run_all(
        factor, "f"
    )
    off = DeepFactorTester(panel, _cfg(winsorize=False, winsorize_std=1.0)).run_all(
        factor, "f"
    )

    assert np.isfinite(on.metrics["IC_mean"])
    assert np.isfinite(off.metrics["IC_mean"])
    assert on.metrics["IC_mean"] != off.metrics["IC_mean"]
    # Rank IC 只看排序，不受截斷影響
    assert on.metrics["Rank_IC_mean"] == pytest.approx(off.metrics["Rank_IC_mean"])


def test_plain_and_newey_west_t_are_both_available() -> None:
    """兩者並列而非取代——看不到未修正的 t 就不知道自相關灌了多少水。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    for key in ("IC_t", "IC_nw_t", "Rank_IC_t", "Rank_IC_nw_t"):
        assert key in r.metrics
        assert np.isfinite(r.metrics[key])
    assert r.metrics["IC_t"] != r.metrics["IC_nw_t"]
    # 未指定時為 0：序列已經是非重疊的，沒有重疊造成的自相關要修（ADR-0003）。
    # 欄位仍照出，此時 nw 只差在標準誤的 ddof，兩者接近但不相等。
    assert r.config.nw_lags == 0
    assert r.config.__class__(holding_period=3, return_periods=(1, 3),
                              newey_west_lags=5).nw_lags == 5


def test_newey_west_widens_the_standard_error_on_a_positively_autocorrelated_series() -> None:
    """正自相關的 IC 序列上，NW 的 |t| 必須小於未修正的 |t|。

    刻意造出一條會變動、且變動有持續性的 IC 序列：每日報酬 = a_d * 因子 + 噪音，
    其中 a_d 是正的 AR(1)。因子固定、價格單調的話每日 IC 恆為 1，變異數是零，
    兩個 t 都會是 nan——那種面板檢驗不到這個性質。
    """
    n_days, syms = 80, [f"S{i:02d}" for i in range(12)]
    values = {sym: float(i) - 5.5 for i, sym in enumerate(syms)}

    rng = np.random.default_rng(20240810)
    a = np.empty(n_days)
    a[0] = 0.01
    for d in range(1, n_days):
        a[d] = 0.9 * a[d - 1] + 0.1 * 0.01 + rng.normal(0, 0.002)

    closes = {}
    for sym in syms:
        px, series = 100.0, []
        for d in range(n_days):
            series.append(px)
            px *= 1 + a[d] * values[sym] + rng.normal(0, 0.01)
        closes[sym] = series

    cfg = _cfg(min_names=6, newey_west_lags=5)
    panel = _panel(cfg, symbols=syms, n_days=n_days, closes=closes)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel, values), "f")

    ic = np.asarray(r.ic_daily["rank_ic"].to_list(), dtype=float)
    assert np.corrcoef(ic[:-1], ic[1:])[0, 1] > 0.1, "前提失效：IC 序列並非正自相關"
    assert abs(r.metrics["Rank_IC_nw_t"]) < abs(r.metrics["Rank_IC_t"])
    assert abs(r.metrics["IC_nw_t"]) < abs(r.metrics["IC_t"])


def test_ic_series_omits_thin_days_instead_of_filling_zero() -> None:
    """樣本不足的日子在序列中缺席，不是一個「IC 恰好為零」的假觀測。"""
    cfg = _cfg(min_names=4)
    panel = _panel(cfg)
    days = _dates()
    thin_day = days[6]
    # 該天只留兩檔有因子值
    factor = _factor(panel).with_columns(
        pl.when((pl.col("date") == thin_day) & ~pl.col("symbol").is_in(["A", "B"]))
        .then(None)
        .otherwise(pl.col("value"))
        .alias("value")
    )

    r = DeepFactorTester(panel, cfg).run_all(factor, "f")
    assert thin_day not in r.ic_daily["date"].to_list()
    assert 0.0 not in r.ic_daily["ic"].to_list()


# =========================================================================
# #6 提前出場
# =========================================================================


def test_early_exit_uses_the_avoid_early_price_not_the_nominal_date() -> None:
    """踩到 avoid_early 時，前向報酬用提前的出場日價格。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    closes = {"A": [10.0 + i for i in range(NDAYS)]}
    flags = [0] * NDAYS
    flags[3] = 1  # T=0 的持有期為 day1..day4，day3 就得出清
    panel = prepare_panel(
        _raw(symbols=["A"], closes=closes, avoid_early={"A": flags}), cfg
    )
    row = panel.sort("date")

    assert row["3day_return"][0] == pytest.approx(
        closes["A"][3] / closes["A"][1] - 1, rel=1e-12
    )
    assert bool(row["3day_early_exit"][0]) is True


def test_nominal_exit_is_kept_when_it_comes_first() -> None:
    """名目出場日早於 avoid_early 時行為不變。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    closes = {"A": [10.0 + i for i in range(NDAYS)]}
    flags = [0] * NDAYS
    flags[9] = 1  # 遠在 T=0 的名目出場日 day4 之後
    panel = prepare_panel(
        _raw(symbols=["A"], closes=closes, avoid_early={"A": flags}), cfg
    )
    row = panel.sort("date")

    assert row["3day_return"][0] == pytest.approx(
        closes["A"][4] / closes["A"][1] - 1, rel=1e-12
    )
    assert bool(row["3day_early_exit"][0]) is False


def test_early_exit_count_is_zero_when_nothing_is_forced_out() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")
    assert r.early_exit_count == 0


def test_early_exit_count_is_reported() -> None:
    """提前出場的次數必須隨結果回報——它代表回測偏離名目持有期的程度。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    flags = [0] * NDAYS
    flags[5] = 1
    panel = _panel(cfg, avoid_early={"F": flags})
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")
    assert r.early_exit_count > 0


def test_early_exit_still_requires_can_sell_on_the_actual_exit_day() -> None:
    """提前出場不是豁免——那一天賣不掉一樣要剔除。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    days = _dates()
    early = [0] * NDAYS
    early[3] = 1          # T=0 的實際出場日提前到 day3
    sell = [1] * NDAYS
    sell[3] = 0           # 而 day3 賣不掉
    panel = _panel(cfg, avoid_early={"F": early}, can_sell={"F": sell})

    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")
    assert _n_on(r, days[0]) == len(SYMS) - 1


# =========================================================================
# #7 IC 衰減
# =========================================================================


def test_decay_uses_one_fixed_sample_across_all_lags() -> None:
    """各 lag 的樣本數必須完全相等，否則衰減曲線混入樣本數變化的效果。"""
    cfg = _cfg(max_lag=4, return_periods=(1, 3))
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    assert r.decay.height == cfg.max_lag + 1
    assert r.decay["n_obs"].n_unique() == 1
    assert r.decay["n_days"].n_unique() == 1


def test_decay_applies_entry_condition_only() -> None:
    """衰減只套進場條件；出場日賣不掉不影響它，但會影響主 IC 的樣本。"""
    cfg = _cfg(holding_period=1, max_lag=2)
    panel_ok = _panel(cfg)
    panel_blocked = _panel(cfg, can_sell={"F": [0] * NDAYS})

    r_ok = DeepFactorTester(panel_ok, cfg).run_all(_factor(panel_ok), "f")
    r_blocked = DeepFactorTester(panel_blocked, cfg).run_all(_factor(panel_blocked), "f")

    assert r_blocked.decay["n_obs"][0] == r_ok.decay["n_obs"][0]
    assert r_blocked.coverage.evaluated_rows < r_ok.coverage.evaluated_rows


def test_decay_entry_condition_does_shrink_the_sample() -> None:
    """反向確認：進場買不到時，衰減的樣本確實縮水。"""
    cfg = _cfg(holding_period=1, max_lag=2)
    panel_ok = _panel(cfg)
    panel_blocked = _panel(cfg, can_buy={"F": [0] * NDAYS})

    r_ok = DeepFactorTester(panel_ok, cfg).run_all(_factor(panel_ok), "f")
    r_blocked = DeepFactorTester(panel_blocked, cfg).run_all(_factor(panel_blocked), "f")
    assert r_blocked.decay["n_obs"][0] < r_ok.decay["n_obs"][0]


def test_decay_lag0_matches_the_main_ic_definition() -> None:
    """lag 0 與主 IC 同為當日截面相關；條件對齊時兩者應相等。"""
    cfg = _cfg(holding_period=1, return_periods=(1,), max_lag=0, noise_std=0.0)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    assert r.decay["ic"][0] == pytest.approx(r.metrics["IC_mean"], rel=1e-9)
    assert r.decay["rank_ic"][0] == pytest.approx(r.metrics["Rank_IC_mean"], rel=1e-9)


def test_decay_shape_matches_a_factor_with_known_decay() -> None:
    """因子直接等於 lag0 的報酬：lag0 的 IC 應為 1，後續 lag 顯著更低。"""
    cfg = _cfg(holding_period=1, return_periods=(1,), max_lag=3, noise_std=0.0)
    rng = np.random.default_rng(3)
    closes = {
        sym: list(100.0 * np.cumprod(1 + rng.normal(0, 0.03, NDAYS)))
        for sym in SYMS
    }
    panel = _panel(cfg, closes=closes)
    factor = panel.select("symbol", "date", pl.col("returns_lag0").alias("value"))

    r = DeepFactorTester(panel, cfg).run_all(factor, "perfect")
    assert r.decay["ic"][0] == pytest.approx(1.0, abs=1e-9)
    assert r.decay["rank_ic"][0] == pytest.approx(1.0, abs=1e-9)
    for lag in range(1, 4):
        assert abs(r.decay["ic"][lag]) < 0.9


# =========================================================================
# #8 繪圖
# =========================================================================


def _result_for_plots():
    cfg = _cfg(group_count=3, max_lag=3)
    panel = _panel(cfg)
    return DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "plotme")


def test_each_plot_can_be_drawn_independently() -> None:
    import matplotlib.pyplot as plt

    r = _result_for_plots()
    for method in (r.plot_ic, r.plot_cumulative_ic, r.plot_group_returns, r.plot_ic_decay):
        ax = method()
        assert ax is not None
        plt.close("all")


def test_plot_all_draws_four_panels() -> None:
    import matplotlib.pyplot as plt

    r = _result_for_plots()
    fig, axes = r.plot_all()
    assert len(fig.axes) == 4
    plt.close("all")


def test_run_all_does_not_draw() -> None:
    """繪圖與計算分離：批次跑多個因子時不該被繪圖拖慢。"""
    import matplotlib.pyplot as plt

    plt.close("all")
    _result_for_plots()
    assert plt.get_fignums() == []


def test_group_return_plot_separates_the_two_ends() -> None:
    """分組累積報酬要看得出多空兩端的分離程度。"""
    cfg = _cfg(group_count=2, noise_std=0.0)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")

    cum = r.cumulative_group_returns()
    assert {"0", "1", "long_short"} <= set(cum.columns)
    assert cum["0"].to_list()[-1] != cum["1"].to_list()[-1]


# =========================================================================
# 與 panda_factor 的隔離
# =========================================================================


def test_deep_eval_does_not_depend_on_panda_factor() -> None:
    """深度回測自己用 polars 實作，不繼承 grouping_factor 的沉默行為。"""
    # 看 AST 而不是字串：註解與 docstring 本來就會提到 panda_factor（口徑沿用自它），
    # 純文字比對會把「不 import panda_factor」這句說明本身判成違規。
    for name in ("deep_eval.py", "deep_panel.py"):
        source = (Path(__file__).parent / name).read_text(encoding="utf-8")
        imported: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not [m for m in imported if m.split(".")[0] == "panda_factor"], (
            f"{name} 匯入了 panda_factor：{imported}"
        )


def test_summary_is_a_single_row_for_side_by_side_comparison() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    tester = DeepFactorTester(panel, cfg)
    rows = [
        tester.run_all(_random_factor(panel, seed=s), name=f"f{s}").summary()
        for s in (1, 2, 3)
    ]
    stacked = pl.concat(rows)
    assert stacked.height == 3
    assert stacked["factor"].to_list() == ["f1", "f2", "f3"]


# =========================================================================
# 分組績效與門檻比例（panda_factor 口徑）
# =========================================================================


def _stats_row(result, label: str) -> dict:
    row = result.group_stats.filter(pl.col("label") == label)
    assert row.height == 1, f"找不到 {label}"
    return row.to_dicts()[0]


def test_group_stats_has_one_row_per_group_plus_long_short() -> None:
    cfg = _cfg(group_count=3, min_names=3)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")

    assert r.group_stats["label"].to_list() == ["group1", "group2", "group3", "long_short"]
    # 多空那一列不屬於任何一組，group 必須是 null 而不是某個組號
    assert _stats_row(r, "long_short")["group"] is None


def test_annualised_return_and_volatility_follow_panda_factor_scaling() -> None:
    """年化 = 均值 × 252/持有期；年化波動用母體標準差（ddof=0）。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    part = r.group_returns.filter(pl.col("group") == 0).sort("date")
    rets = np.asarray(part["ret"].to_list(), dtype=float)
    scale = 252 / 3

    row = _stats_row(r, "group1")
    assert row["annual_return"] == pytest.approx(rets.mean() * scale)
    assert row["annual_volatility"] == pytest.approx(rets.std(ddof=0) * np.sqrt(scale))
    assert row["mean_return"] == pytest.approx(rets.mean())


def test_sharpe_subtracts_the_fixed_risk_free_rate() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    row = _stats_row(r, "group1")
    assert row["sharpe"] == pytest.approx(
        (row["annual_return"] - 0.025) / row["annual_volatility"]
    )


def test_max_drawdown_is_arithmetic_not_compounded() -> None:
    """panda_factor 用 cumsum 而非累乘；兩者在有回撤時算出來的數字不同。"""
    from src.factor.components.deep_eval import _max_drawdown

    rets = np.array([0.5, -0.4, 0.1])  # cumsum: 0.5, 0.1, 0.2 → 回撤 0.4
    assert _max_drawdown(rets) == pytest.approx(0.4)

    compounded = np.cumprod(1 + rets) - 1
    dd_compounded = float(np.max(np.maximum.accumulate(compounded) - compounded))
    assert not np.isclose(dd_compounded, 0.4), "測試前提失效：兩種算法應該不同"


def test_max_drawdown_is_zero_for_a_series_that_never_gives_back() -> None:
    from src.factor.components.deep_eval import _max_drawdown

    assert _max_drawdown(np.array([0.1, 0.2, 0.05])) == pytest.approx(0.0)


def test_turnover_is_zero_when_group_membership_never_changes() -> None:
    """因子跨日固定 → 每天分到同一組 → 換手率為 0。"""
    cfg = _cfg(group_count=2, min_names=2)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_factor(panel), "f")

    for label in ("group1", "group2", "long_short"):
        assert _stats_row(r, label)["turnover"] == pytest.approx(0.0)


def test_turnover_is_one_when_the_two_ends_swap_every_day() -> None:
    """每日反轉因子符號 → 兩組整批對調 → 換手率為 1。"""
    cfg = _cfg(group_count=2, min_names=2)
    panel = _panel(cfg)
    base = {sym: float(i) for i, sym in enumerate(SYMS)}
    days = _dates()
    flipping = panel.select(
        "symbol",
        "date",
        (
            pl.col("symbol").replace_strict(base, default=None)
            * pl.when(pl.col("date").is_in(days[::2])).then(1.0).otherwise(-1.0)
        ).alias("value"),
    )
    r = DeepFactorTester(panel, cfg).run_all(flipping, "f")

    for label in ("group1", "group2"):
        assert _stats_row(r, label)["turnover"] == pytest.approx(1.0)


def test_rank_ic_threshold_ratios_count_days() -> None:
    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    ric = np.asarray(r.ic_daily["rank_ic"].to_list(), dtype=float)
    n = len(ric)
    assert r.metrics["P_rank_ic_gt"] == pytest.approx((ric > 0.02).sum() / n)
    assert r.metrics["P_rank_ic_lt"] == pytest.approx((ric < -0.02).sum() / n)
    assert r.metrics["P_rank_ic_abs_gt"] == pytest.approx(
        r.metrics["P_rank_ic_gt"] + r.metrics["P_rank_ic_lt"]
    )
    assert 0.0 <= r.metrics["P_rank_ic_abs_gt"] <= 1.0


def test_threshold_ratios_use_the_0_02_boundary_strictly() -> None:
    """panda_factor 的 P(IC>0.02) 名字寫 IC、實際打在 rank_ic 上，且是嚴格大於。"""
    from src.factor.components.deep_eval import _threshold_stats

    assert _threshold_stats(pl.Series("rank_ic", [0.5, 0.5]))["P_rank_ic_gt"] == 1.0
    assert _threshold_stats(pl.Series("rank_ic", [0.01, -0.01]))["P_rank_ic_abs_gt"] == 0.0
    # 恰好等於門檻不算
    assert _threshold_stats(pl.Series("rank_ic", [0.02, -0.02]))["P_rank_ic_abs_gt"] == 0.0


def test_monotonicity_is_one_for_perfectly_ordered_group_returns() -> None:
    from src.factor.components.deep_eval import _monotonicity

    assert _monotonicity([0.01, 0.02, 0.03, 0.04]) == pytest.approx(1.0)
    assert _monotonicity([0.04, 0.03, 0.02, 0.01]) == pytest.approx(1.0)  # 取絕對值
    assert np.isnan(_monotonicity([0.02, 0.02, 0.02]))  # 沒有變異就沒有單調性可言


def test_monthly_win_rate_counts_calendar_months_not_days() -> None:
    from src.factor.components.deep_eval import _monthly_win_rate

    dates = pl.Series("date", [date(2024, 1, 5), date(2024, 1, 20), date(2024, 2, 5)])
    # 一月 +0.1 -0.3 = -0.2（輸）、二月 +0.05（贏）：逐日勝率 2/3，月度勝率 1/2
    rets = pl.Series("ret", [0.1, -0.3, 0.05])
    assert _monthly_win_rate(dates, rets) == pytest.approx(0.5)


def test_metric_keys_are_identical_even_when_the_long_short_series_is_empty() -> None:
    """metrics 的鍵集合不能隨因子而變，否則多因子 summary 疊起來會欄位對不齊。

    這個 bug 真的發生過：常數因子分不出組、沒有多空序列，於是少了 5 個鍵，
    49 個 pool 疊起來時 pl.concat 直接 ShapeError。
    """
    cfg = _cfg(min_names=2)
    panel = _panel(cfg)
    tester = DeepFactorTester(panel, cfg)

    normal = tester.run_all(_random_factor(panel), "normal")
    # 所有股票同值 → 相異值不足以分組 → 整段期間都沒有多空價差
    flat = tester.run_all(_factor(panel, {s: 1.0 for s in SYMS}), "flat")

    assert flat.long_short.height == 0, "測試前提失效：這個因子應該分不出組"
    assert set(normal.metrics) == set(flat.metrics)
    assert np.isnan(flat.metrics["long_short_mean"])
    assert np.isnan(flat.metrics["long_short_nw_t"])

    stacked = pl.concat([normal.summary(), flat.summary()])
    assert stacked.height == 2


def test_to_dict_is_json_serialisable_without_nan() -> None:
    import json
    import math

    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    text = json.dumps(r.to_dict(), allow_nan=False)  # 有 NaN 就會直接爆
    back = json.loads(text)
    assert back["name"] == "f"
    assert back["holding_period"] == cfg.holding_period
    assert {"metrics", "group_stats", "decay", "coverage"} <= set(back)
    assert any(row["label"] == "long_short" for row in back["group_stats"])
    assert all(
        v is None or not isinstance(v, float) or math.isfinite(v)
        for v in back["metrics"].values()
    )


def test_to_dict_can_include_the_daily_series() -> None:
    import json

    cfg = _cfg()
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    slim, full = r.to_dict(), r.to_dict(include_series=True)
    assert "ic_daily" not in slim
    assert len(full["ic_daily"]) == r.ic_daily.height
    assert isinstance(full["ic_daily"][0]["date"], str)  # 日期要能進 JSON
    json.dumps(full, allow_nan=False)


# =========================================================================
# 換倉日網格：每 holding_period 個交易日取一列（ADR-0003）
# =========================================================================


def test_holding_period_one_evaluates_every_trading_day() -> None:
    """hp=1 時每個交易日都是換倉日，網格是恆等的——沒有任何一天被抽掉。"""
    cfg = _cfg(holding_period=1)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    # 最後一天沒有前向報酬，本來就進不了統計；其餘每一天都在
    evaluable = sorted(
        panel.filter(pl.col("1day_return").is_not_null())["date"].unique().to_list()
    )
    assert r.ic_daily["date"].to_list() == evaluable


def test_group_returns_are_sampled_every_holding_period_days() -> None:
    """hp=3 → 只留第 0、3、6、9… 個交易日，每一列都是一次真實換倉。

    重疊的版本會每天算一列，這裡的斷言就是那個差別。
    """
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    calendar = sorted(panel["date"].unique().to_list())
    grid = set(calendar[::3])
    for dates in (r.ic_daily["date"].to_list(),
                  r.group_returns["date"].unique().to_list(),
                  r.long_short["date"].to_list()):
        assert dates, "抽樣後不該是空的"
        assert set(dates) <= grid

    # 相鄰兩列相隔 3 個交易日 → 持有區間不重疊
    pos = {d: i for i, d in enumerate(calendar)}
    got = sorted(r.long_short["date"].to_list())
    assert all(pos[b] - pos[a] == 3 for a, b in zip(got, got[1:]))


def test_rebalance_grid_does_not_depend_on_the_factor() -> None:
    """網格定義在面板的交易日曆上，因此兩個因子共用同一組換倉日、可以對比。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    panel = _panel(cfg)
    tester = DeepFactorTester(panel, cfg)
    a = tester.run_all(_random_factor(panel, seed=1), "a")
    b = tester.run_all(_random_factor(panel, seed=2), "b")
    assert a.ic_daily["date"].to_list() == b.ic_daily["date"].to_list()


def test_turnover_compares_consecutive_rebalances_not_consecutive_days() -> None:
    """hp=3、每個換倉日兩組整批對調 → 換手率為 1。

    比較的對象若是「前一個交易日」而不是「上一次換倉」，這裡會算出 0，因為
    因子在換倉日之間是不動的。
    """
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2,
               group_count=2, min_names=2)
    panel = _panel(cfg)
    calendar = sorted(panel["date"].unique().to_list())
    base = {sym: float(i) for i, sym in enumerate(SYMS)}
    # 第 0、6、12… 個交易日一個方向，第 3、9… 個交易日反向
    flip_days = calendar[3::6]
    flipping = panel.select(
        "symbol",
        "date",
        (
            pl.col("symbol").replace_strict(base, default=None)
            * pl.when(pl.col("date").is_in(flip_days)).then(-1.0).otherwise(1.0)
        ).alias("value"),
    )
    r = DeepFactorTester(panel, cfg).run_all(flipping, "f")
    for label in ("group1", "group2"):
        assert _stats_row(r, label)["turnover"] == pytest.approx(1.0)


def test_newey_west_lags_default_to_zero_because_the_series_is_not_overlapping() -> None:
    """非重疊之後沒有重疊造成的自相關，預設不修正；欄位仍照出、仍可手動指定。"""
    cfg = _cfg(holding_period=3, return_periods=(1, 3), max_lag=2)
    assert cfg.nw_lags == 0
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")
    for key in ("IC_nw_t", "Rank_IC_nw_t", "long_short_nw_t"):
        assert key in r.metrics


def test_holding_period_one_results_are_pinned() -> None:
    """hp=1 的數字釘死：每天都是換倉日，抽樣網格是恆等的，結果不該再變。

    這是非重疊改動（ADR-0003）的護欄——hp=1 按定義不受影響，數字一變就是改壞了。
    數值取自改動前的 HEAD，僅 nw_* 因 nw_lags 預設由 1 改為 0 而不同。
    """
    cfg = _cfg(holding_period=1)
    panel = _panel(cfg)
    r = DeepFactorTester(panel, cfg).run_all(_random_factor(panel), "f")

    ls = _stats_row(r, "long_short")
    assert ls["annual_return"] == pytest.approx(-0.013783835075897272)
    assert ls["annual_volatility"] == pytest.approx(0.03125436154540211)
    assert ls["max_drawdown"] == pytest.approx(0.003657667483580429)
    assert ls["sharpe"] == pytest.approx(-1.2409095293646415)
    assert ls["n_periods"] == 12.0
    assert ls["turnover"] == pytest.approx(0.5151515151515151)

    g1 = _stats_row(r, "group1")
    assert g1["annual_return"] == pytest.approx(3.174919780827509)
    assert g1["mean_return"] == pytest.approx(0.012598888019156781)
    assert g1["avg_names"] == pytest.approx(3.0)

    assert r.metrics["Rank_IC_mean"] == pytest.approx(0.14285714285714285)
    assert r.metrics["Rank_IC_t"] == pytest.approx(1.1407286397969485)
    assert r.metrics["IC_t"] == pytest.approx(1.5109026177049776)
    assert r.metrics["n_days"] == 12.0
