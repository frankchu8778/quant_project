"""AlphaGen factor pool 檢驗：因子計算、加權合成、panda_factor 回測。"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from panda_factor.panda_factor.panda_factor.analysis.factor import factor
from panda_factor.panda_factor.panda_factor.analysis.factor_func import (
    cal_pct_lag,
    ext_out_3std,
    grouping_factor,
)
from src.config import RAM_PATH
from src.factor_engine import FactorEngine

warnings.filterwarnings("ignore", category=FutureWarning)

DEFAULT_PLOT_OUTPUT_DIR = Path("/dev/shm")

RETURN_WINDOWS = [
    ("1day_return", 2, 1),
    ("3day_return", 4, 1),
    ("5day_return", 6, 1),
    ("10day_return", 11, 1),
    ("20day_return", 21, 1),
    ("30day_return", 31, 1),
]


@dataclass
class AlphagenPoolConfig:
    result_dir: str | Path
    experiment_name: str = ""
    pool_index: int = 0
    combined_col: str = "Alpha"
    group_cnt: int = 5
    period: int = 1
    predict_direction: int = 1
    require_ic_threshold_for_plot: bool = False
    qlib_data_path: str = RAM_PATH
    instrument: str = "all"
    start_time: str = "2016-01-01"
    end_time: str = "2026-05-15"
    device: str = "cpu"
    max_backtrack_days: int = 300
    max_future_days: int = 0
    adjust_factor: str = "back"
    plot_output_dir: str | Path = DEFAULT_PLOT_OUTPUT_DIR
    show_plot: bool = False


@dataclass
class AlphagenPoolMetrics:
    ic_mean: float
    rank_ic: float
    t_stat: float
    pool_index: int
    n_exprs: int
    title: str
    pool_keys: list[str] = field(default_factory=list)


@dataclass
class AlphagenPoolResult:
    metrics: AlphagenPoolMetrics
    alpha_fb: factor
    df_factor: pd.DataFrame
    df_cuted: pd.DataFrame
    df_benchmark: pd.DataFrame
    selected_pool: dict[str, Any]
    expr_strs: list[str]
    weights: list[float]
    report_path: Path | None = None


class AlphagenPoolAnalyzer:
    """封裝 AlphaGen pool 從表達式計算到 IC 回測的完整流程。"""

    def __init__(self, config: AlphagenPoolConfig) -> None:
        self.config = config
        if not self.config.experiment_name:
            self.config.experiment_name = Path(self.config.result_dir).name
        self._pools: list[dict[str, Any]] | None = None
        self.engine = FactorEngine(
            qlib_data_path=config.qlib_data_path,
            instrument=config.instrument,
            start_time=config.start_time,
            end_time=config.end_time,
            device=config.device,
            max_backtrack_days=config.max_backtrack_days,
            max_future_days=config.max_future_days,
            adjust_factor=config.adjust_factor,
        )
        self.df_returns = self._build_returns()
        self.tradable_mask = self._build_tradable_mask()

    @staticmethod
    def load_pools(result_dir: str | Path) -> list[dict[str, Any]]:
        path = Path(result_dir)
        if not path.is_dir():
            raise FileNotFoundError(f"result_dir 不存在: {path}")
        pools: list[dict[str, Any]] = []
        for file in sorted(path.glob("*.json")):
            with open(file, "r", encoding="utf-8") as f:
                pools.append(json.load(f))
        if not pools:
            raise ValueError(f"目錄內無 .json pool 檔: {path}")
        return pools

    @staticmethod
    def parse_pool(pool: dict[str, Any]) -> tuple[list[str], list[float]]:
        if not isinstance(pool, dict):
            raise TypeError(f"預期 dict，得到 {type(pool)}")
        exprs = pool.get("exprs")
        weights = pool.get("weights")
        if exprs is None or weights is None:
            raise KeyError(
                f"pool 須含 'exprs' 與 'weights'，目前 keys={list(pool.keys())}"
            )
        if not isinstance(exprs, list) or not isinstance(weights, list):
            raise TypeError("exprs 與 weights 須為 list")
        if len(exprs) != len(weights):
            raise ValueError(
                f"exprs 長度 ({len(exprs)}) 與 weights 長度 ({len(weights)}) 不一致"
            )
        expr_strs = [str(e).strip() for e in exprs]
        if any(not s for s in expr_strs):
            raise ValueError("exprs 內含空字串")
        alpha_weights = [float(x) for x in weights]
        return expr_strs, alpha_weights

    def _resolve_pool_index(self, pool_index: int | None) -> int:
        pools = self._get_pools()
        idx = self.config.pool_index if pool_index is None else pool_index
        if idx < 0:
            idx = len(pools) + idx
        if idx < 0 or idx >= len(pools):
            raise IndexError(f"pool_index={idx} 超出 [0, {len(pools) - 1}]")
        return idx

    def _get_pools(self) -> list[dict[str, Any]]:
        if self._pools is None:
            self._pools = self.load_pools(self.config.result_dir)
        return self._pools

    def _build_returns(self) -> pd.DataFrame:
        df_close = self.engine.calc_df("$close", col_name="close").sort_index()
        out: list[pd.Series] = []
        for name, end_lead, start_lead in RETURN_WINDOWS:
            s = df_close.groupby(level="instrument", group_keys=False)["close"].transform(
                lambda x, el=end_lead, sl=start_lead: x.shift(-el) / x.shift(-sl) - 1
            )
            s.name = name
            out.append(s)
        df_returns = pd.concat(out, axis=1)
        df_returns.reset_index(inplace=True)
        return df_returns

    @staticmethod
    def _get_tradable_disposed_mask(df: pd.DataFrame) -> pd.Series:
        if "$is_tradable" not in df.columns or "$is_disposed" not in df.columns:
            raise ValueError("DataFrame 中缺少 $is_tradable 或 $is_disposed 欄位")
        return (df["$is_tradable"] == 1) & (df["$is_disposed"] == 0)

    def _build_tradable_mask(self) -> pd.Series:
        df_flags = self.engine.load_raw_df(["$is_tradable", "$is_disposed"])
        return self._get_tradable_disposed_mask(df_flags)

    @staticmethod
    def _apply_tradable_mask(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        m = mask.reindex(df.index, fill_value=False)
        return df.loc[m]

    def output_dir_for_pool(self, pool_index: int) -> Path:
        """輸出根目錄 / 實驗名稱 / pool_{index}（實驗名稱對應 DEFAULT_EXPERIMENT）。"""
        return (
            Path(self.config.plot_output_dir)
            / self.config.experiment_name
            / f"pool_{pool_index}"
        )

    def build_combined_factor(
        self,
        expr_strs: list[str],
        weights: list[float],
    ) -> pd.DataFrame:
        factor_name = self.config.combined_col
        alpha_names = [f"alpha_{i}" for i in range(len(expr_strs))]
        df = self.engine.calc_many_df(expr_strs=expr_strs, names=alpha_names)
        df = self._apply_tradable_mask(df, self.tradable_mask)

        w = np.asarray(weights, dtype=float)
        mat = df[alpha_names].to_numpy(dtype=np.float64)
        # 各子因子覆蓋率不同：缺值視為 0 貢獻，僅在「全部為 NaN」時丟棄該列
        combined = np.nansum(mat * w, axis=1)
        all_nan = np.isnan(mat).all(axis=1)
        combined[all_nan] = np.nan
        df[factor_name] = combined
        out = df[[factor_name]].dropna()
        if out.empty:
            raise ValueError(
                "加權合成後無有效樣本（可交易區間內所有子因子皆為 NaN）。"
                "請檢查 expression 或資料區間。"
            )
        return out.copy()

    def prepare_for_backtest(self, df_alpha: pd.DataFrame) -> pd.DataFrame:
        factor_name = self.config.combined_col
        df_factor = pd.merge(
            df_alpha.reset_index(),
            self.df_returns,
            on=["datetime", "instrument"],
            how="left",
        )
        df_factor = df_factor.rename(
            columns={"datetime": "date", "instrument": "symbol"}
        )
        df_factor["date"] = pd.to_datetime(df_factor["date"])

        if "returns_lag1" not in df_factor.columns:
            df_factor = cal_pct_lag(df_factor)

        df_factor = df_factor.groupby("date", group_keys=False).apply(
            lambda g: ext_out_3std(g.copy(), factor_name, process_inf=True)
        )
        index_names = list(getattr(df_factor.index, "names", []) or [])
        if "date" in index_names and "date" in df_factor.columns:
            df_factor = df_factor.reset_index(drop=True)
        elif "date" in index_names:
            df_factor = df_factor.reset_index()
        return df_factor

    def run_grouping_and_backtest(
        self,
        df_factor: pd.DataFrame,
    ) -> tuple[factor, pd.DataFrame, pd.DataFrame]:
        factor_name = self.config.combined_col
        cfg = self.config
        df_finite = df_factor[np.isfinite(df_factor[factor_name])].copy()
        df_cuted, df_benchmark = grouping_factor(
            df=df_finite,  # type: ignore[arg-type]
            factor_name=factor_name,
            group_cnt=cfg.group_cnt,
        )
        alpha_fb = factor(name=factor_name, group_number=cfg.group_cnt)
        alpha_fb.set_backtest_parameters(
            period=cfg.period,
            predict_direction=cfg.predict_direction,
        )
        if df_cuted.empty or factor_name not in df_cuted.columns:
            raise ValueError(
                "分組後無有效資料（grouping_factor 結果為空）。"
                "請確認合成因子在足夠交易日上有足夠非 NaN 樣本。"
            )
        alpha_fb.start_backtest(df_cuted, df_benchmark)
        if alpha_fb.df_ic.empty:
            raise ValueError(
                "回測未產生 IC 序列（可能每日分組數不足）。"
                f"df_cuted 列數={len(df_cuted)}"
            )
        return alpha_fb, df_cuted, df_benchmark

    @staticmethod
    def _metric_float(ic_info: pd.DataFrame, label: str, factor_name: str) -> float:
        raw = ic_info.loc[label, factor_name]
        if raw == "" or raw is None:
            return float("nan")
        return float(str(raw).rstrip("%"))

    def _build_metrics(
        self,
        alpha_fb: factor,
        pool_index: int,
        n_exprs: int,
        selected_pool: dict[str, Any],
    ) -> AlphagenPoolMetrics:
        ic_info = alpha_fb.df_info2
        name = alpha_fb.name
        return AlphagenPoolMetrics(
            ic_mean=self._metric_float(ic_info, "IC_mean", name),
            rank_ic=self._metric_float(ic_info, "Rank_IC", name),
            t_stat=self._metric_float(ic_info, "t統計量", name),
            pool_index=pool_index,
            n_exprs=n_exprs,
            title=f"alphagen pool[{pool_index}] n={n_exprs}",
            pool_keys=list(selected_pool.keys()),
        )

    def analyze_pool(
        self,
        pool_index: int | None = None,
        pool: dict[str, Any] | None = None,
    ) -> AlphagenPoolResult:
        if pool is not None:
            expr_strs, weights = self.parse_pool(pool)
            idx = pool_index if pool_index is not None else self.config.pool_index
            selected_pool = pool
        else:
            pools = self._get_pools()
            idx = self._resolve_pool_index(pool_index)
            selected_pool = pools[idx]
            expr_strs, weights = self.parse_pool(selected_pool)

        print(f"計算中：pool [{idx}]，共 {len(expr_strs)} 條 expression…")

        df_alpha = self.build_combined_factor(expr_strs, weights)
        df_factor = self.prepare_for_backtest(df_alpha)
        alpha_fb, df_cuted, df_benchmark = self.run_grouping_and_backtest(df_factor)
        metrics = self._build_metrics(alpha_fb, idx, len(expr_strs), selected_pool)
        result = AlphagenPoolResult(
            metrics=metrics,
            alpha_fb=alpha_fb,
            df_factor=df_factor,
            df_cuted=df_cuted,
            df_benchmark=df_benchmark,
            selected_pool=selected_pool,
            expr_strs=expr_strs,
            weights=weights,
        )
        result.report_path = self.save_report_md(result)
        return result

    @staticmethod
    def should_skip_plot(metrics: AlphagenPoolMetrics, require_threshold: bool) -> bool:
        if not require_threshold:
            return False
        return not (
            (metrics.ic_mean > 0.02 or metrics.rank_ic > 0.02) and metrics.t_stat > 2
        )

    def save_report_md(self, result: AlphagenPoolResult) -> Path:
        """僅寫入流程說明 Markdown（無 CSV、無數據表）。"""
        out_dir = self.output_dir_for_pool(result.metrics.pool_index)
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / "factor_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._workflow_comparison_markdown())
        print(f"說明已寫入: {md_path}")
        return md_path

    @staticmethod
    def _workflow_comparison_markdown() -> str:
        return """# 與 rolling.ipynb 流程差異

| 步驟 | rolling.ipynb (XGB_pred) | alphagen_pool_analyzer |
|------|--------------------------|-------------------------|
| 因子來源 | 模型預測 `pred_by_day` stack 成 long | AlphaGen JSON `exprs` + `weights` |
| 因子計算 | 直接 merge 預測值 | `FactorEngine.calc_many_df` + `nansum` 加權 |
| 可交易篩選 | 無（notebook 內未做） | `$is_tradable` / `$is_disposed` mask |
| 極值處理 | 無 | 逐日 `ext_out_3std` |
| 收益合併 | `merge(df_returns)` | 同左 |
| 分組回測 | `grouping_factor` + `start_backtest` | 同左 |
| 統計檢視 | `show_df_info(0/1)` 於 notebook 顯示 | 終端 `print_summary` 印出 IC 與分組表 |
| 圖表 | `draw_*` + `plt.show()` | `draw_*` 存 PNG 至輸出目錄 |
"""

    @staticmethod
    def print_summary(result: AlphagenPoolResult) -> None:
        """終端輸出 show_df_info(0/1) 統計表（對應 rolling.ipynb）。"""
        alpha_fb = result.alpha_fb
        m = result.metrics
        print(f"\n{m.title}  IC_mean={m.ic_mean}  Rank_IC={m.rank_ic}  t={m.t_stat}")

        if alpha_fb.df_info.empty:
            print("多空分組統計: 無資料")
        else:
            print("\n=== 多空分組統計 (show_df_info 0) ===")
            print(alpha_fb.df_info.to_string())

        if alpha_fb.df_info2.empty:
            print("\nIC 統計: 無資料")
        else:
            print("\n=== IC 統計 (show_df_info 1) ===")
            print(alpha_fb.df_info2.to_string())

        if result.report_path:
            print(f"\n流程說明: {result.report_path}")

    def plot(self, result: AlphagenPoolResult) -> list[Path]:
        alpha_fb = result.alpha_fb
        if result.df_cuted.empty or alpha_fb.df_ic.empty or alpha_fb.df_pnl.empty:
            print("略過畫圖：回測資料為空，請先確認 IC 指標已正常計算。")
            return []

        title = result.metrics.title
        out_dir = self.output_dir_for_pool(result.metrics.pool_index)
        out_dir.mkdir(parents=True, exist_ok=True)
        show = self.config.show_plot
        saved: list[Path] = []

        def _draw(
            draw_fn: Callable[[], None],
            filename: str,
            subtitle: str = "",
        ) -> None:
            _orig_show = plt.show
            plt.show = lambda *args, **kwargs: None
            try:
                draw_fn()
                if subtitle:
                    plt.gcf().suptitle(subtitle)
                path = out_dir / filename
                plt.gcf().savefig(path, dpi=200, bbox_inches="tight")
                saved.append(path)
                print(f"已儲存: {path}")
                if show:
                    _orig_show()
            finally:
                plt.show = _orig_show
                plt.close()

        _draw(alpha_fb.draw_pct, "group_return.png", title)
        _draw(lambda: alpha_fb.draw_ic(0), "ic_normal.png", f"{title} — IC (normal)")
        _draw(lambda: alpha_fb.draw_ic(1), "ic_rank.png", f"{title} — IC (rank)")
        _draw(alpha_fb.draw_ic_dacay, "ic_decay.png", f"{title} — IC decay")
        print(f"共 {len(saved)} 張圖已寫入: {out_dir}")
        return saved
