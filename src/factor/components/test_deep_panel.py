"""深度回測面板準備的行為測試。

斷言打在 `prepare_panel` 的輸出上，不碰私有 helper。
風格沿用 src/alphas/test_*.py：手刻小 polars DataFrame、純 pytest function。
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from src.factor.components.deep_panel import DeepBacktestConfig, prepare_panel


def _raw(
    closes: dict[str, list[float]],
    *,
    start: date = date(2024, 1, 1),
    dates: dict[str, list[date]] | None = None,
    can_buy: dict[str, list[int]] | None = None,
    can_sell: dict[str, list[int]] | None = None,
    untradable: dict[str, list[int]] | None = None,
) -> pl.DataFrame:
    """由每檔的 close_adj 序列造出最小可用的原始日線。"""
    rows = []
    for sym, series in closes.items():
        sym_dates = (
            dates[sym] if dates and sym in dates
            else [start + timedelta(days=i) for i in range(len(series))]
        )
        for i, close in enumerate(series):
            rows.append(
                {
                    "symbol": sym,
                    "date": sym_dates[i],
                    "close_adj": close,
                    "untradable": (untradable or {}).get(sym, [0] * len(series))[i],
                    "can_buy": (can_buy or {}).get(sym, [1] * len(series))[i],
                    "can_sell": (can_sell or {}).get(sym, [1] * len(series))[i],
                    "avoid_early": 0,
                }
            )
    return pl.DataFrame(rows)


def _cfg(**kwargs) -> DeepBacktestConfig:
    defaults = dict(holding_period=1, return_periods=(1, 3, 5), max_lag=3)
    defaults.update(kwargs)
    return DeepBacktestConfig(**defaults)


def _get(panel: pl.DataFrame, sym: str, idx: int, col: str):
    """取某檔第 idx 個交易日的欄位值。"""
    return panel.filter(pl.col("symbol") == sym).sort("date")[col][idx]


# --- 欄位與型別 ---------------------------------------------------------


def test_produces_forward_and_lag_return_columns() -> None:
    panel = prepare_panel(_raw({"A": [10.0 + i for i in range(12)]}), _cfg())
    for col in ("1day_return", "3day_return", "5day_return"):
        assert col in panel.columns
    for i in range(4):
        assert f"returns_lag{i}" in panel.columns


def test_numeric_columns_are_float64() -> None:
    """Float32 在市值／成交額量級的因子上會讓截面相關係數失去有效位數。"""
    raw = _raw({"A": [10.0 + i for i in range(12)]}).with_columns(
        pl.col("close_adj").cast(pl.Float32)
    )
    panel = prepare_panel(raw, _cfg())
    for col in ("close_adj", "1day_return", "5day_return", "returns_lag2"):
        assert panel.schema[col] == pl.Float64, f"{col} 不是 Float64"


def test_extra_columns_are_upcast_to_float64() -> None:
    """因子值常經由 extra_cols 進來；Float32 的市值／成交額量級因子會讓 IC 失效。"""
    raw = _raw({"A": [10.0 + i for i in range(12)]}).with_columns(
        pl.lit(1.5e9, pl.Float32).alias("amount"),
        pl.lit(3.2e6, pl.Float32).alias("mktcap"),
    )
    panel = prepare_panel(raw, _cfg(extra_cols=("amount", "mktcap")))
    assert panel.schema["amount"] == pl.Float64
    assert panel.schema["mktcap"] == pl.Float64


def test_integer_flags_are_not_upcast() -> None:
    """旗標不以數值身分進入統計，沒有理由付 Float64 的記憶體。"""
    raw = _raw({"A": [10.0 + i for i in range(12)]}).with_columns(
        pl.col("untradable").cast(pl.Int8),
        pl.col("can_buy").cast(pl.Int8),
        pl.col("can_sell").cast(pl.Int8),
    )
    panel = prepare_panel(raw, _cfg())
    for col in ("untradable", "can_buy", "can_sell"):
        assert panel.schema[col] == pl.Int8


def test_null_tradability_flags_are_filled_conservatively() -> None:
    """上游 left-join 補出的列沒有旗標來源；沒有證據就不算可交易。"""
    c = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    raw = _raw({"A": c}).with_columns(
        pl.when(pl.col("close_adj") == 12.0).then(None).otherwise(pl.col("untradable")).alias("untradable"),
        pl.when(pl.col("close_adj") == 12.0).then(None).otherwise(pl.col("can_buy")).alias("can_buy"),
        pl.when(pl.col("close_adj") == 12.0).then(None).otherwise(pl.col("can_sell")).alias("can_sell"),
    )
    panel = prepare_panel(raw, _cfg())

    for col in ("untradable", "can_buy", "can_sell"):
        assert panel[col].null_count() == 0, f"{col} 仍有 null 通過"
    assert _get(panel, "A", 2, "untradable") == 1  # 不在宇宙
    assert _get(panel, "A", 2, "can_buy") == 0     # 買不到
    assert _get(panel, "A", 2, "can_sell") == 0    # 賣不掉
    # 其餘列不受影響
    assert _get(panel, "A", 1, "can_buy") == 1


def test_missing_required_column_raises() -> None:
    raw = _raw({"A": [10.0, 11.0, 12.0]}).drop("can_sell")
    with pytest.raises(ValueError, match="can_sell"):
        prepare_panel(raw, _cfg())


def test_tradability_flags_are_carried_through() -> None:
    panel = prepare_panel(_raw({"A": [10.0 + i for i in range(12)]}), _cfg())
    for col in ("untradable", "can_buy", "can_sell"):
        assert col in panel.columns


# --- 報酬的算術 ---------------------------------------------------------


def test_forward_return_uses_t_plus_one_entry_and_t_plus_n_plus_one_exit() -> None:
    """1day_return = close_adj[T+2] / close_adj[T+1] - 1，一天都不能差。"""
    c = [10.0, 11.0, 13.0, 17.0, 23.0, 31.0, 41.0, 53.0, 67.0, 83.0]
    panel = prepare_panel(_raw({"A": c}), _cfg())

    for t in range(len(c) - 2):
        assert _get(panel, "A", t, "1day_return") == pytest.approx(
            c[t + 2] / c[t + 1] - 1, rel=1e-12
        )
    for t in range(len(c) - 4):
        assert _get(panel, "A", t, "3day_return") == pytest.approx(
            c[t + 4] / c[t + 1] - 1, rel=1e-12
        )
    for t in range(len(c) - 6):
        assert _get(panel, "A", t, "5day_return") == pytest.approx(
            c[t + 6] / c[t + 1] - 1, rel=1e-12
        )


def test_forward_return_is_null_when_exit_runs_off_the_end() -> None:
    c = [10.0, 11.0, 13.0, 17.0, 23.0]
    panel = prepare_panel(_raw({"A": c}), _cfg())
    # 1day_return 需要 T+2，最後兩天取不到
    assert _get(panel, "A", len(c) - 2, "1day_return") is None
    assert _get(panel, "A", len(c) - 1, "1day_return") is None


def test_lag_returns_are_not_misaligned() -> None:
    """returns_lag{i} 是第 i 個交易日之後的單日報酬，逐 lag 對過。"""
    c = [10.0, 11.0, 13.0, 17.0, 23.0, 31.0, 41.0, 53.0, 67.0, 83.0]
    panel = prepare_panel(_raw({"A": c}), _cfg(max_lag=3))

    for lag in range(4):
        for t in range(len(c) - 2 - lag):
            assert _get(panel, "A", t, f"returns_lag{lag}") == pytest.approx(
                c[t + lag + 2] / c[t + lag + 1] - 1, rel=1e-12
            ), f"lag={lag} t={t} 錯位"


def test_lag0_equals_one_day_return() -> None:
    c = [10.0, 11.0, 13.0, 17.0, 23.0, 31.0, 41.0]
    panel = prepare_panel(_raw({"A": c}), _cfg())
    lag0 = panel.sort("date")["returns_lag0"].to_list()
    one = panel.sort("date")["1day_return"].to_list()
    assert lag0 == one


# --- 停牌（ADR-0001） ---------------------------------------------------


def test_return_across_halt_is_not_na() -> None:
    """停牌日有列但不可交易；跨越它的報酬照實計算，不設 NA。"""
    c = [10.0, 11.0, 12.0, 12.0, 12.0, 12.0, 15.0, 16.0, 17.0, 18.0]
    #               ^^^^ index 2..5 停牌：買不到也賣不掉
    halt = [1, 1, 0, 0, 0, 0, 1, 1, 1, 1]
    panel = prepare_panel(
        _raw({"A": c}, can_buy={"A": halt}, can_sell={"A": halt}), _cfg()
    )

    # T=0 進場 T=1、5 日後出場 T=6，整段跨越停牌
    assert _get(panel, "A", 0, "5day_return") is not None
    assert _get(panel, "A", 0, "5day_return") == pytest.approx(
        c[6] / c[1] - 1, rel=1e-12
    )


def test_return_across_calendar_gap_is_not_na() -> None:
    """真正的日曆缺口（面板無列）同樣照實計算，不因跨越多個日曆日而設 NA。"""
    c = [10.0, 11.0, 12.0, 15.0, 16.0, 17.0, 18.0]
    d = [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 30),  # 中間 26 個日曆日沒有列
        date(2024, 1, 31),
        date(2024, 2, 1),
        date(2024, 2, 2),
    ]
    panel = prepare_panel(_raw({"A": c}, dates={"A": d}), _cfg())

    assert _get(panel, "A", 1, "1day_return") == pytest.approx(
        c[3] / c[2] - 1, rel=1e-12
    )


# --- 跨 symbol 邊界 -----------------------------------------------------


def test_no_leakage_across_symbols() -> None:
    """A 股的報酬不會取到 B 股的價格。"""
    a = [10.0, 11.0, 12.0, 13.0]
    b = [500.0, 600.0, 700.0, 800.0]
    panel = prepare_panel(_raw({"A": a, "B": b}), _cfg())

    # A 的最後兩天取不到 T+2，必須是 null 而不是 B 的價格
    assert _get(panel, "A", 2, "1day_return") is None
    assert _get(panel, "A", 3, "1day_return") is None
    assert _get(panel, "A", 0, "1day_return") == pytest.approx(a[2] / a[1] - 1)

    for lag in range(4):
        tail = _get(panel, "A", 3, f"returns_lag{lag}")
        assert tail is None, f"returns_lag{lag} 在 A 的尾端洩漏到 B"


def test_unsorted_input_is_handled() -> None:
    """輸入未排序時結果與排序後相同。"""
    a = [10.0, 11.0, 13.0, 17.0, 23.0, 31.0]
    b = [50.0, 55.0, 60.0, 66.0, 70.0, 77.0]
    raw = _raw({"A": a, "B": b})
    shuffled = raw.sample(fraction=1.0, shuffle=True, seed=7)

    expected = prepare_panel(raw, _cfg())
    actual = prepare_panel(shuffled, _cfg())
    assert actual.sort(["symbol", "date"]).equals(expected.sort(["symbol", "date"]))


# --- 決定性 -------------------------------------------------------------


def test_is_deterministic() -> None:
    raw = _raw({"A": [10.0 + i for i in range(15)], "B": [50.0 - i for i in range(15)]})
    assert prepare_panel(raw, _cfg()).equals(prepare_panel(raw, _cfg()))


def test_input_is_not_mutated() -> None:
    raw = _raw({"A": [10.0 + i for i in range(12)]})
    before = raw.clone()
    prepare_panel(raw, _cfg())
    assert raw.equals(before)


# --- config -------------------------------------------------------------


def test_holding_period_must_be_present_in_return_periods() -> None:
    with pytest.raises(ValueError, match="holding_period"):
        DeepBacktestConfig(holding_period=7, return_periods=(1, 3, 5))


def test_extra_columns_can_be_kept() -> None:
    raw = _raw({"A": [10.0 + i for i in range(12)]}).with_columns(
        pl.lit(1.5).alias("turnover")
    )
    panel = prepare_panel(raw, _cfg(extra_cols=("turnover",)))
    assert "turnover" in panel.columns


def test_unrequested_columns_are_dropped() -> None:
    """面板只留深度回測要用的欄位，不把上游一百多欄整包帶進來。"""
    raw = _raw({"A": [10.0 + i for i in range(12)]}).with_columns(
        pl.lit(1.5).alias("turnover")
    )
    panel = prepare_panel(raw, _cfg())
    assert "turnover" not in panel.columns
