"""批量單因子回測的 spawn worker（供 ProcessPoolExecutor 使用）。"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from typing import Any, Dict, Optional, Tuple

# 每個 worker 進程一份；由 initializer 載入
_WORKER_DF = None


def init_worker(parquet_path: str, project_root: str = "/home/newt/quant_project") -> None:
    """子進程啟動時設定路徑、載入基準面板，並限制內部執行緒數。"""
    global _WORKER_DF

    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault("POLARS_MAX_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

    import polars as pl

    _WORKER_DF = pl.read_parquet(parquet_path)


def run_factor_task(task: Tuple[str, Optional[int]]) -> Dict[str, Any]:
    """計算單一因子並做完整單因子回測，回傳篩選指標。"""
    import numpy as np

    from src.alphas import zhong_jin_vol_price as zj
    import src.factor.single_factor_eval as single_factor_eval
    from src.factor.single_factor_eval import extract_df_info2_metrics, passes_ic_screen

    base_name, days = task
    task_name = f"{base_name}_{days}d" if days is not None else base_name

    if _WORKER_DF is None:
        return {
            "task": task_name,
            "factor": None,
            "days": days,
            "Rank_IC": np.nan,
            "Rank_IC_IR": np.nan,
            "t統計量": np.nan,
            "result": "Worker 未初始化",
            "passed": False,
            "error": "RuntimeError: worker df is None（initializer 未執行）",
        }

    try:
        generator = getattr(zj, f"generate_{base_name}")
        before = set(_WORKER_DF.columns)
        factor_df = generator(_WORKER_DF, days) if days is not None else generator(_WORKER_DF)
        new_columns = [c for c in factor_df.columns if c not in before]
        if len(new_columns) != 1:
            raise RuntimeError(f"預期新增 1 欄，實際新增 {new_columns}")
        factor_name = new_columns[0]

        original_display = single_factor_eval.display
        single_factor_eval.display = lambda _: None
        try:
            with redirect_stdout(io.StringIO()):
                alpha = single_factor_eval.run_single_factor_test(
                    factor_df,
                    factor_name=factor_name,
                    group_count=5,
                    show_plots=False,
                )
        finally:
            single_factor_eval.display = original_display

        metrics = extract_df_info2_metrics(alpha, factor_name)
        rank_ic = metrics["Rank_IC"]
        rank_ic_ir = metrics["Rank_IC_IR"]
        t_stat = metrics["t統計量"]
        passed = passes_ic_screen(metrics)

        return {
            "task": task_name,
            "factor": factor_name,
            "days": days,
            "Rank_IC": rank_ic,
            "Rank_IC_IR": rank_ic_ir,
            "t統計量": t_stat,
            "result": (
                f"Rank_IC={rank_ic:.4f}, Rank_IC_IR={rank_ic_ir:.4f}, t統計量={t_stat:.4f}"
            ),
            "passed": bool(passed),
            "error": None,
        }
    except Exception as exc:
        return {
            "task": task_name,
            "factor": None,
            "days": days,
            "Rank_IC": np.nan,
            "Rank_IC_IR": np.nan,
            "t統計量": np.nan,
            "result": f"{type(exc).__name__}: {exc}",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
