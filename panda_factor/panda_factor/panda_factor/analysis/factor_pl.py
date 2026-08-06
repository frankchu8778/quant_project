"""``factor`` 類別的 polars 加速版本（Phase 3）。

以子類別覆寫 ``start_backtest``，**不改動 analysis/factor.py**。其餘方法
（``cal_df_stock``、``cal_turnover_rate``、``cal_df_info1``、``cal_df_info2``、
``draw_*``）全部沿用父類別實作。

為什麼 ``df_pnl`` / ``df_ic`` 仍回傳 pandas
------------------------------------------
兩者在 ``factor.py`` 內部約有 25 處讀取，且相依於 **index 即日期** 這件事：
- ``cal_df_info1``（factor.py:215/219）以 ``groupby(pd.Grouper(freq='M'))`` 做月度彙總，
  需要 DatetimeIndex
- ``draw_pct`` / ``draw_ic`` / ``draw_ic_dacay`` 直接把 index 當 x 軸餵給 matplotlib

polars 沒有 index 概念。硬要把這些一併改掉，等於把 Phase 3 的範圍擴大到繪圖與
統計表格式化 —— 那是計畫中明確排除的 P3 項目。因此此處的策略是：
**運算過程走 polars，出口再轉回 pandas 並還原 index 契約。**
"""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd
import polars as pl

from panda_factor.analysis.factor import factor
from panda_factor.analysis.factor_func_pl import cal_backtest_frames_pl

__all__ = ["factor_pl"]

_Frame = Union[pd.DataFrame, pl.DataFrame]


def _as_polars(df: _Frame, date_col: str = "date") -> pl.DataFrame:
    """統一轉成 polars。pandas 輸入時 NaN 會依 pl.from_pandas 預設轉為 null。"""
    if isinstance(df, pl.DataFrame):
        return df
    out = df
    if date_col not in out.columns and out.index.name in (None, date_col):
        out = out.reset_index()
        if date_col not in out.columns and "index" in out.columns:
            out = out.rename(columns={"index": date_col})
    return pl.from_pandas(out.reset_index(drop=True))


def _benchmark_as_polars(df: _Frame, date_col: str = "date") -> pl.DataFrame:
    """benchmark 允許 pandas（日期為 index）或 polars（日期為欄位）兩種形式。"""
    if isinstance(df, pl.DataFrame):
        return df
    out = df.copy()
    if date_col not in out.columns:
        out = out.reset_index().rename(columns={out.index.name or "index": date_col})
    return pl.from_pandas(out.reset_index(drop=True))


def _long_to_wide_stock(
    long: pl.DataFrame, date_col: str, group_col: str, group_cnt: int
) -> pd.DataFrame:
    """把長格式持倉表（date × group → symbol list）攤成父類別的寬表形狀。

    欄位順序固定為 ``group1_code``…``group{N}_code`` —— 這是隱性契約，
    ``cal_df_info1``（factor.py:171/176/182）以位置索引 ``.iloc[:, n]`` 存取，
    欄序錯了不會報錯，只會把各組的數字對調。

    快速路徑用 ``partition_by`` 逐組取出，比 ``pivot`` 便宜約四成（實測 5.6ms vs
    9.8ms）；但它相依於「每組都存在、且各組的日期序列完全一致」。該前提在現行流程下
    必然成立（``grouping_factor_pl`` 已保證每日相異值數 ≥ group_cnt，故每日 N 組皆有
    成員），然而本方法是公開介面，可能收到任意 df，因此前提不成立時退回 pivot。
    """
    parts = long.partition_by(group_col, as_dict=True, maintain_order=True)
    ref_dates = None
    data: dict[str, list] = {}
    for n in range(1, group_cnt + 1):
        sub = parts.get((n,))
        if sub is None:
            ref_dates = None  # 某組完全缺席
            break
        sub = sub.sort(date_col)
        dates = sub[date_col].to_list()
        if ref_dates is None:
            ref_dates = dates
        elif dates != ref_dates:
            ref_dates = None  # 各組日期對不齊
            break
        data[f"group{n}_code"] = sub["codes"].to_list()

    if ref_dates is not None:
        df_stock = pd.DataFrame(data, index=ref_dates)
        df_stock.index.name = None
        return df_stock

    # 退路：pivot 能容忍缺格（缺的位置留 null），父類別對此有處理分支
    wide = long.with_columns(
        (pl.lit("group") + pl.col(group_col).cast(pl.Utf8) + pl.lit("_code")).alias("_col")
    ).pivot(on="_col", index=date_col, values="codes")
    ordered = [date_col] + [
        f"group{n}_code"
        for n in range(1, group_cnt + 1)
        if f"group{n}_code" in wide.columns
    ]
    wide = wide.select(ordered).sort(date_col)
    # Series.to_list() 直接給出 list of lists，省掉 to_pandas() 產生 ndarray 再逐格
    # tolist() 的往返（父類別的 cell 型別契約是 Python list）
    df_stock = pd.DataFrame(
        {c: wide[c].to_list() for c in wide.columns if c != date_col},
        index=wide[date_col].to_list(),
    )
    df_stock.index.name = None
    return df_stock


class factor_pl(factor):
    """``factor`` 的 polars 版，只覆寫 ``start_backtest``。

    用法與父類別完全相同::

        alpha = factor_pl(name=factor_name, group_number=5)
        alpha.set_backtest_parameters(period=1, predict_direction=1)
        alpha.start_backtest(df_cuted, df_benchmark)

    ``df_cuted`` 與 ``df_benchmark`` 可為 pandas 或 polars。回測完成後
    ``df_pnl`` / ``df_ic`` / ``df_info`` / ``df_info2`` 的型別與內容均與父類別一致。
    """

    # 供 cal_turnover_rate 重用的長格式持倉表，由 cal_df_stock 建立
    _stock_long_pl: Optional[pl.DataFrame] = None

    def cal_df_stock(self, df: _Frame, date_col: str = "date") -> None:
        """對應 factor.cal_df_stock（factor.py:121），巢狀 groupby 改為單次聚合。

        ``self.df_stock`` 的形狀與父類別一致：index 為日期、欄位為
        ``group1_code``…``group{N}_code``、每格是該組當日的 symbol list。
        """
        group_col = f"{self.name}_group"
        pdf = _as_polars(df, date_col)
        if group_col not in pdf.columns or pdf.height == 0:
            self.df_stock = pd.DataFrame()
            self._stock_long_pl = None
            return

        long = (
            pdf.group_by([date_col, group_col])
            .agg(pl.col("symbol").alias("codes"))
            .sort([group_col, date_col])
        )
        self._stock_long_pl = long

        self.df_stock = _long_to_wide_stock(
            long, date_col, group_col, self.group_cnt
        )

    def cal_turnover_rate(self) -> None:
        """對應 factor.cal_turnover_rate（factor.py:66）。

        父類別以雙層 Python 迴圈 + ``.iloc`` 純量存取 + Python ``set`` 差集計算，
        完全未向量化；此處改為一次 ``list.set_difference`` 運算式算完所有日期與分組。

        換手率定義（factor.py:114-115）::

            turnover[i, n] = |今日持倉 - period 日前持倉| / |period 日前持倉|

        前 ``period`` 列因無前值而為 NaN，與父類別 ``if i < self.period: continue`` 一致。

        註：父類別另有一條處理 ``df_stock`` 出現缺值（某日某組完全無成員）的分支，
        該情況在現行流程下不可達 —— ``grouping_factor`` 已濾掉相異值數不足 ``group_cnt``
        的日子，故每個交易日必定 N 組皆有成員。
        """
        if self.df_stock.empty:
            return
        if self._stock_long_pl is None:
            # df_stock 由外部直接指派（未經本類別的 cal_df_stock）時沒有長格式快取，
            # 退回父類別實作以免靜默不計算。
            super().cal_turnover_rate()
            return

        group_col = f"{self.name}_group"
        date_col = self._stock_long_pl.columns[0]

        turnover = (
            self._stock_long_pl.with_columns(
                pl.col("codes").shift(self.period).over(group_col).alias("_prev")
            )
            .with_columns(
                (
                    pl.col("codes").list.set_difference(pl.col("_prev")).list.len()
                    / pl.col("_prev").list.len()
                )
                .cast(pl.Float64)
                .alias("_turnover")
            )
            .with_columns(
                (
                    pl.lit("group")
                    + pl.col(group_col).cast(pl.Utf8)
                    + pl.lit("_day_turnover")
                ).alias("_col")
            )
            .pivot(on="_col", index=date_col, values="_turnover")
        )

        ordered = [date_col] + [
            f"group{n}_day_turnover"
            for n in range(1, self.group_cnt + 1)
            if f"group{n}_day_turnover" in turnover.columns
        ]
        df_turnover = (
            turnover.select(ordered).sort(date_col).to_pandas().set_index(date_col)
        )
        df_turnover.index.name = None
        self.df_turnover = df_turnover

    def start_backtest(
        self,
        df: _Frame,
        df_benchmark_pct: _Frame,
        date_col: str = "date",
    ) -> None:
        """對應 factor.start_backtest（factor.py:261），逐日迴圈改由 polars 一次算完。"""
        # 空表檢查不需要把整張表轉成 pandas —— pandas 與 polars 都有 .columns，
        # 列數則各用 len() / .height 取得。原先的 df.to_pandas() 會為了這個判斷
        # 物化整份 df_cuted（59k 列 × 30 餘欄）。
        n_rows = df.height if isinstance(df, pl.DataFrame) else len(df)
        if n_rows == 0 or self.name not in df.columns:
            print('回测数据缺失!')
            return

        self.cal_df_stock(df)
        self.cal_turnover_rate()

        df_ic_pl, df_pnl_pl = cal_backtest_frames_pl(
            _as_polars(df, date_col),
            factor_name=self.name,
            group_cnt=self.group_cnt,
            period=self.period,
            df_benchmark=_benchmark_as_polars(df_benchmark_pct, date_col),
            date_col=date_col,
            logger=getattr(self, "logger", None) if not isinstance(
                getattr(self, "logger", None), type
            ) else None,
        )

        df_pnl = df_pnl_pl.to_pandas().set_index(date_col)
        df_pnl.index.name = None
        df_ic = df_ic_pl.to_pandas().set_index(date_col)
        df_ic.index.name = None

        # 以下超額報酬與多空組合的推導，與 factor.py:317-335 完全相同
        for n in range(1, self.group_cnt + 3):
            if n <= self.group_cnt:
                df_pnl[f'group{n}_pro'] = df_pnl[f'group{n}_pnl'] - df_pnl['return_benchmark']
            elif n == self.group_cnt + 1:  # 多空组合1
                if self.predict_direction == 0:
                    df_pnl['group_ls'] = df_pnl['group1_pnl'] - df_pnl[f'group{self.group_cnt}_pnl']
                    df_pnl['group_ls_pro'] = df_pnl['group1_pro'] - df_pnl[f'group{self.group_cnt}_pro']
                else:
                    df_pnl['group_ls'] = df_pnl[f'group{self.group_cnt}_pnl'] - df_pnl['group1_pnl']
                    df_pnl['group_ls_pro'] = df_pnl[f'group{self.group_cnt}_pro'] - df_pnl['group1_pro']
            elif n == self.group_cnt + 2:  # 多空组合2
                if self.group_cnt >= 4:
                    if self.predict_direction == 0:
                        df_pnl['group_ls_2'] = df_pnl['group2_pnl'] - df_pnl[f'group{self.group_cnt - 1}_pnl']
                        df_pnl['group_ls_2_pro'] = df_pnl['group2_pro'] - df_pnl[f'group{self.group_cnt - 1}_pro']
                    else:
                        df_pnl['group_ls_2'] = df_pnl[f'group{self.group_cnt - 1}_pnl'] - df_pnl['group2_pnl']
                        df_pnl['group_ls_2_pro'] = df_pnl[f'group{self.group_cnt - 1}_pro'] - df_pnl['group2_pro']

        self.df_pnl = df_pnl
        self.df_ic = df_ic

        self.cal_df_info1()
        self.cal_df_info2()
