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

    # ── runtime 注入臨時特徵（可被 $name 表達式讀取）────────────

    def _full_period(self) -> slice:
        """含 backtrack / future 的完整時間窗，對齊 self._data.data 第 0 維。"""
        return slice(-self._data.max_backtrack_days, 1 + self._data.max_future_days)

    def inject_feature(
        self,
        name: str,
        panel: torch.Tensor,
        replace: bool = True,
    ) -> None:
        """
        把 (T_full, n_stocks) panel 掛進 StockData，並註冊給 parser。
        T_full 必須等於 data.data.shape[0]（含 backtrack），滾動算子才正確。
        """
        name = str(name).strip().lower().lstrip("$")
        data = self._data
        t_full, n_stocks = data.data.shape[0], data.n_stocks
        if tuple(panel.shape) != (t_full, n_stocks):
            raise ValueError(
                f"${name} panel shape {tuple(panel.shape)} != "
                f"({t_full}, {n_stocks}) = (T_full, n_stocks)"
            )
        panel = panel.to(device=data.device, dtype=data.data.dtype)

        # parser 認 $name；StockData 認 column
        self._parser._features[name] = name

        if name in data._features:
            if not replace:
                raise ValueError(f"${name} 已存在；設 replace=True 可覆寫")
            j = data._features.index(name)
            data.data[:, j, :] = panel
        else:
            data._features.append(name)
            data.data = torch.cat([data.data, panel.unsqueeze(1)], dim=1)

        print(
            f"[FactorEngine] injected ${name}: "
            f"features={data.n_features}, tensor={tuple(data.data.shape)}"
        )

    def inject_from_expr(
        self,
        name: str,
        expr_str: str,
        fill_with: Optional[str] = "close",
        replace: bool = True,
    ) -> None:
        """
        用現有表達式算出完整時間軸 panel，可選用另一特徵填 NA，再 inject。
        例：engine.inject_from_expr("vwap", "SafeDiv($amount, $volume)", fill_with="close")
        之後可用 Mean($vwap, 10) 等表達式。
        """
        period = self._full_period()
        # fill_with 的 $xxx 須已在 parser；先算主表達式
        panel = self._parser.parse(expr_str).evaluate(self._data, period)
        if fill_with is not None:
            fill_name = str(fill_with).strip().lower().lstrip("$")
            fill = self._parser.parse(f"${fill_name}").evaluate(self._data, period)
            panel = torch.where(torch.isnan(panel), fill, panel)
        self.inject_feature(name, panel, replace=replace)

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

        # 全部先在 GPU 算完再一次搬回 CPU，避免每因子 calc_df 來回 PCIe
        exprs = [self._parser.parse(s) for s in expr_strs]
        device = self._data.device
        with torch.no_grad():
            tensors = []
            for expr in exprs:
                t = expr.evaluate(self._data)
                if normalize:
                    t = normalize_by_day(t)
                if t.device != device:
                    t = t.to(device, non_blocking=True)
                tensors.append(t)
            stacked = torch.stack(tensors, dim=2)
            if device.type == "cuda":
                torch.cuda.synchronize(device)
        return self._data.make_dataframe(stacked, columns=names)
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