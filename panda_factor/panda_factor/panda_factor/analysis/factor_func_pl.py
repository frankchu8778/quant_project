"""factor_func.py 中逐日運算函式的 polars 平行實作。

設計原則
--------
1. **Additive**：本模組完全不改動 factor_func.py。兩套實作並存，呼叫端可逐一遷移，
   隨時可回退，且能在同一份資料上做 A/B 比對（見 tests/test_factor_func_pl.py）。
2. **語意對齊優先於實作相似**：目標是與 pandas 版在數值上等價（容差 1e-8），
   而非逐行照抄。消除 Python 層的逐日 groupby 迴圈正是重構的意義。

與 pandas 版的兩項語意差異（已知且刻意）
--------------------------------------
**NaN vs null** —— pandas 不區分兩者，一律視為缺值；polars 區分，且 NaN 具傳染性
（``pl.Series([1.0, float('nan'), 3.0]).mean()`` 回傳 NaN，而非 2.0）。由 polars
原生運算產生的 NaN（例如 ``0/0``）並不是 null，會讓整個日期截面的 mean/std 變成 NaN，
進而使 clip 邊界失效。因此本模組在聚合前一律先把 NaN 正規化為 null
（見 :func:`nan_to_null`），以對齊 pandas 的缺值語意。
以 ``pl.from_pandas`` 轉入的資料預設已完成此轉換（``nan_to_null=True``）。

**列序** —— pandas 的 ``groupby('symbol')[col].transform(shift)`` 是在各群組內
「依 DataFrame 現有列序」位移，並未先排序；若輸入未依日期排序，其結果其實是錯的。
本模組改為明確依 (symbol, date) 排序後再位移，最後還原輸入列序。因此：
輸入已依日期排序時 → 與 pandas 版逐值相同；輸入未排序時 → 本模組正確、pandas 版不正確。
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
import polars as pl

__all__ = [
    "nan_to_null",
    "cal_pct_lag_pl",
    "ext_out_3std_pl",
    "grouping_factor_pl",
    "to_backtest_contract",
    "qualifying_dates_pl",
    "cal_backtest_frames_pl",
]

# 還原輸入列序用的暫時欄位；以不易碰撞的名稱避免蓋掉使用者欄位
_ROW_IDX = "__pf_row_idx__"
_NOISY = "__pf_noisy__"

DEFAULT_MAX_LAG = 20
DEFAULT_SOURCE_COL = "1day_return"

# grouping_factor 產生的基準報酬欄：(來源欄, 輸出欄)。順序與 factor_func.py:793-799 一致。
BENCHMARK_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("1day_return", "1D_m"),
    ("3day_return", "3D_m"),
    ("5day_return", "5D_m"),
    ("10day_return", "10D_m"),
    ("20day_return", "20D_m"),
    ("30day_return", "30D_m"),
)


def nan_to_null(df: pl.DataFrame, cols: Sequence[str]) -> pl.DataFrame:
    """把指定浮點欄中的 NaN 轉為 null，以對齊 pandas 視 NaN 為缺值的語意。

    polars 的聚合會被 NaN 汙染但會略過 null，因此在任何 mean/std/corr 之前
    都必須做這步，否則單一個 NaN 就會讓整個截面的統計量變成 NaN。
    """
    targets = [
        c for c in cols
        if c in df.columns and df.schema[c] in (pl.Float32, pl.Float64)
    ]
    if not targets:
        return df
    return df.with_columns(
        [
            pl.when(pl.col(c).is_nan()).then(None).otherwise(pl.col(c)).alias(c)
            for c in targets
        ]
    )


def cal_pct_lag_pl(
    df: pl.DataFrame,
    source_col: str = DEFAULT_SOURCE_COL,
    max_lag: int = DEFAULT_MAX_LAG,
    symbol_col: str = "symbol",
    date_col: str = "date",
) -> pl.DataFrame:
    """對應 factor_func.cal_pct_lag（factor_func.py:79）。

    產生 ``returns_lag0`` … ``returns_lag{max_lag}``，其中
    ``returns_lag{i} = source_col.shift(-i)``（各標的獨立位移）。

    pandas 版以 21 次 ``groupby('symbol').transform(shift)`` 完成；此處改為單次
    ``with_columns`` 內的 21 個 ``shift().over()`` 運算式，消除 Python 層迴圈。

    :param df: 至少包含 symbol_col、date_col、source_col 的 polars DataFrame
    :param source_col: 位移來源欄，預設 ``1day_return``
    :param max_lag: 最大落後期數（含），預設 20 → 產生 lag0..lag20 共 21 欄
    :returns: 追加 lag 欄的新 DataFrame，**列序與輸入相同**
    """
    if source_col not in df.columns:
        raise ValueError(f"df 缺少來源欄 {source_col!r}")
    for col in (symbol_col, date_col):
        if col not in df.columns:
            raise ValueError(f"df 缺少 {col!r}")

    exprs = [
        pl.col(source_col).shift(-i).over(symbol_col).alias(f"returns_lag{i}")
        for i in range(0, max_lag + 1)
    ]

    return (
        df.with_row_index(_ROW_IDX)
        .sort([symbol_col, date_col])
        .with_columns(exprs)
        .sort(_ROW_IDX)
        .drop(_ROW_IDX)
    )


def ext_out_3std_pl(
    df: pl.DataFrame,
    factor_name: str,
    noise_std: float = 1e-10,
    process_inf: bool = False,
    date_col: str = "date",
    rng: Optional[np.random.Generator] = None,
) -> pl.DataFrame:
    """對應 factor_func.ext_out_3std（factor_func.py:473），逐日截面 3-sigma 去極值。

    pandas 版由呼叫端以 ``groupby('date', group_keys=False).apply(...)`` 逐組呼叫；
    此處以 ``.over(date_col)`` 視窗運算式一次完成，同時消除函式內與呼叫端兩層迴圈。

    運算順序刻意與 pandas 版一致：加噪音 → 計算截面 mean/std → clip → 處理 inf。
    順序有意義：mean/std 是在**含 inf 的資料上**計算，因此某日若存在 inf，
    該日邊界會變成 NaN 而使 clip 失效 —— 這是 pandas 版的既有行為，此處如實保留。

    :param noise_std: 噪音標準差。實測噪音量級 1e-10 對結果影響 <1e-9（見
        tests/test_golden_baseline.py::test_noise_is_numerically_negligible），
        傳 ``0.0`` 可完全關閉以取得確定性輸出。
    :param process_inf: 是否把 ±inf 換成當日上下邊界
    :param rng: 自訂亂數產生器；未提供時使用 numpy 全域 RNG（與 pandas 版一致）
    :returns: factor_name 欄已去極值的新 DataFrame，列序與輸入相同
    """
    if factor_name not in df.columns:
        raise ValueError(f"df 缺少因子欄 {factor_name!r}")
    if date_col not in df.columns:
        raise ValueError(f"df 缺少 {date_col!r}")

    out = nan_to_null(df, [factor_name]).with_columns(
        pl.col(factor_name).cast(pl.Float64)
    )

    if noise_std:
        draw = rng.normal if rng is not None else np.random.normal
        noise = draw(0.0, noise_std, size=out.height)
        out = out.with_columns(pl.col(factor_name) + pl.Series("__pf_noise__", noise))

    mu = pl.col(factor_name).mean().over(date_col)
    sigma = pl.col(factor_name).std().over(date_col)
    edge_up = mu + 3.0 * sigma
    edge_low = mu - 3.0 * sigma

    out = out.with_columns(pl.col(factor_name).clip(edge_low, edge_up))

    if process_inf:
        out = out.with_columns(
            pl.when(pl.col(factor_name).is_infinite() & (pl.col(factor_name) > 0))
            .then(edge_up)
            .when(pl.col(factor_name).is_infinite() & (pl.col(factor_name) < 0))
            .then(edge_low)
            .otherwise(pl.col(factor_name))
            .alias(factor_name)
        )

    return out


def grouping_factor_pl(
    df: pl.DataFrame,
    factor_name: str,
    group_cnt: int = 10,
    logger=None,
    date_col: str = "date",
    noise_std: float = 1e-10,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """對應 factor_func.grouping_factor（factor_func.py:768）。

    pandas 版以 ``for date, group in df.groupby('date')`` 逐日跑 ``pd.qcut``，再
    ``pd.concat`` 合併；此處改為單一 ``qcut().over(date_col)`` 加一次 ``group_by`` 聚合。

    如實複製的 pandas 行為
    ----------------------
    1. ``group_cnt`` 不在 2..20 範圍內 → 強制改為 10（factor_func.py:784-789）
    2. 某日「去除缺值後的相異值數」< ``group_cnt`` → 該日自 df_cuted 剔除
    3. **某日因子含任何缺值 → 整日自 df_cuted 剔除**。pandas 版此行為並非刻意設計，
       而是 factor_func.py:826-828 把長度為「非缺值筆數」的 qcut 結果指派回長度為
       「全部筆數」的 DataFrame，觸發 ``ValueError: Length of values does not match``，
       再被 :828 的 ``except ValueError`` 捕捉而跳過該日。此處明確以條件式重現。
    4. 被剔除的日子**仍會出現在 df_benchmark 中** —— pandas 版在跳過判斷之前就已寫入
       benchmark（factor_func.py:792-800）。因此 df_benchmark 的日期數可能多於 df_cuted。
    5. 噪音只用於計算分組，``factor_name`` 欄本身保留原值（factor_func.py:827 是把
       噪音加在傳給 qcut 的暫時陣列上，未寫回 DataFrame）。

    :param noise_std: 加在分組用暫時值上的噪音，避免 qcut 分箱邊界重複。傳 ``0.0``
        可得確定性輸出，但在大量重複值的資料上 qcut 可能因邊界重複而拋錯。
    :returns: ``(df_cuted, df_benchmark)``，兩者皆為 polars DataFrame。
        df_benchmark 以 ``date_col`` 為一般欄位而非 index（polars 無 index 概念）；
        需要餵給 pandas 版 ``factor.start_backtest`` 時請用 :func:`to_backtest_contract`。
    """
    if factor_name not in df.columns:
        raise ValueError(f"df 缺少因子欄 {factor_name!r}")
    if date_col not in df.columns:
        raise ValueError(f"df 缺少 {date_col!r}")

    if group_cnt < 2 or group_cnt > 20:
        msg = f"Group count {group_cnt} is out of range (2-20), will use default value 10"
        if logger:
            logger.warning(msg)
        else:
            print(f"Warning: {msg}")
        group_cnt = 10

    src_cols = [src for src, _ in BENCHMARK_COLUMNS if src in df.columns]
    work = nan_to_null(df, [factor_name, *src_cols])

    # 基準報酬：所有日期都要有，且必須在剔除無效日之前計算
    df_benchmark = (
        work.group_by(date_col)
        .agg(
            [
                (pl.col(src).mean() if src in work.columns else pl.lit(None, pl.Float64))
                .alias(dst)
                for src, dst in BENCHMARK_COLUMNS
            ]
        )
        .sort(date_col)
    )

    # 逐日有效性判斷（對應上文 2. 與 3.）
    stats = work.group_by(date_col).agg(
        pl.col(factor_name).null_count().alias("_null_cnt"),
        pl.col(factor_name).drop_nulls().n_unique().alias("_nunique"),
    )
    invalid = stats.filter(
        (pl.col("_null_cnt") > 0) | (pl.col("_nunique") < group_cnt)
    )
    if invalid.height:
        for row in invalid.iter_rows(named=True):
            if row["_null_cnt"] > 0:
                msg = (
                    f"{factor_name},{row[date_col]},contains "
                    f"{row['_null_cnt']} null factor value(s), will skip"
                )
            else:
                msg = (
                    f"Factor {factor_name},{row[date_col]},group count less than "
                    f"{group_cnt}, will skip"
                )
            if logger:
                logger.warning(msg)

    valid_dates = stats.filter(
        (pl.col("_null_cnt") == 0) & (pl.col("_nunique") >= group_cnt)
    ).select(date_col)

    # semi-join 而非 is_in(Series)：後者在 polars 1.x 已標記 deprecated（同型別集合語意有歧義）。
    # 先記錄輸入列序：join 的保序性並非 polars 的文件保證，最後再據此還原，
    # 以免相依於未定義行為。
    work = work.with_row_index(_ROW_IDX).join(valid_dates, on=date_col, how="semi")
    if work.height == 0:
        empty = df.clear().with_columns(
            pl.lit(None, pl.Int64).alias(f"{factor_name}_group")
        )
        return empty, df_benchmark

    # 噪音只作用於分組用的暫時欄，不改動 factor_name 本身
    if noise_std:
        draw = rng.normal if rng is not None else np.random.normal
        noise = draw(0.0, noise_std, size=work.height)
        work = work.with_columns(
            (pl.col(factor_name) + pl.Series("__pf_noise__", noise)).alias(_NOISY)
        )
    else:
        work = work.with_columns(pl.col(factor_name).alias(_NOISY))

    labels = [str(i) for i in range(1, group_cnt + 1)]
    df_cuted = (
        work.with_columns(
            pl.col(_NOISY)
            .qcut(group_cnt, labels=labels)
            .over(date_col)
            # Categorical 直接 cast 成整數會取到「類別索引」（0-based）而非標籤值，
            # 且不會報錯 —— 必須先轉字串再轉整數。factor.py:305 以 `== n` 比較整數，
            # 少了這步會靜默產生 off-by-one 的分組。
            .cast(pl.Utf8)
            .cast(pl.Int64)
            .alias(f"{factor_name}_group")
        )
        .drop(_NOISY)
        # 先還原輸入列序，再依日期做穩定排序 —— 這正是 pandas 版
        # 「groupby('date') 依序迭代 + concat」的等效結果：日期遞增，日內維持原序。
        .sort(_ROW_IDX)
        .sort(date_col, maintain_order=True)
        .drop(_ROW_IDX)
    )

    return df_cuted, df_benchmark


def to_backtest_contract(
    df_cuted: pl.DataFrame,
    df_benchmark: pl.DataFrame,
    date_col: str = "date",
):
    """把 polars 產物轉成 pandas 版 ``factor.start_backtest`` 期望的形狀。

    ``factor.start_backtest`` 有兩項 index 相依：
    - factor.py:305 ``group[group[f'{name}_group'] == n]`` → 分組欄需可與整數比較
    - factor.py:309 ``df_benchmark_pct.loc[date, f'{period}D_m']`` → benchmark 需以日期為 index

    :returns: ``(pd.DataFrame, pd.DataFrame)``
    """
    cuted = df_cuted.to_pandas()
    benchmark = df_benchmark.to_pandas().set_index(date_col)
    benchmark.index.name = None
    return cuted, benchmark


def qualifying_dates_pl(
    df: pl.DataFrame,
    factor_name: str,
    group_cnt: int,
    period: int,
    date_col: str = "date",
    logger=None,
) -> pl.Series:
    """挑出 start_backtest 實際會納入統計的日期（factor.py:277-289）。

    兩道篩選，順序不可對調：
    1. 該日「去除缺值後的相異因子值數」< ``group_cnt`` → 剔除
    2. 對**通過第 1 關**的日期由 0 起編號，只取編號 ≡ 0 (mod period) 者。
       這正是 pandas 版 ``day_count`` 的語意 —— ``day_count`` 只在通過第 1 關時遞增，
       且模數判斷發生在遞增之前，因此取到的是第 0、period、2*period… 個合格日。
    """
    stats = (
        df.group_by(date_col)
        .agg(pl.col(factor_name).drop_nulls().n_unique().alias("_nunique"))
        .sort(date_col)
    )

    if logger is not None:
        for row in stats.filter(pl.col("_nunique") < group_cnt).iter_rows(named=True):
            logger.warning(
                f"因子{factor_name},{row[date_col]},分组小于{group_cnt},已跳过"
            )

    qualifying = stats.filter(pl.col("_nunique") >= group_cnt)
    return (
        qualifying.with_row_index("_k")
        .filter(pl.col("_k") % period == 0)[date_col]
    )


def cal_backtest_frames_pl(
    df: pl.DataFrame,
    factor_name: str,
    group_cnt: int,
    period: int,
    df_benchmark: pl.DataFrame,
    date_col: str = "date",
    max_lag: int = DEFAULT_MAX_LAG,
    logger=None,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """對應 factor.start_backtest 的逐日迴圈（factor.py:277-312）。

    pandas 版每個交易日要跑 43 次 ``.corr()``／``.rank().corr()``（IC、Rank IC，
    加 20 組 lag 各兩種），外加 group_cnt 次分組平均；此處以兩次 ``group_by().agg()``
    一次算完所有日期。

    Rank IC 的計算方式必須特別注意
    ------------------------------
    factor.py:295 寫的是 ``group[name].rank().corr(group[ret].rank())`` ——
    **先各自對整段序列排名，再取 Pearson 相關**。這與 ``corr(method='spearman')``
    在含缺值時**並不等價**（實測差異可達 7e-3）：``.rank()`` 是在各欄自己的完整序列上
    排名（缺值給缺值），Pearson 才做 pairwise 丟棄；Spearman 則是對齊後才排名。
    ``returns_lag*`` 各欄尾端必然有缺值，因此這個差異一定會被觸發。
    此處如實複製 rank-then-pearson，**不可**改用 spearman。

    ``ir`` 亦然：``factor.py:296`` 用的是 ``group.shape[0]``，即**含缺值列**的總列數。

    :returns: ``(df_ic, df_pnl)``，皆為 polars DataFrame 且以 ``date_col`` 為一般欄位。
        欄位順序與 pandas 版一致（df_ic：ic、rank_ic、ir，接著 lag 由 1 至 max_lag
        以 rank_ic_lagN、ic_lagN 交錯排列）。
    """
    ret_col = f"{period}day_return"
    for col in (factor_name, ret_col, date_col):
        if col not in df.columns:
            raise ValueError(f"df 缺少 {col!r}")

    group_col = f"{factor_name}_group"
    if group_col not in df.columns:
        raise ValueError(f"df 缺少分組欄 {group_col!r}")

    lag_cols = [f"returns_lag{i}" for i in range(1, max_lag + 1)]
    missing = [c for c in lag_cols if c not in df.columns]
    if missing:
        raise ValueError(f"df 缺少 lag 欄: {missing[:3]}…（共 {len(missing)} 欄）")

    work = nan_to_null(df, [factor_name, ret_col, *lag_cols])

    dates = qualifying_dates_pl(
        work, factor_name, group_cnt, period, date_col=date_col, logger=logger
    )
    work = work.join(dates.to_frame(), on=date_col, how="semi")

    # ---- IC ----
    ranked_factor = pl.col(factor_name).rank()
    ic_exprs = [
        pl.corr(pl.col(factor_name), pl.col(ret_col)).alias("ic"),
        pl.corr(ranked_factor, pl.col(ret_col).rank()).alias("rank_ic"),
        # ir = ic * sqrt(當日總列數)，列數含缺值列
        (pl.corr(pl.col(factor_name), pl.col(ret_col)) * pl.len().sqrt()).alias("ir"),
    ]
    for i in range(1, max_lag + 1):
        lag = f"returns_lag{i}"
        # 順序須與 factor.py:298-300 的寫入順序一致（rank 先於 ic），
        # 因為 pd.DataFrame(ic_dict).T 的欄位順序即為 dict 的插入順序。
        ic_exprs.append(
            pl.corr(ranked_factor, pl.col(lag).rank()).alias(f"rank_ic_lag{i}")
        )
        ic_exprs.append(pl.corr(pl.col(factor_name), pl.col(lag)).alias(f"ic_lag{i}"))

    df_ic = work.group_by(date_col).agg(ic_exprs).sort(date_col)

    # ---- PNL ----
    pnl_exprs = [
        pl.col(ret_col).filter(pl.col(group_col) == n).mean().alias(f"group{n}_pnl")
        for n in range(1, group_cnt + 1)
    ]
    df_pnl = work.group_by(date_col).agg(pnl_exprs).sort(date_col)

    bench_col = f"{period}D_m"
    if bench_col not in df_benchmark.columns:
        raise ValueError(f"df_benchmark 缺少 {bench_col!r}")
    df_pnl = df_pnl.join(
        df_benchmark.select([date_col, pl.col(bench_col).alias("return_benchmark")]),
        on=date_col,
        how="left",
    )

    return df_ic, df_pnl
