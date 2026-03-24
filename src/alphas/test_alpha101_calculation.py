"""
測試 Alpha101 因子使用 FactorEngine (alphagen) 引擎計算的實際結果
檢查計算結果的合理性、數據質量等

使用方法:
    # 測試所有因子（快速模式，只測試前 5 個）
    python -m src.alphas.test_alpha101_calculation_v2 --max-factors 5

    # 測試所有因子
    python -m src.alphas.test_alpha101_calculation_v2

    # 測試單個因子
    python -m src.alphas.test_alpha101_calculation_v2 --factor alpha001

    # 自定義時間範圍
    python -m src.alphas.test_alpha101_calculation_v2 --start-time 2021-01-01 --end-time 2023-12-31

注意:
    - 確保 qlib 已正確安裝
    - 確保 RAM/SSD 資料目錄中有 Qlib 格式數據
    - 此版本使用 FactorEngine（基於 alphagen 表達式引擎），不再直接呼叫 D.features
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch

from src.factor_engine import FactorEngine
from src.alphas.alpha101 import Alpha101
from src.config import QLIB_DATA_DIR_TW, RAM_PATH

warnings.filterwarnings("ignore")


# ── 常數 ─────────────────────────────────────────────────────────
# 如果 RAMDisk 有數據就用 RAM，否則回退 SSD
def _resolve_data_path() -> str:
    if os.path.exists(os.path.join(RAM_PATH, "calendars")):
        print(f"偵測到 RAMDisk 數據，使用: {RAM_PATH}")
        return RAM_PATH
    print(f"未偵測到 RAMDisk 數據，回退至 SSD: {QLIB_DATA_DIR_TW}")
    return str(QLIB_DATA_DIR_TW)


# ── IC / RankIC 計算 ────────────────────────────────────────────
def calculate_ic_rankic(
    factor_tensor: torch.Tensor,
    close_tensor: torch.Tensor,
    forward_period: int = 1,
) -> Tuple[pd.Series, pd.Series, Dict]:
    """
    從 Tensor 層面計算 IC / RankIC（截面相關性）。

    Parameters
    ----------
    factor_tensor : Tensor, shape (n_days, n_stocks)
    close_tensor  : Tensor, shape (n_days, n_stocks)
    forward_period : int                        
        未來收益率天數。

    Returns
    -------
    (ic_series, rankic_series, stats_dict)
    """
    from scipy.stats import spearmanr

    n_days = factor_tensor.shape[0]
    if n_days <= forward_period:
        return pd.Series(dtype=float), pd.Series(dtype=float), {}

    # forward return: (close[t+N] / close[t]) - 1
    fwd_return = (close_tensor[forward_period:] / close_tensor[:-forward_period]) - 1.0
    # 對齊因子（取前 n_days - forward_period 天）
    factor_aligned = factor_tensor[: n_days - forward_period]

    # 轉 numpy
    factor_np = factor_aligned.cpu().numpy()
    return_np = fwd_return.cpu().numpy()

    ic_list: List[float] = []
    rankic_list: List[float] = []

    for t in range(factor_np.shape[0]):
        f_day = factor_np[t]
        r_day = return_np[t]

        # 過濾 NaN / Inf
        mask = np.isfinite(f_day) & np.isfinite(r_day)
        if mask.sum() < 5:
            continue

        f_valid = f_day[mask]
        r_valid = r_day[mask]

        # Pearson IC
        ic_val: float = float(np.corrcoef(f_valid, r_valid)[0, 1])
        # Spearman RankIC
        rankic_val: float = float(spearmanr(f_valid, r_valid).statistic)  # type: ignore[union-attr]

        if np.isfinite(ic_val) and np.isfinite(rankic_val):
            ic_list.append(ic_val)
            rankic_list.append(rankic_val)

    ic_series = pd.Series(ic_list, name="IC")
    rankic_series = pd.Series(rankic_list, name="RankIC")

    stats: Dict = {}
    if len(ic_series) > 0:
        stats = {
            "IC_mean": float(ic_series.mean()),
            "IC_std": float(ic_series.std()),
            "IC_IR": float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else None,
            "RankIC_mean": float(rankic_series.mean()),
            "RankIC_std": float(rankic_series.std()),
            "RankIC_IR": (
                float(rankic_series.mean() / rankic_series.std())
                if rankic_series.std() > 0
                else None
            ),
            "IC_positive_ratio": float((ic_series > 0).sum() / len(ic_series)),
            "IC_win_rate": float((ic_series > 0.02).sum() / len(ic_series)),
            "IC_lose_rate": float((ic_series < -0.02).sum() / len(ic_series)),
            "valid_days": len(ic_series),
        }

    return ic_series, rankic_series, stats


# ── 單因子計算 ──────────────────────────────────────────────────
def calculate_alpha_factor(
    factor_name: str,
    expression: str,
    engine: FactorEngine,
    close_tensor: torch.Tensor,
    calculate_ic: bool = False,
    forward_period: int = 1,
) -> Tuple[bool, Optional[pd.DataFrame], Dict]:
    """
    使用 FactorEngine 計算單個 alpha 因子並蒐集統計量。

    Returns
    -------
    (success, data_df_or_None, stats_dict)
    """
    stats: Dict = {
        "factor_name": factor_name,
        "expression": expression,
        "success": False,
        "error": None,
        "data_shape": None,
        "null_count": None,
        "null_percentage": None,
        "inf_count": None,
        "inf_percentage": None,
        "mean": None,
        "std": None,
        "min": None,
        "max": None,
        "median": None,
        "valid_data_points": None,
        "total_data_points": None,
    }

    try:
        # 計算因子 tensor → (n_days, n_stocks)
        factor_tensor = engine.calc(expression)

        # 轉為 DataFrame（MultiIndex: datetime × instrument）
        data_df = engine.data.make_dataframe(factor_tensor, columns=[factor_name])

        if data_df.empty:
            stats["error"] = "計算結果為空"
            return False, None, stats

        factor_values = data_df[factor_name]

        stats["success"] = True
        stats["data_shape"] = data_df.shape
        stats["total_data_points"] = len(factor_values)

        # NaN
        null_count = int(factor_values.isna().sum())
        stats["null_count"] = null_count
        stats["null_percentage"] = (
            float(null_count / len(factor_values) * 100) if len(factor_values) > 0 else 0.0
        )

        # Inf
        inf_count = int(np.isinf(factor_values.to_numpy()).sum())
        stats["inf_count"] = inf_count
        stats["inf_percentage"] = (
            float(inf_count / len(factor_values) * 100) if len(factor_values) > 0 else 0.0
        )

        # 基本統計量（排除 NaN / Inf）
        valid_values = factor_values.replace([np.inf, -np.inf], np.nan).dropna()
        stats["valid_data_points"] = len(valid_values)

        if len(valid_values) > 0:
            stats["mean"] = float(valid_values.mean())
            stats["std"] = float(valid_values.std())
            stats["min"] = float(valid_values.min())
            stats["max"] = float(valid_values.max())
            stats["median"] = float(valid_values.median())

        # IC / RankIC
        if calculate_ic:
            ic_series, rankic_series, ic_stats = calculate_ic_rankic(
                factor_tensor, close_tensor, forward_period
            )
            stats.update(ic_stats)
            stats["ic_series"] = ic_series
            stats["rankic_series"] = rankic_series

        return True, data_df, stats

    except Exception as e:
        stats["error"] = str(e)
        return False, None, stats


# ── 全量測試 ────────────────────────────────────────────────────
def test_all_alpha101_factors(
    engine: FactorEngine,
    max_factors: Optional[int] = None,
    forward_period: int = 1,
) -> pd.DataFrame:
    """
    測試所有 Alpha101 因子。

    Parameters
    ----------
    engine : FactorEngine
        已初始化的因子引擎。
    max_factors : int | None
        最多測試幾個因子（None 表示全部）。
    forward_period : int
        IC 計算使用的未來收益天數。

    Returns
    -------
    pd.DataFrame  各因子的統計結果。
    """
    print(f"開始測試 Alpha101 因子計算")
    print(f"   股票數量: {engine.n_stocks}")
    print(f"   交易日數: {engine.n_days}")
    print(f"   IC 前瞻天數: {forward_period}\n")

    # 預先計算 close tensor（只算一次）
    close_tensor = engine.calc("$close")

    all_factors = Alpha101.get_all_factors()
    factor_names = sorted(all_factors.keys())

    if max_factors is not None:
        factor_names = factor_names[:max_factors]
        print(f"僅測試前 {max_factors} 個因子（快速測試模式）\n")

    results: List[Dict] = []

    for i, factor_name in enumerate(factor_names, 1):
        expression = all_factors[factor_name]
        print(f"[{i}/{len(factor_names)}] 測試 {factor_name}...", end=" ")

        success, _, stats = calculate_alpha_factor(
            factor_name,
            expression,
            engine,
            close_tensor,
            calculate_ic=True,
            forward_period=forward_period,
        )

        if success:
            print("PASS")
            if stats["null_percentage"] is not None and stats["null_percentage"] > 50:
                print(f"   警告: NaN 比例過高 ({stats['null_percentage']:.2f}%)")
            if stats["inf_percentage"] is not None and stats["inf_percentage"] > 0:
                print(f"   警告: 包含 Inf ({stats['inf_percentage']:.2f}%)")
        else:
            print(f"FAIL: {stats['error']}")

        results.append(stats)

    results_df = pd.DataFrame(results)

    # ── 摘要 ──
    print("\n" + "=" * 80)
    print("測試總結")
    print("=" * 80)
    success_count = int(results_df["success"].sum())
    total = len(results_df)
    print(f"成功: {success_count}/{total}")
    print(f"失敗: {total - success_count}/{total}")

    if success_count > 0:
        ok = results_df[results_df["success"]]
        print(f"\n成功因子統計:")
        print(f"   平均 NaN 比例: {ok['null_percentage'].mean():.2f}%")
        print(f"   平均有效數據點: {ok['valid_data_points'].mean():.0f}")
        print(f"   含 Inf 的因子數: {(ok['inf_count'] > 0).sum()}")
        print(f"\n因子值統計範圍:")
        print(f"   平均值: [{ok['mean'].min():.4f}, {ok['mean'].max():.4f}]")
        print(f"   標準差: [{ok['std'].min():.4f}, {ok['std'].max():.4f}]")

    return results_df


# ── 單因子詳細分析 ──────────────────────────────────────────────
def detailed_factor_analysis(
    factor_name: str,
    engine: FactorEngine,
    forward_period: int = 1,
) -> None:
    """對單個因子進行詳細分析並印出報告。"""
    all_factors = Alpha101.get_all_factors()
    if factor_name not in all_factors:
        print(f"因子 {factor_name} 不存在")
        return

    expression = all_factors[factor_name]
    print(f"詳細分析因子: {factor_name}")
    print(f"   表達式: {expression}")
    print(f"   股票數量: {engine.n_stocks}")
    print(f"   交易日數: {engine.n_days}\n")

    close_tensor = engine.calc("$close")

    success, data_df, stats = calculate_alpha_factor(
        factor_name,
        expression,
        engine,
        close_tensor,
        calculate_ic=True,
        forward_period=forward_period,
    )

    if not success:
        print(f"計算失敗: {stats['error']}")
        return

    print("=" * 80)
    print("計算結果統計")
    print("=" * 80)
    skip_keys = {"factor_name", "expression", "success", "error", "ic_series", "rankic_series"}
    for key, value in stats.items():
        if key in skip_keys or value is None:
            continue
        if isinstance(value, float):
            print(f"   {key}: {value:.4f}")
        else:
            print(f"   {key}: {value}")

    # IC / RankIC
    if stats.get("IC_mean") is not None:
        print(f"\nIC / RankIC 統計:")
        print(f"   IC 均值:          {stats.get('IC_mean', 0):.4f}")
        print(f"   IC 標準差:        {stats.get('IC_std', 0):.4f}")
        print(f"   IC IR:            {stats.get('IC_IR', 0):.4f}")
        print(f"   RankIC 均值:      {stats.get('RankIC_mean', 0):.4f}")
        print(f"   RankIC 標準差:    {stats.get('RankIC_std', 0):.4f}")
        print(f"   RankIC IR:        {stats.get('RankIC_IR', 0):.4f}")
        print(f"   IC 正相關比例:    {stats.get('IC_positive_ratio', 0):.2%}")
        print(f"   IC 勝率 (>0.02):  {stats.get('IC_win_rate', 0):.2%}")
        print(f"   IC 敗率 (<-0.02): {stats.get('IC_lose_rate', 0):.2%}")
        print(f"   有效交易日數:     {stats.get('valid_days', 0)}")

        ic_series = stats.get("ic_series")
        if ic_series is not None and len(ic_series) > 0:
            print(f"\nIC 時間序列（最近 10 天）:")
            print(ic_series.tail(10).to_string())

    if data_df is not None and not data_df.empty:
        factor_col = data_df.columns[0]
        print(f"\n數據預覽（前 10 行）:")
        print(data_df.head(10))

        print(f"\n按股票統計:")
        factor_values = data_df[factor_col]
        by_stock = factor_values.groupby(level=1)
        stock_stats = pd.DataFrame(
            {
                "mean": by_stock.mean(),
                "std": by_stock.std(),
                "min": by_stock.min(),
                "max": by_stock.max(),
                "null_count": by_stock.apply(lambda x: x.isna().sum()),
            }
        )
        print(stock_stats)


# ── CLI ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="測試 Alpha101 因子計算（FactorEngine 版）")
    parser.add_argument("--factor", type=str, help="測試單個因子（例如: alpha001）")
    parser.add_argument("--max-factors", type=int, help="最多測試的因子數量（快速測試）")
    parser.add_argument("--start-time", type=str, default="2020-01-01", help="開始時間")
    parser.add_argument("--end-time", type=str, default="2025-12-31", help="結束時間")
    parser.add_argument("--forward-period", type=int, default=1, help="IC 前瞻天數")
    parser.add_argument("--device", type=str, default="cpu", help="計算裝置 (cpu/cuda:0)")

    args = parser.parse_args()

    # 建立引擎（一次載入，後續所有因子共用）
    data_path = _resolve_data_path()
    engine = FactorEngine(
        qlib_data_path=data_path,
        instrument="all",
        start_time=args.start_time,
        end_time=args.end_time,
        max_backtrack_days=260,
        max_future_days=0,
        device=args.device,
    )

    if args.factor:
        detailed_factor_analysis(
            args.factor,
            engine=engine,
            forward_period=args.forward_period,
        )
    else:
        results_df = test_all_alpha101_factors(
            engine=engine,
            max_factors=args.max_factors,
            forward_period=args.forward_period,
        )

        # 儲存結果
        base_dir = "/home/newt/quant_project/testing"
        os.makedirs(base_dir, exist_ok=True)

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d")
        output_json = os.path.join(base_dir, f"alpha101_test_results_{timestamp}.json")

        try:
            # 移除不可序列化的欄位再存檔
            save_df = results_df.drop(columns=["ic_series", "rankic_series"], errors="ignore")
            save_df.to_json(output_json, orient="records", force_ascii=False, date_format="iso")
            print(f"\n測試結果已保存至: {output_json}")
        except Exception as e:
            print(f"儲存 JSON 失敗: {e}")
