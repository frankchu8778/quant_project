"""以 FactorEngine 面板對齊 DuckDB 日線，並計算累乘復權價。"""

from __future__ import annotations

from datetime import date
from typing import Sequence, Union

import duckdb
import polars as pl

from src.factor_engine import FactorEngine

PRICE_COLS: tuple[str, ...] = ("open", "high", "low", "close")
DEFAULT_QLIB_PATH = "/dev/shm/qlib_ram"
DEFAULT_DUCKDB_PATH = "/home/newt/quant_project/duckdb/daily_data.duckdb"


def load_aligned_adjusted_daily(
    start_time: str,
    end_time: str,
    *,
    qlib_data_path: str = DEFAULT_QLIB_PATH,
    duckdb_path: str = DEFAULT_DUCKDB_PATH,
    instrument: Union[str, Sequence[str]] = "all",
    device: str = "cpu",
    table: str = "daily_data",
    price_cols: Sequence[str] = PRICE_COLS,
    adj_col: str = "adj_factor",
    verbose: bool = True,
) -> pl.DataFrame:
    """
    以 FactorEngine 的完整 date/symbol 為主索引，left-join DuckDB 日線後填充，
    再依 adj_factor 累乘得到 OHLC 復權價（*_adj）。

    對齊規則（與批量測試 notebook 相同）：
    - Engine 基準外的 DuckDB pairs 只報告、不併入
    - OHLC 按 symbol forward_fill；volume / return_day 缺值填 0
    - adj_factor 缺值（Engine 補出的日期）視為 1；原始值必須 > 0
    """
    engine_pairs = _engine_date_symbol_pairs(
        qlib_data_path=qlib_data_path,
        instrument=instrument,
        start_time=start_time,
        end_time=end_time,
        device=device,
        verbose=verbose,
    )
    df = _align_duckdb_to_engine(
        engine_pairs,
        duckdb_path=duckdb_path,
        table=table,
        price_cols=price_cols,
        verbose=verbose,
    )
    return _apply_cumulative_adjust(df, price_cols=price_cols, adj_col=adj_col)


def _engine_date_symbol_pairs(
    *,
    qlib_data_path: str,
    instrument: Union[str, Sequence[str]],
    start_time: str,
    end_time: str,
    device: str,
    verbose: bool,
) -> pl.DataFrame:
    engine = FactorEngine(
        qlib_data_path=qlib_data_path,
        instrument=instrument,
        start_time=start_time,
        end_time=end_time,
        device=device,
        max_backtrack_days=0,
        max_future_days=0,
        features=["open"],
        adjust_factor="none",
    )
    engine_index = engine.calc_df("$open", col_name="_open").index.to_frame(index=False)
    engine_index.columns = ["date", "symbol"]
    pairs = (
        pl.from_pandas(engine_index)
        .with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("symbol").cast(pl.String),
        )
        .sort(["symbol", "date"])
    )
    if verbose:
        print(f"FactorEngine 基準：{pairs.height:,} 個 date/symbol pairs")
    return pairs


def _align_duckdb_to_engine(
    engine_pairs: pl.DataFrame,
    *,
    duckdb_path: str,
    table: str,
    price_cols: Sequence[str],
    verbose: bool,
) -> pl.DataFrame:
    con = duckdb.connect(database=duckdb_path, read_only=True)
    try:
        duck_df = (
            con.execute(f"SELECT * FROM {table}").pl()
            .with_columns(
                pl.col("date").cast(pl.Date),
                pl.col("symbol").cast(pl.String),
                pl.lit(True).alias("_duck_present"),
            )
        )
    finally:
        con.close()

    outside = duck_df.select(["date", "symbol"]).join(
        engine_pairs, on=["date", "symbol"], how="anti"
    )
    if verbose and outside.height:
        print(f"注意：DuckDB 有 {outside.height:,} 個 pairs 不在 Qlib/Engine 基準內，將不納入")

    df = engine_pairs.join(duck_df, on=["date", "symbol"], how="left").sort(
        ["symbol", "date"]
    )
    missing_pair_count = df["_duck_present"].null_count()
    df = (
        df.with_columns(
            [pl.col(col).forward_fill().over("symbol").alias(col) for col in price_cols]
        )
        .with_columns(
            pl.col("volume").fill_null(0),
            pl.col("return_day").fill_null(0),
        )
        .drop("_duck_present")
    )
    if verbose:
        print(f"DuckDB 原始：{duck_df.height:,} rows")
        print(
            f"Engine 對齊後：{df.height:,} rows（新增並填充 {missing_pair_count:,} 個 pairs）"
        )
    return df


def _apply_cumulative_adjust(
    df: pl.DataFrame,
    *,
    price_cols: Sequence[str] = PRICE_COLS,
    adj_col: str = "adj_factor",
) -> pl.DataFrame:
    invalid_adj_count = df.filter(
        pl.col(adj_col).is_not_null() & (pl.col(adj_col) <= 0)
    ).height
    if invalid_adj_count:
        raise ValueError(f"{adj_col} 有 {invalid_adj_count:,} 筆小於或等於 0，復權無法進行")

    return (
        df.sort(["symbol", "date"])
        .with_columns(
            pl.col(adj_col)
            .fill_null(1.0)
            .cum_prod()
            .over("symbol")
            .alias("cum_adj_factor")
        )
        .with_columns(
            [(pl.col(col) * pl.col("cum_adj_factor")).alias(f"{col}_adj") for col in price_cols]
        )
    )


if __name__ == "__main__":
# 復權累乘：缺值視為 1；day1 adj=1.1 → cum=1.1；day2 null→1 → cum 仍為 1.1
    # close_adj = close * cum_adj_factor → 11.0, 12.1
    sample = pl.DataFrame(
        {
            "symbol": ["A", "A"],
            "date": [date(2020, 1, 1), date(2020, 1, 2)],
            "open": [10.0, 11.0],
            "high": [10.0, 11.0],
            "low": [10.0, 11.0],
            "close": [10.0, 11.0],
            "adj_factor": [1.1, None],
        }
    )
    out = _apply_cumulative_adjust(sample)
    assert abs(out["cum_adj_factor"][0] - 1.1) < 1e-12
    assert abs(out["cum_adj_factor"][1] - 1.1) < 1e-12  # null → 1
    assert abs(out["close_adj"][0] - 11.0) < 1e-12
    assert abs(out["close_adj"][1] - 12.1) < 1e-12
    print("align_and_adjust self-check ok")
