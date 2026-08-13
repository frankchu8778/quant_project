"""單檔跑一次：AlphaGen 實驗結果 → 加權合成因子 → 深度單因子回測。

把 ``alphagen_test.ipynb`` 的手動流程接到 ``src/factor/components`` 的深度回測上，
一條指令從實驗目錄跑到評估報表：

    載入 pool JSON → 建 FactorEngine → 注入 base features → 一次算完所有表達式
      → 依 weights 加權合成 → 建深度回測面板 → DeepFactorTester.run_all → 報表 + 圖

用法::

    python -m src.factor.run_deep_eval_alphagen --target-date 20260805
    python -m src.factor.run_deep_eval_alphagen --experiment all_20_None_..._rl \\
        --holding-period 5 --scope both --top-plots 5

與 notebook 的三個差異，都是刻意的：

1. **不在因子端套 untradable 遮罩。** 面板的 ``untradable`` 已經做了同一件事，而且是
   在正確的時點上做的（ADR-0002）。因子值留著、由評估層剔除比較乾淨。要復刻 notebook
   的行為可加 ``--apply-untradable-mask``。
2. **自動注入 alpha101/191 base features。** notebook 的 markdown 說明了這個需求但
   程式沒做；這裡從表達式裡掃出 ``$alpha101_042`` 這類引用再回頭算它們。
3. **評估窗與資料窗分開。** 資料要從 ``--start-time`` 開始（表達式有回看期），但只在
   ``--eval-start/--eval-end`` 之間評估。

深度回測本身的參數與判讀請見 ``src/factor/components/usage.md``。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

DEFAULT_RESULTS_BASE = "/mnt/d/alphagen_out/results"
DEFAULT_RAM_PATH = "/dev/shm/qlib_ram"
DEFAULT_FEATURE_CONFIG = (
    "/home/newt/quant_project/setting_files/feature_config_alpha101.json"
)
DEFAULT_OUT_DIR = "/dev/shm/deep_eval_alphagen"

#: 表達式裡對 alpha101/191 base feature 的引用，例如 ``$alpha101_042``。
_BASE_FEATURE_RE = re.compile(r"\$(alpha(?:101|191))_(\d{3})\b")


@dataclass(frozen=True)
class RunConfig:
    """一次執行的全部設定。"""

    results_base: Path
    experiment: str
    pool_filter: tuple[str, ...]
    start_time: str
    end_time: str
    eval_start: str | None
    eval_end: str | None
    device: str
    panel_device: str
    qlib_data_path: str
    duckdb_path: str
    instrument: str
    feature_config: str
    holding_period: int
    return_periods: tuple[int, ...]
    max_lag: int
    group_count: int
    min_names: int
    min_coverage: float
    seed: int
    fee_rate: float
    tax_rate: float
    slippage_bps: float
    scope: str
    top_plots: int
    series_top: int
    apply_untradable_mask: bool
    out_dir: Path


# ---------------------------------------------------------------------------
# 1. 載入實驗結果
# ---------------------------------------------------------------------------


def resolve_experiment(results_base: Path, experiment: str | None, target_date: str | None) -> str:
    """挑出要跑的實驗目錄名。"""
    if experiment:
        if not (results_base / experiment).is_dir():
            raise FileNotFoundError(f"找不到實驗目錄 {results_base / experiment}")
        return experiment

    if not target_date:
        raise ValueError("--experiment 與 --target-date 至少要給一個")

    matches = sorted(d for d in os.listdir(results_base) if target_date in d)
    if not matches:
        raise FileNotFoundError(f"{results_base} 下沒有含 {target_date} 的實驗目錄")
    if len(matches) > 1:
        print(f"[warn] {target_date} 對到 {len(matches)} 個實驗，取第一個：{matches[0]}")
        for m in matches[1:]:
            print(f"       其餘：{m}")
    return matches[0]


def load_pools(result_dir: Path, pool_filter: Sequence[str]) -> Dict[str, dict]:
    """讀進實驗目錄下的所有 pool JSON。"""
    pools: Dict[str, dict] = {}
    for file in sorted(os.listdir(result_dir)):
        if not file.endswith(".json") or file == "feature_config.json":
            continue
        if pool_filter and not any(p in file for p in pool_filter):
            continue
        with open(result_dir / file, "r") as f:
            data = json.load(f)
        if "exprs" not in data or "weights" not in data:
            print(f"[warn] {file} 沒有 exprs/weights，略過")
            continue
        if len(data["exprs"]) != len(data["weights"]):
            raise ValueError(
                f"{file} 的 exprs({len(data['exprs'])}) 與 "
                f"weights({len(data['weights'])}) 長度不一致"
            )
        pools[file] = data

    if not pools:
        raise FileNotFoundError(f"{result_dir} 下沒有可用的 pool JSON")
    return pools


def name_expressions(pools: Dict[str, dict]) -> tuple[List[str], List[str]]:
    """幫每條表達式配上 ``{pool 檔名}_{該 pool 內索引}`` 的欄位名。

    同一條表達式可能出現在多個 pool，這裡不去重——欄位名要能對回它所屬的 pool。
    """
    col_names, expr_strs = [], []
    for pool_file, pool in pools.items():
        stem = Path(pool_file).stem
        for i, expr in enumerate(pool["exprs"]):
            col_names.append(f"{stem}_{i:03d}")
            expr_strs.append(expr)
    return col_names, expr_strs


# ---------------------------------------------------------------------------
# 2. FactorEngine 與 base features
# ---------------------------------------------------------------------------


def build_engine(cfg: RunConfig):
    """建 FactorEngine。feature_config 必須在 import 之前設好。"""
    os.environ["ALPHAGEN_FEATURE_CONFIG"] = cfg.feature_config
    from src.factor_engine import FactorEngine

    return FactorEngine(
        qlib_data_path=cfg.qlib_data_path,
        instrument=cfg.instrument,
        start_time=cfg.start_time,
        end_time=cfg.end_time,
        device=cfg.device,
        max_backtrack_days=300,
        max_future_days=0,
        adjust_factor="back",
    )


def ffill_features(engine, fields: Sequence[str]) -> None:
    """沿時間軸前向填充原始價格欄位：t 缺值就沿用已填好的 t-1。"""
    import torch

    period = engine._full_period()
    with torch.no_grad():
        for field in fields:
            name = field.lower().lstrip("$")
            panel = engine.parse(f"${name}").evaluate(engine.data, period).clone()
            for t in range(1, panel.shape[0]):
                panel[t] = torch.where(torch.isnan(panel[t]), panel[t - 1], panel[t])
            engine.inject_feature(name, panel, replace=True)


def required_base_features(expr_strs: Sequence[str]) -> List[str]:
    """掃出表達式引用到的 alpha101/191 base feature，依名稱排序。"""
    found = set()
    for expr in expr_strs:
        for family, number in _BASE_FEATURE_RE.findall(expr):
            found.add(f"{family}_{number}")
    return sorted(found)


def inject_base_features(engine, expr_strs: Sequence[str]) -> List[str]:
    """注入表達式需要的 base features，回傳實際注入的清單。

    AlphaGen 訓練時把 alpha101/191 當成 base feature，搜出來的表達式會直接引用
    ``$alpha101_042``。不先算出來注入，parser 解析階段就會失敗。
    """
    ffill_features(engine, ["close", "open", "high", "low"])
    # $vwap：alpha101/191 大量使用，NA 用 $close 補
    engine.inject_from_expr("vwap", "SafeDiv($amount, $volume)", fill_with="close")

    needed = required_base_features(expr_strs)
    if not needed:
        print("表達式沒有引用 alpha101/191 base feature，跳過注入")
        return []

    # qlib dump 通常已經把 alpha101/191 當成一般欄位存進去了（載入訊息裡看得到）。
    # 已經在的就不要重算——重算不只多花時間，Alpha101 的表達式本身還要回看數十天，
    # 在資料窗起點會直接撞 OutOfDataRangeError。
    present = {str(f).lower().lstrip("$") for f in engine.data._features}
    missing = [n for n in needed if n not in present]
    print(f"表達式引用 {len(needed)} 個 base feature，其中 {len(present & set(needed))} 個已在資料中")
    if not missing:
        return []

    from src.alphas.alpha101 import Alpha101
    from src.alphas.alpha191 import Alpha191

    repos = {"alpha101": Alpha101, "alpha191": Alpha191}
    injected = []
    for name in missing:
        family, number = name.rsplit("_", 1)
        method = getattr(repos[family], f"alpha{number}", None)
        if method is None:
            raise AttributeError(
                f"表達式引用了 ${name}，資料裡沒有，"
                f"{repos[family].__name__} 也沒有 alpha{number}()"
            )
        engine.inject_from_expr(name, method(), replace=True)
        injected.append(name)

    print(f"補算並注入 {len(injected)} 個：{', '.join(injected)}")
    return injected


# ---------------------------------------------------------------------------
# 3. 計算因子並加權合成
# ---------------------------------------------------------------------------


def compute_factor_panel(engine, col_names: List[str], expr_strs: List[str], cfg: RunConfig) -> pl.DataFrame:
    """一次算完所有表達式，回傳 polars 寬表（symbol, date, *col_names）。"""
    df = engine.calc_many_df(expr_strs=expr_strs, names=col_names)

    if cfg.apply_untradable_mask:
        # 復刻 notebook 的行為。預設不走這條——面板會在正確的時點做同一件事。
        flags = engine.load_raw_df(["$untradable"])
        mask = flags["$untradable"] == 0
        df = df.loc[mask.reindex(df.index, fill_value=False)]

    df = (
        df.reset_index()
        .rename(columns={"datetime": "date", "instrument": "symbol"})[
            ["date", "symbol", *col_names]
        ]
        .sort_values(["date", "symbol"])
        .reset_index(drop=True)
    )

    wide = pl.from_pandas(df).with_columns(
        pl.col("date").cast(pl.Date),
        pl.col("symbol").cast(pl.String),
        *[pl.col(c).cast(pl.Float64) for c in col_names],
    )

    if cfg.eval_start:
        wide = wide.filter(pl.col("date") >= pl.lit(cfg.eval_start).str.to_date())
    if cfg.eval_end:
        wide = wide.filter(pl.col("date") <= pl.lit(cfg.eval_end).str.to_date())
    return wide


def pool_factor_frames(
    wide: pl.DataFrame,
    pools: Dict[str, dict],
    col_names: List[str],
    expr_strs: List[str],
) -> Dict[str, pl.DataFrame]:
    """依各 pool 的 weights 把成員欄位加權合成單一因子。"""
    frames: Dict[str, pl.DataFrame] = {}
    cursor = 0
    for pool_file, pool in pools.items():
        n = len(pool["exprs"])
        # name_expressions 是照 pools 的順序連續配號的，直接用游標切片即可，
        # 不必用 expr_strs.index()——重複的表達式會讓 index() 指到別的 pool。
        member_cols = col_names[cursor : cursor + n]
        cursor += n

        weighted = pl.sum_horizontal(
            [pl.col(c) * float(w) for c, w in zip(member_cols, pool["weights"])]
        )
        frames[Path(pool_file).stem] = (
            wide.select("symbol", "date", weighted.alias("value"))
            .drop_nulls("value")
            .filter(pl.col("value").is_finite())
        )
    return frames


def expr_factor_frames(wide: pl.DataFrame, col_names: List[str]) -> Dict[str, pl.DataFrame]:
    """每條表達式各自一個因子框。"""
    return {
        c: wide.select("symbol", "date", pl.col(c).alias("value"))
        .drop_nulls("value")
        .filter(pl.col("value").is_finite())
        for c in col_names
    }


# ---------------------------------------------------------------------------
# 4. 深度回測
# ---------------------------------------------------------------------------


def build_panel(cfg: RunConfig):
    """建深度回測面板。回傳 (panel, config)。"""
    from src.factor.components.align_and_adjust import load_aligned_adjusted_daily
    from src.factor.components.deep_panel import DeepBacktestConfig, prepare_panel

    bt_config = DeepBacktestConfig(
        holding_period=cfg.holding_period,
        return_periods=cfg.return_periods,
        max_lag=cfg.max_lag,
        group_count=cfg.group_count,
        min_names=cfg.min_names,
        min_coverage=cfg.min_coverage,
        seed=cfg.seed,
        fee_rate=cfg.fee_rate,
        tax_rate=cfg.tax_rate,
        slippage_bps=cfg.slippage_bps,
    )
    raw = load_aligned_adjusted_daily(
        start_time=cfg.start_time,
        end_time=cfg.end_time,
        qlib_data_path=cfg.qlib_data_path,
        duckdb_path=cfg.duckdb_path,
        instrument=cfg.instrument,
        device=cfg.panel_device,
    )
    return prepare_panel(raw, bt_config), bt_config


def evaluate(panel, bt_config, factors: Dict[str, pl.DataFrame]):
    """對每個因子跑一次 run_all。單一因子失敗不中斷整批。"""
    from src.factor.components.deep_eval import DeepFactorTester

    tester = DeepFactorTester(panel, bt_config)
    results, failures = {}, {}
    for i, (name, frame) in enumerate(factors.items(), 1):
        try:
            results[name] = tester.run_all(frame, name=name)
        except Exception as exc:  # noqa: BLE001 — 一個因子壞掉不該讓整批白跑
            failures[name] = f"{type(exc).__name__}: {exc}"
            print(f"  [{i}/{len(factors)}] {name}  失敗：{failures[name]}")
            continue
        if i % 25 == 0 or i == len(factors):
            print(f"  [{i}/{len(factors)}] 已完成")
    return results, failures


def summarise(results) -> pl.DataFrame:
    """把所有結果疊成一張表，依 |Rank IC| 由大到小排序。"""
    rows = []
    for name, r in results.items():
        row = r.summary().with_columns(
            pl.lit(r.coverage.coverage).alias("coverage"),
            pl.lit(r.early_exit_count).alias("early_exit"),
            pl.lit(r.dropped_days).alias("dropped_days"),
        )
        rows.append(row)
    # diagonal：欄位理應一致（deep_eval 保證鍵集合固定），但一個因子的欄位差異
    # 不值得讓整批 49 個 pool 的結果全部丟掉。
    return pl.concat(rows, how="diagonal_relaxed").sort(
        pl.col("Rank_IC_mean").abs(), descending=True, nulls_last=True
    )


def build_json(
    results,
    pools: Dict[str, dict],
    cfg: RunConfig,
    table: pl.DataFrame,
    series_top: int = 0,
) -> dict:
    """把全部因子的結果組成一份可以直接 json.dump 的字典。

    每個 pool 帶著自己的表達式與權重一起輸出，報表才自帶出處——只有指標的話，
    隔幾天回頭看不知道 ``100352_steps_pool`` 到底是哪十條式子加權出來的。

    ``series_top`` 只讓排名最前的幾個因子附上逐日序列。序列是畫圖的唯一來源，
    但每個因子都附會讓 JSON 膨脹數十倍，所以預設誰都不附。
    """
    by_stem = {Path(f).stem: p for f, p in pools.items()}
    ranking = table["factor"].to_list()
    with_series = set(ranking[:series_top]) if series_top > 0 else set()

    factors = {}
    for name, result in results.items():
        entry = result.to_dict(include_series=name in with_series)
        entry["rank"] = ranking.index(name) + 1 if name in ranking else None
        pool = by_stem.get(name)
        if pool is not None:
            entry["n_exprs"] = len(pool["exprs"])
            entry["weights"] = pool["weights"]
            entry["exprs"] = pool["exprs"]
        factors[name] = entry

    return {
        "experiment": cfg.experiment,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "holding_period": cfg.holding_period,
            "return_periods": list(cfg.return_periods),
            "group_count": cfg.group_count,
            "max_lag": cfg.max_lag,
            "min_names": cfg.min_names,
            "min_coverage": cfg.min_coverage,
            "seed": cfg.seed,
            "fee_rate": cfg.fee_rate,
            "tax_rate": cfg.tax_rate,
            "slippage_bps": cfg.slippage_bps,
            "data_range": [cfg.start_time, cfg.end_time],
            "eval_range": [cfg.eval_start, cfg.eval_end],
            "scope": cfg.scope,
        },
        "notes": {
            "ranking": "factors 內的 rank 依 |Rank_IC_mean| 由大到小",
            "P_rank_ic_gt": "Rank IC > 0.02 的交易日比例（panda_factor 的 P(IC>0.02)，實際打在 rank_ic 上）",
            "P_rank_ic_lt": "Rank IC < -0.02 的交易日比例",
            "monotonicity": "各組年化報酬與組序的相關係數絕對值，1 為完美單調",
            "group_stats": "panda_factor 口徑：年化用 252/持有期、波動 ddof=0、"
                           "最大回撤走算術累加、夏普扣 2.5%、勝率按自然月、"
                           "換手率 = 本期在組內但上期不在的比例",
            "no_benchmark": "不含超額/跟蹤誤差/資訊比率——benchmark 是宇宙等權平均而非市場指數",
            "nulls": "null 代表該項算不出來（樣本不足或分母為零），不是 0",
        },
        "n_factors": len(factors),
        "factors": factors,
    }


def save_plots(results, table: pl.DataFrame, out_dir: Path, top_n: int) -> None:
    """把排名最前的幾個因子各存一張 2x2 圖。"""
    if top_n <= 0:
        return
    import warnings

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from src.factor.components.deep_eval import use_cjk_font

    cjk = use_cjk_font()
    if not cjk:
        print("[note] 找不到中文字型，圖上的中文會顯示成方框（數據不受影響）")

    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        if not cjk:
            warnings.filterwarnings("ignore", message="Glyph .* missing from font")
        for name in table["factor"].to_list()[:top_n]:
            fig, _ = results[name].plot_all()
            fig.suptitle(name)
            fig.savefig(plot_dir / f"{name}.png", dpi=110, bbox_inches="tight")
            plt.close(fig)
    print(f"圖表：{plot_dir}（前 {min(top_n, table.height)} 名）")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AlphaGen pool → 加權合成 → 深度單因子回測（單檔跑一次）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    src = p.add_argument_group("實驗來源")
    src.add_argument("--results-base", default=DEFAULT_RESULTS_BASE)
    src.add_argument("--experiment", default=None, help="實驗子目錄名；與 --target-date 擇一")
    src.add_argument("--target-date", default=None, help="以日期字串挑實驗目錄，例如 20260805")
    src.add_argument(
        "--pool",
        action="append",
        default=[],
        help="只跑檔名含此字串的 pool，可重複給；預設全跑",
    )

    data = p.add_argument_group("資料範圍")
    data.add_argument("--start-time", default="2022-01-01", help="資料起點（含表達式回看期）")
    data.add_argument("--end-time", default="2024-12-31")
    data.add_argument("--eval-start", default=None, help="只評估這天之後的因子值")
    data.add_argument("--eval-end", default=None)
    data.add_argument("--device", default="cuda:0", help="FactorEngine 的裝置")
    data.add_argument("--panel-device", default="cpu", help="建面板時讀 qlib 的裝置")
    data.add_argument("--qlib-data-path", default=DEFAULT_RAM_PATH)
    data.add_argument("--duckdb-path", default="/home/newt/quant_project/duckdb/daily_data.duckdb")
    data.add_argument("--instrument", default="all")
    data.add_argument("--feature-config", default=DEFAULT_FEATURE_CONFIG)

    bt = p.add_argument_group("回測設定（詳見 components/usage.md）")
    bt.add_argument("--holding-period", type=int, default=5)
    bt.add_argument("--return-periods", type=int, nargs="+", default=[1, 5, 10, 20])
    bt.add_argument("--max-lag", type=int, default=20)
    bt.add_argument("--group-count", type=int, default=5)
    bt.add_argument("--min-names", type=int, default=20)
    bt.add_argument("--min-coverage", type=float, default=0.5)
    bt.add_argument("--seed", type=int, default=42)
    bt.add_argument(
        "--fee-rate", type=float, default=0.001425 * 0.4, help="手續費率，買賣皆收；預設 4 折"
    )
    bt.add_argument("--tax-rate", type=float, default=0.003, help="證交稅率，僅賣出收取")
    bt.add_argument(
        "--slippage-bps", type=float, default=20.0, help="單邊滑點（基點），買賣各收一次"
    )

    out = p.add_argument_group("輸出")
    out.add_argument(
        "--scope",
        choices=("pool", "expr", "both"),
        default="pool",
        help="評估加權合成因子、每條表達式、或兩者",
    )
    out.add_argument("--top-plots", type=int, default=3, help="存前幾名的圖；0 為不畫")
    out.add_argument(
        "--series-top",
        type=int,
        default=1,
        help="JSON 裡附上逐日序列的前幾名（畫圖用）；0 為都不附",
    )
    out.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    out.add_argument(
        "--apply-untradable-mask",
        action="store_true",
        help="在因子端就套 untradable 遮罩（復刻 notebook；預設交給面板處理）",
    )
    return p.parse_args()


def _config_from_args(args: argparse.Namespace) -> RunConfig:
    results_base = Path(args.results_base)
    experiment = resolve_experiment(results_base, args.experiment, args.target_date)
    return RunConfig(
        results_base=results_base,
        experiment=experiment,
        pool_filter=tuple(args.pool),
        start_time=args.start_time,
        end_time=args.end_time,
        eval_start=args.eval_start,
        eval_end=args.eval_end,
        device=args.device,
        panel_device=args.panel_device,
        qlib_data_path=args.qlib_data_path,
        duckdb_path=args.duckdb_path,
        instrument=args.instrument,
        feature_config=args.feature_config,
        holding_period=args.holding_period,
        return_periods=tuple(sorted(set(args.return_periods) | {args.holding_period})),
        max_lag=args.max_lag,
        group_count=args.group_count,
        min_names=args.min_names,
        min_coverage=args.min_coverage,
        seed=args.seed,
        fee_rate=args.fee_rate,
        tax_rate=args.tax_rate,
        slippage_bps=args.slippage_bps,
        scope=args.scope,
        top_plots=args.top_plots,
        series_top=args.series_top,
        apply_untradable_mask=args.apply_untradable_mask,
        out_dir=Path(args.out_dir) / experiment,
    )


def _step(n: int, title: str) -> float:
    print(f"\n=== [{n}] {title} " + "=" * max(0, 56 - len(title)))
    return time.time()


def main() -> None:
    cfg = _config_from_args(_parse_args())
    result_dir = cfg.results_base / cfg.experiment
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    if not Path(cfg.qlib_data_path).exists():
        raise FileNotFoundError(
            f"{cfg.qlib_data_path} 不存在，qlib ramdisk 需要重建："
            "bash rebuild_data/dump_qlib_to_ramdisk.sh"
        )

    t = _step(1, "載入 pool")
    pools = load_pools(result_dir, cfg.pool_filter)
    col_names, expr_strs = name_expressions(pools)
    print(f"實驗：{cfg.experiment}")
    print(f"pool 數：{len(pools)}，表達式數：{len(expr_strs)}")

    t = _step(2, "建 FactorEngine 與 base features")
    engine = build_engine(cfg)
    inject_base_features(engine, expr_strs)
    print(f"耗時 {time.time() - t:.1f}s")

    t = _step(3, "計算全部表達式")
    wide = compute_factor_panel(engine, col_names, expr_strs, cfg)
    print(
        f"因子寬表：rows={wide.height:,} cols={len(col_names)} "
        f"date=[{wide['date'].min()} ~ {wide['date'].max()}]  耗時 {time.time() - t:.1f}s"
    )

    t = _step(4, "加權合成")
    factors: Dict[str, pl.DataFrame] = {}
    if cfg.scope in ("pool", "both"):
        factors.update(pool_factor_frames(wide, pools, col_names, expr_strs))
    if cfg.scope in ("expr", "both"):
        factors.update(expr_factor_frames(wide, col_names))
    print(f"待評估因子數：{len(factors)}")

    t = _step(5, "建深度回測面板")
    panel, bt_config = build_panel(cfg)
    print(f"面板：rows={panel.height:,} cols={len(panel.columns)}  耗時 {time.time() - t:.1f}s")

    t = _step(6, f"深度回測（holding_period={bt_config.holding_period}）")
    results, failures = evaluate(panel, bt_config, factors)
    print(f"成功 {len(results)} / 失敗 {len(failures)}  耗時 {time.time() - t:.1f}s")

    if not results:
        print("\n沒有任何因子評估成功：")
        for name, msg in failures.items():
            print(f"  {name}: {msg}")
        sys.exit(1)

    _step(7, "輸出")
    table = summarise(results)
    csv_path = cfg.out_dir / f"deep_eval_hp{cfg.holding_period}.csv"
    table.write_csv(csv_path)
    print(f"報表：{csv_path}")

    json_path = cfg.out_dir / f"deep_eval_hp{cfg.holding_period}.json"
    payload = build_json(results, pools, cfg, table, series_top=cfg.series_top)
    # allow_nan=False：NaN 不是合法 JSON，to_dict 已經轉成 null，這裡當作防線
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"JSON：{json_path}")

    if failures:
        fail_path = cfg.out_dir / "failures.json"
        fail_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2))
        print(f"失敗清單：{fail_path}")

    save_plots(results, table, cfg.out_dir, cfg.top_plots)

    cols = ["factor", "n_days", "coverage", "Rank_IC_mean", "Rank_IC_ir",
            "Rank_IC_t", "P_rank_ic_gt", "P_rank_ic_lt", "monotonicity",
            "long_short_mean", "net_long_short_mean"]
    with pl.Config(tbl_rows=20, tbl_width_chars=200, fmt_str_lengths=40):
        print(table.select(cols).head(20))
    print(
        "\n判讀提醒：先看 coverage，再看 net_long_short_mean——"
        "扣掉成本才是能不能用的判準。n_days 是換倉次數，不是交易日數（ADR-0003）。"
    )


if __name__ == "__main__":
    main()
