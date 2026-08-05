"""CLI：執行 AlphaGen pool 因子檢驗與回測。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.factor.alphagen_pool_analyzer import (  # noqa: E402
    DEFAULT_PLOT_OUTPUT_DIR,
    AlphagenPoolAnalyzer,
    AlphagenPoolConfig,
)

DEFAULT_RESULTS_BASE = "/mnt/d/alphagen_out/results"
DEFAULT_EXPERIMENT = "all_20_None_20260418050914_rl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(     
        description="AlphaGen pool 因子檢驗（calc → 加權合成 → panda_factor 回測）"
    )
    parser.add_argument(
        "--results-base",
        type=str,
        default=DEFAULT_RESULTS_BASE,
        help=f"AlphaGen 結果根目錄（預設 {DEFAULT_RESULTS_BASE}）",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default=DEFAULT_EXPERIMENT,
        help=f"實驗子目錄名稱（預設 {DEFAULT_EXPERIMENT}）",
    )
    parser.add_argument(
        "--pool-index",
        type=int,
        default=-1,
        help="要檢驗的 pool 索引（-1 為最後一個，預設 -1）",
    )
    parser.add_argument("--start-time", type=str, default="2016-01-01")
    parser.add_argument("--end-time", type=str, default="2026-05-15")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="僅輸出 IC 指標，不儲存圖表",
    )
    parser.add_argument(
        "--plot-dir",
        type=str,
        default=str(DEFAULT_PLOT_OUTPUT_DIR),
        help=f"圖表輸出目錄（預設 {DEFAULT_PLOT_OUTPUT_DIR}，WSL 對應 \\\\wsl.localhost\\Ubuntu\\dev\\shm）",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="儲存後另開視窗顯示圖表（預設僅存檔）",
    )
    parser.add_argument(
        "--require-ic-threshold-for-plot",
        action="store_true",
        help="未達 IC 門檻（IC>0.02 或 Rank_IC>0.02 且 t>2）時略過畫圖",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result_dir = Path(args.results_base) / args.experiment

    config = AlphagenPoolConfig(
        result_dir=result_dir,
        experiment_name=args.experiment,
        pool_index=args.pool_index,
        require_ic_threshold_for_plot=args.require_ic_threshold_for_plot,
        start_time=args.start_time,
        end_time=args.end_time,
        device=args.device,
        plot_output_dir=args.plot_dir,
        show_plot=args.show,
    )

    analyzer = AlphagenPoolAnalyzer(config)
    pools = analyzer._get_pools()
    resolved = analyzer._resolve_pool_index(args.pool_index)
    out_base = Path(args.plot_dir) / args.experiment / f"pool_{resolved}"
    print(f"實驗目錄: {result_dir}")
    print(f"共 {len(pools)} 個 pool，本次檢驗 index={resolved}")
    print(f"輸出目錄: {out_base}")

    result = analyzer.analyze_pool(pool_index=args.pool_index)
    analyzer.print_summary(result)

    if args.no_plot:
        return

    if AlphagenPoolAnalyzer.should_skip_plot(
        result.metrics, config.require_ic_threshold_for_plot
    ):
        print(
            "\n未滿足 IC 門檻（IC_mean 或 Rank_IC > 0.02 且 t>2），略過畫圖。"
            "可移除 --require-ic-threshold-for-plot 或設為 False。"
        )
        return

    analyzer.plot(result)


if __name__ == "__main__":
    main()
