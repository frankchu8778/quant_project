"""
中金《量化多因子系列（7）：价量因子手册》公式表實作（Polars）。

納入：波動率、流動性、動量/反轉（不含業績公告）、量價相關。
略過（缺可靠欄位／已確認排除）：
  - 業績公告類 mmt_report_*
  - Wind 分單／開尾盤資金流
  - 北向資金、融資融券
  - 籌碼分布（daily_data 無籌碼成本分佈）
  - 複合因子（依賴上列略過子因子）

欄位命名對齊 duckdb/daily_data.duckdb：
  symbol, date, open, high, low, close, amount, turnover, return_day, limit_status
週期：1M=22、3M=66、6M=126；年窗口 DAYS_1Y=22*12=264。
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import polars as pl

DAYS_1M = 22
DAYS_3M = 66
DAYS_6M = 126
DAYS_1Y = DAYS_1M * 12  # 264

_KEY_COLS = ("symbol", "date")


# ── helpers ──────────────────────────────────────────────────────────


def _require_cols(df: pl.DataFrame, cols: Iterable[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"df 缺少必要欄位: {missing}")


def _require_days(days: int) -> int:
    if not isinstance(days, (int, np.integer)) or int(days) < 1:
        raise ValueError(f"days 須為正整數，收到: {days!r}")
    return int(days)


def _period_suffix(days: int) -> str:
    return {DAYS_1M: "1M", DAYS_3M: "3M", DAYS_6M: "6M"}.get(days, f"{days}d")


def _out_name(base: str, days: int) -> str:
    return f"{base}_{_period_suffix(days)}"


def _sorted(df: pl.DataFrame) -> pl.DataFrame:
    return df.sort(["symbol", "date"])


def _safe_div(num: pl.Expr, den: pl.Expr) -> pl.Expr:
    return (
        pl.when(den.is_null() | num.is_null() | (den == 0))
        .then(None)
        .otherwise(num / den)
    )


def _rolling_std(expr: pl.Expr, days: int) -> pl.Expr:
    return expr.rolling_std(window_size=days, min_samples=days, ddof=1).over("symbol")


def _rolling_mean(expr: pl.Expr, days: int) -> pl.Expr:
    return expr.rolling_mean(window_size=days, min_samples=days).over("symbol")


def _rolling_sum(expr: pl.Expr, days: int) -> pl.Expr:
    return expr.rolling_sum(window_size=days, min_samples=days).over("symbol")


def _window_full(col: str, days: int) -> pl.Expr:
    """視窗內列數（含 null）達 days 才為 True；用 is_not_null 計數。"""
    return (
        pl.col(col).is_not_null().cast(pl.UInt32).rolling_sum(window_size=days).over("symbol")
        == days
    )


def _ret_over(days: int, price: str = "close") -> pl.Expr:
    prev = pl.col(price).shift(days).over("symbol")
    return _safe_div(pl.col(price), prev) - 1.0


# ── 波動率 ───────────────────────────────────────────────────────────


def generate_vol_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """過去 N 日日收益率標準差 → vol_std_{1M|3M|6M|Nd}。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    name = _out_name("vol_std", days)
    df = _sorted(df)
    return df.with_columns(_rolling_std(pl.col("return_day"), days).alias(name))


def generate_vol_down_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """下行波動率：視窗內漲跌幅 < 0 之日收益率標準差。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    name = _out_name("vol_down_std", days)
    df = _sorted(df)
    neg = pl.when(pl.col("return_day") < 0).then(pl.col("return_day"))
    full = _window_full("return_day", days)
    # min_samples=2：視窗內至少兩個負報酬才有樣本標準差
    std = neg.rolling_std(window_size=days, min_samples=2, ddof=1).over("symbol")
    return df.with_columns(pl.when(full).then(std).alias(name))


def generate_vol_up_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """上行波動率：視窗內漲跌幅 > 0 之日收益率標準差。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    name = _out_name("vol_up_std", days)
    df = _sorted(df)
    pos = pl.when(pl.col("return_day") > 0).then(pl.col("return_day"))
    full = _window_full("return_day", days)
    std = pos.rolling_std(window_size=days, min_samples=2, ddof=1).over("symbol")
    return df.with_columns(pl.when(full).then(std).alias(name))


def generate_vol_highlow_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """日內振幅均值；日振幅 = 最高價 / 最低價。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "high", "low"])
    name = _out_name("vol_highlow_avg", days)
    df = _sorted(df)
    amp = _safe_div(pl.col("high"), pl.col("low"))
    return df.with_columns(_rolling_mean(amp, days).alias(name))


def generate_vol_highlow_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """日內振幅標準差；日振幅 = 最高價 / 最低價。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "high", "low"])
    name = _out_name("vol_highlow_std", days)
    df = _sorted(df)
    amp = _safe_div(pl.col("high"), pl.col("low"))
    return df.with_columns(_rolling_std(amp, days).alias(name))


def generate_vol_upshadow_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """標準化上影線均值；(H - max(O,C)) / H。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "high", "close"])
    name = _out_name("vol_upshadow_avg", days)
    df = _sorted(df)
    shadow = _safe_div(
        pl.col("high") - pl.max_horizontal("open", "close"),
        pl.col("high"),
    )
    return df.with_columns(_rolling_mean(shadow, days).alias(name))


def generate_vol_upshadow_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """標準化上影線標準差；(H - max(O,C)) / H。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "high", "close"])
    name = _out_name("vol_upshadow_std", days)
    df = _sorted(df)
    shadow = _safe_div(
        pl.col("high") - pl.max_horizontal("open", "close"),
        pl.col("high"),
    )
    return df.with_columns(_rolling_std(shadow, days).alias(name))


def generate_vol_downshadow_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """標準化下影線均值；(min(O,C) - L) / L。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "low", "close"])
    name = _out_name("vol_downshadow_avg", days)
    df = _sorted(df)
    shadow = _safe_div(
        pl.min_horizontal("open", "close") - pl.col("low"),
        pl.col("low"),
    )
    return df.with_columns(_rolling_mean(shadow, days).alias(name))


def generate_vol_downshadow_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """標準化下影線標準差；(min(O,C) - L) / L。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "low", "close"])
    name = _out_name("vol_downshadow_std", days)
    df = _sorted(df)
    shadow = _safe_div(
        pl.min_horizontal("open", "close") - pl.col("low"),
        pl.col("low"),
    )
    return df.with_columns(_rolling_std(shadow, days).alias(name))


# ── 流動性 ───────────────────────────────────────────────────────────


def generate_liq_turn_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率均值。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "turnover"])
    name = _out_name("liq_turn_avg", days)
    df = _sorted(df)
    return df.with_columns(_rolling_mean(pl.col("turnover"), days).alias(name))


def generate_liq_turn_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率標準差。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "turnover"])
    name = _out_name("liq_turn_std", days)
    df = _sorted(df)
    return df.with_columns(_rolling_std(pl.col("turnover"), days).alias(name))


def generate_liq_vstd(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """成交波動比：N 日成交額合計 / N 日收益率標準差。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "amount", "return_day"])
    name = _out_name("liq_vstd", days)
    df = _sorted(df)
    amt = _rolling_sum(pl.col("amount"), days)
    vol = _rolling_std(pl.col("return_day"), days)
    return df.with_columns(_safe_div(amt, vol).alias(name))


def generate_liq_amihud_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """Amihud 非流動性均值：mean(|ret| / amount)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "amount", "return_day"])
    name = _out_name("liq_amihud_avg", days)
    df = _sorted(df)
    daily = _safe_div(pl.col("return_day").abs(), pl.col("amount"))
    return df.with_columns(_rolling_mean(daily, days).alias(name))


def generate_liq_amihud_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """Amihud 非流動性標準差：std(|ret| / amount)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "amount", "return_day"])
    name = _out_name("liq_amihud_std", days)
    df = _sorted(df)
    daily = _safe_div(pl.col("return_day").abs(), pl.col("amount"))
    return df.with_columns(_rolling_std(daily, days).alias(name))


def _kline_shortcut() -> pl.Expr:
    return 2.0 * (pl.col("high") - pl.col("low")) - (pl.col("open") - pl.col("close")).abs()


def generate_liq_shortcut_avg(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """最短路徑非流動性均值：mean(日K最短路徑 / amount)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "high", "low", "close", "amount"])
    name = _out_name("liq_shortcut_avg", days)
    df = _sorted(df)
    daily = _safe_div(_kline_shortcut(), pl.col("amount"))
    return df.with_columns(_rolling_mean(daily, days).alias(name))


def generate_liq_shortcut_std(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """最短路徑非流動性標準差：std(日K最短路徑 / amount)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "high", "low", "close", "amount"])
    name = _out_name("liq_shortcut_std", days)
    df = _sorted(df)
    daily = _safe_div(_kline_shortcut(), pl.col("amount"))
    return df.with_columns(_rolling_std(daily, days).alias(name))


# ── 動量 / 反轉（略過 mmt_report_*）─────────────────────────────────


def generate_mmt_normal_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """過去 N 日收益率（預設 1 個月）。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close"])
    df = _sorted(df)
    return df.with_columns(_ret_over(days).alias("mmt_normal_M"))


def generate_mmt_normal_A(
    df: pl.DataFrame,
    month_days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """過去 12 個月收益率 − 過去 1 個月收益率。"""
    month_days = _require_days(month_days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "close"])
    df = _sorted(df)
    return df.with_columns(
        (_ret_over(year_days) - _ret_over(month_days)).alias("mmt_normal_A")
    )


def generate_mmt_avg_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """相對均價的 N 日收益率：close / mean(close, N)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close"])
    df = _sorted(df)
    return df.with_columns(
        _safe_div(pl.col("close"), _rolling_mean(pl.col("close"), days)).alias("mmt_avg_M")
    )


def generate_mmt_avg_A(
    df: pl.DataFrame,
    month_days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """1 個月前收盤價 / 過去 1 年均價。"""
    month_days = _require_days(month_days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "close"])
    df = _sorted(df)
    num = pl.col("close").shift(month_days).over("symbol")
    den = _rolling_mean(pl.col("close"), year_days)
    return df.with_columns(_safe_div(num, den).alias("mmt_avg_A"))


def _intraday_ret() -> pl.Expr:
    return _safe_div(pl.col("close"), pl.col("open")) - 1.0


def _overnight_ret() -> pl.Expr:
    return _safe_div(pl.col("open"), pl.col("close").shift(1).over("symbol")) - 1.0


def generate_mmt_intraday_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """N 日內漲跌幅之和。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "close"])
    df = _sorted(df)
    return df.with_columns(_rolling_sum(_intraday_ret(), days).alias("mmt_intraday_M"))


def generate_mmt_intraday_A(
    df: pl.DataFrame,
    month_days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """1 年日內漲跌幅之和 − 1 個月日內漲跌幅之和。"""
    month_days = _require_days(month_days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "open", "close"])
    df = _sorted(df)
    r = _intraday_ret()
    return df.with_columns(
        (_rolling_sum(r, year_days) - _rolling_sum(r, month_days)).alias("mmt_intraday_A")
    )


def generate_mmt_overnight_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """N 日隔夜漲跌幅之和。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "open", "close"])
    df = _sorted(df)
    return df.with_columns(_rolling_sum(_overnight_ret(), days).alias("mmt_overnight_M"))


def generate_mmt_overnight_A(
    df: pl.DataFrame,
    month_days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """1 年隔夜漲跌幅之和 − 1 個月隔夜漲跌幅之和。"""
    month_days = _require_days(month_days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "open", "close"])
    df = _sorted(df)
    r = _overnight_ret()
    return df.with_columns(
        (_rolling_sum(r, year_days) - _rolling_sum(r, month_days)).alias("mmt_overnight_A")
    )


def _off_limit_ret() -> pl.Expr:
    # limit_status: 1 漲停 / -1 跌停 / 0 正常；非 0 日報酬視為 0（不計入漲跌）
    return (
        pl.when(pl.col("limit_status") == 0)
        .then(pl.col("return_day"))
        .otherwise(0.0)
    )


def _compound_off_limit(days: int) -> pl.Expr:
    # product(1+r)-1 ≡ exp(sum(log(1+r)))-1；limit 日 r=0
    log1p = (1.0 + _off_limit_ret()).log()
    return _rolling_sum(log1p, days).exp() - 1.0


def generate_mmt_off_limit_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """除去漲跌停後，過去 N 日收盤漲跌幅。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "limit_status"])
    df = _sorted(df)
    return df.with_columns(_compound_off_limit(days).alias("mmt_off_limit_M"))


def generate_mmt_off_limit_A(
    df: pl.DataFrame,
    month_days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """除去漲跌停後：1 年收盤漲跌幅 − 1 個月收盤漲跌幅。"""
    month_days = _require_days(month_days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "return_day", "limit_status"])
    df = _sorted(df)
    return df.with_columns(
        (_compound_off_limit(year_days) - _compound_off_limit(month_days)).alias(
            "mmt_off_limit_A"
        )
    )


def _rolling_range_mmt(amp: np.ndarray, ret: np.ndarray, days: int) -> np.ndarray:
    out = np.full(len(amp), np.nan, dtype=np.float64)
    k = max(1, int(days * 0.2))
    for i in range(days - 1, len(amp)):
        a = amp[i - days + 1 : i + 1]
        r = ret[i - days + 1 : i + 1]
        if not (np.isfinite(a).all() and np.isfinite(r).all()):
            continue
        order = np.argsort(a, kind="mergesort")
        out[i] = r[order[-k:]].mean() - r[order[:k]].mean()
    return out


def generate_mmt_range_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """振幅調整動量：振幅前 20% 日均報酬 − 振幅後 20% 日均報酬。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "high", "low", "return_day"])
    df = _sorted(df)
    name = "mmt_range_M"

    def _one(g: pl.DataFrame) -> pl.DataFrame:
        amp = (g["high"] / g["low"]).to_numpy()
        ret = g["return_day"].to_numpy()
        vals = _rolling_range_mmt(amp, ret, days)
        return g.with_columns(pl.Series(name, vals))

    return df.group_by("symbol", maintain_order=True).map_groups(_one)


def generate_mmt_range_A(df: pl.DataFrame, days: int = DAYS_1Y) -> pl.DataFrame:
    """1 年振幅調整動量。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "high", "low", "return_day"])
    df = _sorted(df)
    name = "mmt_range_A"

    def _one(g: pl.DataFrame) -> pl.DataFrame:
        amp = (g["high"] / g["low"]).to_numpy()
        ret = g["return_day"].to_numpy()
        vals = _rolling_range_mmt(amp, ret, days)
        return g.with_columns(pl.Series(name, vals))

    return df.group_by("symbol", maintain_order=True).map_groups(_one)


def generate_mmt_route_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """路徑調整動量：區間收益率 / 日漲跌幅絕對值之和。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close", "return_day"])
    df = _sorted(df)
    num = _ret_over(days)
    den = _rolling_sum(pl.col("return_day").abs(), days)
    return df.with_columns(_safe_div(num, den).alias("mmt_route_M"))


def generate_mmt_route_A(df: pl.DataFrame, days: int = DAYS_1Y) -> pl.DataFrame:
    """1 年路徑調整動量。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close", "return_day"])
    df = _sorted(df)
    num = _ret_over(days)
    den = _rolling_sum(pl.col("return_day").abs(), days)
    return df.with_columns(_safe_div(num, den).alias("mmt_route_A"))


def generate_mmt_discrete_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """資訊離散度：上漲天數占比 − 下跌天數占比。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    df = _sorted(df)
    up = (pl.col("return_day") > 0).cast(pl.Float64)
    down = (pl.col("return_day") < 0).cast(pl.Float64)
    return df.with_columns(
        (_rolling_mean(up, days) - _rolling_mean(down, days)).alias("mmt_discrete_M")
    )


def generate_mmt_discrete_A(df: pl.DataFrame, days: int = DAYS_1Y) -> pl.DataFrame:
    """1 年資訊離散度動量。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    df = _sorted(df)
    up = (pl.col("return_day") > 0).cast(pl.Float64)
    down = (pl.col("return_day") < 0).cast(pl.Float64)
    return df.with_columns(
        (_rolling_mean(up, days) - _rolling_mean(down, days)).alias("mmt_discrete_A")
    )


def generate_mmt_sec_rank_M(df: pl.DataFrame, days: int = DAYS_1M) -> pl.DataFrame:
    """橫截面 rank 動量：每日收益橫截面排名，再取過去 N 日均值。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    df = _sorted(df)
    return (
        df.with_columns(pl.col("return_day").rank().over("date").alias("_sec_rk"))
        .with_columns(_rolling_mean(pl.col("_sec_rk"), days).alias("mmt_sec_rank_M"))
        .drop("_sec_rk")
    )


def generate_mmt_sec_rank_A(df: pl.DataFrame, days: int = DAYS_1Y) -> pl.DataFrame:
    """1 年橫截面 rank 動量。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day"])
    df = _sorted(df)
    return (
        df.with_columns(pl.col("return_day").rank().over("date").alias("_sec_rk"))
        .with_columns(_rolling_mean(pl.col("_sec_rk"), days).alias("mmt_sec_rank_A"))
        .drop("_sec_rk")
    )


def _rolling_ts_rank_last(arr: np.ndarray, window: int) -> np.ndarray:
    """每個時點：當前價在過去 window 日內的百分位排名（含當日）。"""
    out = np.full(len(arr), np.nan, dtype=np.float64)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1 : i + 1]
        if not np.isfinite(w).all():
            continue
        last = w[-1]
        out[i] = float(np.sum(w <= last)) / float(window)
    return out


def generate_mmt_time_rank_M(
    df: pl.DataFrame,
    days: int = DAYS_1M,
    year_days: int = DAYS_1Y,
) -> pl.DataFrame:
    """時序 rank 動量：每日價格在 1 年時序排名，再取過去 N 日均值。"""
    days = _require_days(days)
    year_days = _require_days(year_days)
    _require_cols(df, [*_KEY_COLS, "close"])
    df = _sorted(df)

    def _one(g: pl.DataFrame) -> pl.DataFrame:
        close = g["close"].to_numpy().astype(np.float64)
        ts_rank = _rolling_ts_rank_last(close, year_days)
        # 再對 ts_rank 做 days 日均值
        out = np.full(len(ts_rank), np.nan, dtype=np.float64)
        for i in range(year_days + days - 2, len(ts_rank)):
            w = ts_rank[i - days + 1 : i + 1]
            if np.isfinite(w).all():
                out[i] = w.mean()
        return g.with_columns(pl.Series("mmt_time_rank_M", out))

    return df.group_by("symbol", maintain_order=True).map_groups(_one)


def generate_mmt_highest_days_A(df: pl.DataFrame, days: int = DAYS_1Y) -> pl.DataFrame:
    """近 1 年最高價出現日距今天數。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "high"])
    df = _sorted(df)

    def _one(g: pl.DataFrame) -> pl.DataFrame:
        high = g["high"].to_numpy().astype(np.float64)
        out = np.full(len(high), np.nan, dtype=np.float64)
        for i in range(days - 1, len(high)):
            w = high[i - days + 1 : i + 1]
            if not np.isfinite(w).all():
                continue
            out[i] = float(days - 1 - int(np.argmax(w)))
        return g.with_columns(pl.Series("mmt_highest_days_A", out))

    return df.group_by("symbol", maintain_order=True).map_groups(_one)


# ── 量價相關 ─────────────────────────────────────────────────────────


def _rolling_corr(a: pl.Expr, b: pl.Expr, days: int) -> pl.Expr:
    return pl.rolling_corr(a, b, window_size=days, min_samples=days).over("symbol")


def generate_corr_price_turn(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與價格同步相關。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close", "turnover"])
    name = _out_name("corr_price_turn", days)
    df = _sorted(df)
    return df.with_columns(
        _rolling_corr(pl.col("turnover"), pl.col("close"), days).alias(name)
    )


def generate_corr_price_turn_post(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與價格相關（量領先一期）：corr(turn_{t-1}, price_t)。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close", "turnover"])
    name = _out_name("corr_price_turn_post", days)
    df = _sorted(df)
    turn_lag = pl.col("turnover").shift(1).over("symbol")
    return df.with_columns(_rolling_corr(turn_lag, pl.col("close"), days).alias(name))


def generate_corr_price_turn_prior(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與價格相關（價領先一期）：corr(turn_t, price_{t-1})。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "close", "turnover"])
    name = _out_name("corr_price_turn_prior", days)
    df = _sorted(df)
    px_lag = pl.col("close").shift(1).over("symbol")
    return df.with_columns(
        _rolling_corr(pl.col("turnover"), px_lag, days).alias(name)
    )


def generate_corr_ret_turn(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與收益率同步相關。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turn", days)
    df = _sorted(df)
    return df.with_columns(
        _rolling_corr(pl.col("turnover"), pl.col("return_day"), days).alias(name)
    )


def generate_corr_ret_turn_post(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與收益率相關（量領先一期）。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turn_post", days)
    df = _sorted(df)
    turn_lag = pl.col("turnover").shift(1).over("symbol")
    return df.with_columns(
        _rolling_corr(turn_lag, pl.col("return_day"), days).alias(name)
    )


def generate_corr_ret_turn_prior(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率與收益率相關（價領先一期）。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turn_prior", days)
    df = _sorted(df)
    ret_lag = pl.col("return_day").shift(1).over("symbol")
    return df.with_columns(
        _rolling_corr(pl.col("turnover"), ret_lag, days).alias(name)
    )


def _turnover_delta() -> pl.Expr:
    return pl.col("turnover") - pl.col("turnover").shift(1).over("symbol")


def generate_corr_ret_turnd(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率變動與收益率同步相關。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turnd", days)
    df = _sorted(df)
    return df.with_columns(
        _rolling_corr(_turnover_delta(), pl.col("return_day"), days).alias(name)
    )


def generate_corr_ret_turnd_post(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率變動與收益率相關（量領先一期）。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turnd_post", days)
    df = _sorted(df)
    d_lag = _turnover_delta().shift(1).over("symbol")
    return df.with_columns(
        _rolling_corr(d_lag, pl.col("return_day"), days).alias(name)
    )


def generate_corr_ret_turnd_prior(df: pl.DataFrame, days: int) -> pl.DataFrame:
    """換手率變動與收益率相關（價領先一期）。"""
    days = _require_days(days)
    _require_cols(df, [*_KEY_COLS, "return_day", "turnover"])
    name = _out_name("corr_ret_turnd_prior", days)
    df = _sorted(df)
    ret_lag = pl.col("return_day").shift(1).over("symbol")
    return df.with_columns(
        _rolling_corr(_turnover_delta(), ret_lag, days).alias(name)
    )


# ── 清單清單（方便覆蓋率核對）───────────────────────────────────────

PERIOD_FACTORS: Sequence[str] = (
    "vol_std",
    "vol_down_std",
    "vol_up_std",
    "vol_highlow_avg",
    "vol_highlow_std",
    "vol_upshadow_avg",
    "vol_upshadow_std",
    "vol_downshadow_avg",
    "vol_downshadow_std",
    "liq_turn_avg",
    "liq_turn_std",
    "liq_vstd",
    "liq_amihud_avg",
    "liq_amihud_std",
    "liq_shortcut_avg",
    "liq_shortcut_std",
    "corr_price_turn",
    "corr_price_turn_post",
    "corr_price_turn_prior",
    "corr_ret_turn",
    "corr_ret_turn_post",
    "corr_ret_turn_prior",
    "corr_ret_turnd",
    "corr_ret_turnd_post",
    "corr_ret_turnd_prior",
)

FIXED_FACTORS: Sequence[str] = (
    "mmt_normal_M",
    "mmt_normal_A",
    "mmt_avg_M",
    "mmt_avg_A",
    "mmt_intraday_M",
    "mmt_intraday_A",
    "mmt_overnight_M",
    "mmt_overnight_A",
    "mmt_off_limit_M",
    "mmt_off_limit_A",
    "mmt_range_M",
    "mmt_range_A",
    "mmt_route_M",
    "mmt_route_A",
    "mmt_discrete_M",
    "mmt_discrete_A",
    "mmt_sec_rank_M",
    "mmt_sec_rank_A",
    "mmt_time_rank_M",
    "mmt_highest_days_A",
)

SKIPPED_FACTORS: Sequence[str] = (
    "mmt_report_overnight",
    "mmt_report_jump",
    "mmt_report_period",
    # 資金流 / 北向 / 融資融券 / 籌碼 / 複合 — 見模組 docstring
)
