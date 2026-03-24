"""
FactorEngine — 基於 alphagen 表達式引擎的因子計算封裝層。

所有算子直接 import 自 alphagen.data.expression，不複製任何程式碼。
日後在 expression.py 新增算子並加入 Operators 列表後，此處自動可用。
"""

from typing import List, Optional, Union

import torch
import pandas as pd

# ── 直接引用 alphagen 原有模組，不複製 ──────────────────────────
from alphagen.data.expression import (
    Expression,
    Operators,
    Greater,
    Less,
    Pow,
    Eq,
)
from alphagen.data.expressions.rolling import Ts_ArgMax, Ts_ArgMin
from alphagen.data.parser import ExpressionParser
from alphagen.utils.pytorch_utils import normalize_by_day
from alphagen_qlib.stock_data import (
    StockData,
    FeatureType,
    initialize_qlib,
)

from typing import Literal
class FactorEngine:
    """
    因子計算引擎。

    Parameters
    ----------
    qlib_data_path : str
        Qlib dumper 產生的資料目錄路徑（可放 ramdisk）。
    instrument : str | list[str]
        股票池名稱（如 "csi300", "all"）或股票代碼列表。
    start_time, end_time : str
        資料區間，格式 "YYYY-MM-DD"。
    max_backtrack_days : int
        滾動算子可回溯的最大天數，預設 100。
    max_future_days : int
        允許看未來的最大天數（用於 target），預設 0。
    device : str | torch.device
        計算裝置，"cpu" / "cuda:0" 等。
    features : list[FeatureType] | None
        載入的基礎特徵，預設全部 (OPEN, CLOSE, HIGH, LOW, VOLUME)。

    Examples
    --------
    >>> engine = FactorEngine(
    ...     qlib_data_path="/dev/shm/qlib_ram",
    ...     instrument="csi300",
    ...     start_time="2020-01-01",
    ...     end_time="2024-12-31",
    ...     device="cpu",
    ... )
    >>> tensor = engine.calc("Mean($close, 20)")
    >>> df = engine.calc_df("CSRank(Div($close, Mean($close, 10)))")
    >>> df = engine.calc_many_df(
    ...     ["Mean($close, 5)", "Std($volume, 20)"],
    ...     names=["ma5", "vol_std20"],
    ... )
    """

    def __init__(
        self,
        qlib_data_path: str,
        instrument: Union[str, List[str]],
        start_time: str,
        end_time: str,
        max_backtrack_days: int = 260,
        max_future_days: int = 0,
        device: Union[str, torch.device] = "cpu",
        features: Optional[List[FeatureType]] = None,
        adjust_factor: Optional[Literal['pre' , 'back' , 'none']]   = 'none' # 復權設定: 前復權、後復權、不復權
    ) -> None:
        # 1. 先初始化 Qlib（搶在 StockData 的自動初始化之前）
        initialize_qlib(qlib_data_path)

        # 2. device 字串 → torch.device
        if isinstance(device, str):
            device = torch.device(device)

        # 3. 建立表達式解析器（import Operators 列表，自動包含所有算子）
        self._parser = ExpressionParser(
            Operators,
            ignore_case=True,
            non_positive_time_deltas_allowed=False,
            additional_operator_mapping={
                "Power": [Pow],         # Power(a, b) → Pow(a, b)
                "IdxMax": [Ts_ArgMax],  # IdxMax(a, n) → Ts_ArgMax(a, n)
                "IdxMin": [Ts_ArgMin],  # IdxMin(a, n) → Ts_ArgMin(a, n)
            },
        )

        # 4. 載入資料（Qlib 讀取 bin → 3D Tensor）
        print(
            f"[FactorEngine] Loading data: instrument={instrument}, "
            f"period=[{start_time}, {end_time}], device={device}"
        )
        self._data = StockData(
            instrument=instrument,
            start_time=start_time,
            end_time=end_time,
            max_backtrack_days=max_backtrack_days,
            max_future_days=max_future_days,
            features=features,
            device=device,
            adjust_factor=adjust_factor,
        )
        print(
            f"[FactorEngine] Data loaded: "
            f"{self._data.n_days} days, "
            f"{self._data.n_stocks} stocks, "
            f"{self._data.n_features} features, "
            f"tensor shape={tuple(self._data.data.shape)}"
        )

    # ── 公開屬性 ────────────────────────────────────────────────

    @property
    def data(self) -> StockData:
        """底層 StockData 物件，可直接存取 3D Tensor。"""
        return self._data

    @property
    def parser(self) -> ExpressionParser:
        """表達式解析器，可自行呼叫 parser.parse(...)。"""
        return self._parser

    @property
    def n_days(self) -> int:
        return self._data.n_days

    @property
    def n_stocks(self) -> int:
        return self._data.n_stocks

    @property
    def stock_ids(self) -> pd.Index:
        return self._data.stock_ids

    # ── 解析（不計算） ──────────────────────────────────────────

    def parse(self, expr_str: str) -> Expression:
        """
        將字串解析為表達式樹，不進行計算。

        Parameters
        ----------
        expr_str : str
            因子表達式，例如 "Mean($close, 20)"。

        Returns
        -------
        Expression
            可呼叫 .evaluate(data) 的表達式樹節點。
        """
        return self._parser.parse(expr_str)

    # ── 計算 → Tensor ──────────────────────────────────────────

    def calc(
        self,
        expr_str: str,
        normalize: bool = False,
    ) -> torch.Tensor:
        """
        解析並計算因子，回傳原始 Tensor。

        Parameters
        ----------
        expr_str : str
            因子表達式。
        normalize : bool
            是否做截面標準化（每天去均值、除標準差）。

        Returns
        -------
        torch.Tensor
            shape = (n_days, n_stocks)。
        """
        expr = self._parser.parse(expr_str)
        tensor = expr.evaluate(self._data)
        if normalize:
            tensor = normalize_by_day(tensor)
        return tensor

    # ── 計算 → DataFrame ───────────────────────────────────────

    def calc_df(
        self,
        expr_str: str,
        normalize: bool = False,
        col_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        解析並計算單一因子，回傳 MultiIndex DataFrame。

        Parameters
        ----------
        expr_str : str
            因子表達式。
        normalize : bool
            是否做截面標準化。
        col_name : str | None
            欄位名稱，預設使用表達式字串。

        Returns
        -------
        pd.DataFrame
            index = MultiIndex(datetime, instrument)，columns = [col_name]。
        """
        tensor = self.calc(expr_str, normalize=normalize)
        name = col_name if col_name is not None else expr_str
        return self._data.make_dataframe(tensor, columns=[name])

    # ── 批次計算 → 寬表 DataFrame ─────────────────────────────

    def calc_many_df(
        self,
        expr_strs: List[str],
        names: Optional[List[str]] = None,
        normalize: bool = False,
    ) -> pd.DataFrame:
        """
        批次計算多個因子，合併成寬表 DataFrame。

        Parameters
        ----------
        expr_strs : list[str]
            因子表達式列表。
        names : list[str] | None
            各因子的欄位名稱，長度須與 expr_strs 一致。
            預設使用表達式字串本身。
        normalize : bool
            是否做截面標準化。

        Returns
        -------
        pd.DataFrame
            index = MultiIndex(datetime, instrument)，
            columns = names (或表達式字串)。
        """
        if names is not None and len(names) != len(expr_strs):
            raise ValueError(
                f"names 長度 ({len(names)}) 與 expr_strs 長度 ({len(expr_strs)}) 不一致"
            )
        if names is None:
            names = expr_strs

        tensors = [self.calc(expr_str, normalize=normalize) for expr_str in expr_strs]
        return self._data.make_dataframe(tensors, columns=names)
    # ── 直接從 Qlib 原始資料載入指定表達式 ─────────────────────────────
    def load_raw_df(
        self,
        exprs: Union[str, List[str]],
    ) -> pd.DataFrame:
        """
        直接從 Qlib 原始資料載入指定表達式，不經過 engine 的 FeatureType / tensor。
        使用與本 engine 相同的 instrument 與日期範圍。
        exprs: 例如 "$is_tradable", "$is_disposed" 或 ["$is_tradable", "$is_disposed"]
        """
        from qlib.data.dataset.loader import QlibDataLoader
        if isinstance(exprs, str):
            exprs = [exprs]
        instrument = self._data._instrument
        start = self._data._dates[0]
        end = self._data._dates[-1]
        return QlibDataLoader(config=exprs).load(instrument, start, end)