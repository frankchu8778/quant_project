import marimo

__generated_with = "0.20.4"
app = marimo.App()


@app.cell
def _():
    import json
    import os
    import sys
    from pathlib import Path

    import numpy as np
    import pandas as pd

    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    alphagen_factor_result_path = "/dev/shm/out/results"
    experiment_name = "all_20_0_20260322020556_rl"
    result_dir = os.path.join(alphagen_factor_result_path, experiment_name)
    # 每個 JSON 一筆 pool：{"exprs": [str, ...], "weights": [float, ...]}
    expersions = []
    for file in sorted(f for f in os.listdir(result_dir) if f.endswith(".json")):
        with open(os.path.join(result_dir, file), "r") as f:
            expersions.append(json.load(f))
    return expersions, pd


@app.cell
def _(pd):
    from src.config import RAM_PATH
    from src.factor_engine import FactorEngine

    g = globals()
    if g.get("alphagen_test_engine") is None:
        g["alphagen_test_engine"] = FactorEngine(
            qlib_data_path=RAM_PATH,
            instrument="all",
            start_time="2016-01-01",
            end_time="2026-03-21",
            device="cpu",
            max_backtrack_days=300,
            max_future_days=0,
            adjust_factor="back",
        )
    engine = g["alphagen_test_engine"]

    if g.get("alphagen_test_df_returns") is None:
        df_close = engine.calc_df("$close", col_name="close").sort_index()

        return_windows = [
            ("1day_return", 2, 1),
            ("3day_return", 4, 1),
            ("5day_return", 6, 1),
            ("10day_return", 11, 1),
            ("20day_return", 21, 1),
            ("30day_return", 31, 1),
        ]

        out = []
        for _name, end_lead, start_lead in return_windows:
            s = df_close.groupby(level="instrument", group_keys=False)["close"].transform(
                lambda x: x.shift(-end_lead) / x.shift(-start_lead) - 1
            )
            s.name = _name
            out.append(s)

        df_returns = pd.concat(out, axis=1)
        df_returns.reset_index(inplace=True)
        g["alphagen_test_df_returns"] = df_returns
    df_returns = g["alphagen_test_df_returns"]
    return df_returns, engine


@app.cell
def _(expersions):
    """每個元素為一個 pool dict：exprs / weights 等長；用 POOL_INDEX 選第幾個 JSON 結果。"""

    def pool_exprs_weights(pool: dict):
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

    POOL_INDEX = 0
    COMBINED_COL = "Alpha"
    REQUIRE_IC_THRESHOLD_FOR_PLOT = False

    if not expersions:
        raise ValueError("expersions 為空，請確認 result 目錄有 .json")
    if POOL_INDEX < 0 or POOL_INDEX >= len(expersions):
        raise IndexError(f"POOL_INDEX={POOL_INDEX} 超出 [0, {len(expersions) - 1}]")

    selected_pool = expersions[POOL_INDEX]
    expr_strs, ALPHA_WEIGHTS = pool_exprs_weights(selected_pool)
    alpha_names = [f"alpha_{i}" for i in range(len(expr_strs))]
    return (
        ALPHA_WEIGHTS,
        COMBINED_COL,
        POOL_INDEX,
        REQUIRE_IC_THRESHOLD_FOR_PLOT,
        alpha_names,
        expr_strs,
        selected_pool,
    )


@app.cell
def _(COMBINED_COL, engine, pd):
    import matplotlib.pyplot as plt
    import numpy as np

    def process_untradable_and_disposed(
        df,
        drop: bool = False,
        keep_flag: bool = False,
        show_daily_na: bool = True,
    ):
        if "$is_tradable" not in df.columns or "$is_disposed" not in df.columns:
            raise ValueError("DataFrame 中缺少 $is_tradable 或 $is_disposed 欄位")

        valid = (df["$is_tradable"] == 1) & (df["$is_disposed"] == 0)
        factor_cols = [c for c in df.columns if c not in ("$is_tradable", "$is_disposed")]
        merged_masked = df.loc[valid].copy()
        if show_daily_na:

            if isinstance(merged_masked.index, pd.MultiIndex):
                dates = merged_masked.index.get_level_values(0)
            elif "date" in merged_masked.columns:
                dates = merged_masked["date"]
            else:
                raise ValueError("df 需有 date 欄位或 (date, instrument) MultiIndex")
            rows = []
            for date, g in merged_masked.groupby(dates):
                n = len(g)
                row = {"date": date, "總筆數": n}
                for col in factor_cols:
                    if col not in g.columns:
                        continue
                    na_count = g[col].isna().sum()
                    pct = (na_count / n * 100) if n else 0.0
                    row[f"{col}_NA數"] = na_count
                    row[f"{col}_NA_ratio"] = pct
                rows.append(row)
            stats = pd.DataFrame(rows)

            bins = np.linspace(0, 100, 21)
            n_factors = len([c for c in factor_cols if f"{c}_NA_ratio" in stats.columns])
            fig, axes = plt.subplots(n_factors, 1, figsize=(8, 4 * n_factors))
            if n_factors == 1:
                axes = [axes]
            for ax, col in enumerate(factor_cols):
                if f"{col}_NA_ratio" not in stats.columns:
                    continue
                ratio = stats[f"{col}_NA_ratio"]
                counts, bin_edges = np.histogram(ratio, bins=bins)
                bin_labels = [f"{bin_edges[i]:.0f}–{bin_edges[i+1]:.0f}%" for i in range(len(bin_edges) - 1)]
                axes[ax].bar(bin_labels, counts, width=0.8, edgecolor="gray")
                axes[ax].set_xlabel("NA ratio")
                axes[ax].set_ylabel("Times")
                axes[ax].set_title(f"{col} daily NA ratio dist")
                axes[ax].tick_params(axis="x", rotation=45)
            plt.tight_layout()
            plt.show()

        if COMBINED_COL in merged_masked.columns and drop:
            merged_masked = merged_masked.dropna(subset=[COMBINED_COL])

        if keep_flag:
            return merged_masked
        return merged_masked[factor_cols]

    def get_tradable_disposed_mask(df):
        if "$is_tradable" not in df.columns or "$is_disposed" not in df.columns:
            raise ValueError("DataFrame 中缺少 $is_tradable 或 $is_disposed 欄位")
        return (df["$is_tradable"] == 1) & (df["$is_disposed"] == 0)

    def apply_tradable_mask(df, mask):
        m = mask.reindex(df.index, fill_value=False)
        return df.loc[m]

    df_is_tradable = engine.load_raw_df(["$is_tradable", "$is_disposed"])
    tradable_mask = get_tradable_disposed_mask(df_is_tradable)
    return apply_tradable_mask, tradable_mask


@app.cell
def _(
    ALPHA_WEIGHTS,
    COMBINED_COL,
    POOL_INDEX,
    REQUIRE_IC_THRESHOLD_FOR_PLOT,
    alpha_names,
    apply_tradable_mask,
    df_returns,
    engine,
    expr_strs,
    pd,
    selected_pool,
    tradable_mask,
):
    """參考 factor_test copy.ipynb：calc_many_df → 可交易 mask → 加權合併 → 合併收益 → panda_factor 檢驗與畫圖。"""
    import warnings

    import matplotlib.pyplot as plt
    import numpy as np
    from panda_factor.panda_factor.panda_factor.analysis.factor import factor
    from panda_factor.panda_factor.panda_factor.analysis.factor_func import (
        cal_pct_lag,
        ext_out_3std,
        grouping_factor,
    )

    warnings.filterwarnings("ignore", category=FutureWarning)

    factor_name = COMBINED_COL
    df = engine.calc_many_df(expr_strs=expr_strs, names=alpha_names)
    df = apply_tradable_mask(df, tradable_mask)
    df = df.dropna(subset=alpha_names)

    w = np.asarray(ALPHA_WEIGHTS, dtype=float)
    df[factor_name] = 0.0
    for k, name in enumerate(alpha_names):
        df[factor_name] = df[factor_name] + w[k] * df[name]

    df = df[[factor_name]].copy()
    df_factor = pd.merge(df.reset_index(), df_returns, on=["datetime", "instrument"], how="left")
    rename_map = {"datetime": "date", "instrument": "symbol"}
    df_factor = df_factor.rename(columns=rename_map)
    df_factor["date"] = pd.to_datetime(df_factor["date"])

    if "returns_lag1" not in df_factor.columns:
        df_factor = cal_pct_lag(df_factor)

    df_factor = df_factor.groupby("date", group_keys=False).apply(
        lambda g: ext_out_3std(g.copy(), factor_name, process_inf=True)
    )
    df_factor_for_grouping = df_factor[np.isfinite(df_factor[factor_name])].copy()
    df_cuted, df_benchmark = grouping_factor(
        df=df_factor_for_grouping,  # type: ignore[arg-type]
        factor_name=factor_name,
        group_cnt=5,
    )

    alpha_fb = factor(name=factor_name, group_number=5)
    alpha_fb.set_backtest_parameters(
        period=1,
        predict_direction=1,
    )
    alpha_fb.start_backtest(df_cuted, df_benchmark)

    ic_info = alpha_fb.df_info2
    ic_mean = float(ic_info.loc["IC_mean", alpha_fb.name])
    rank_ic = float(ic_info.loc["Rank_IC", alpha_fb.name])
    t_stat = float(ic_info.loc["t统计量", alpha_fb.name])
    title = f"alphagen pool[{POOL_INDEX}] n={len(alpha_names)}"
    print(f"{title}\nIC_mean={ic_mean}, Rank_IC={rank_ic}, t统计量={t_stat}")
    print("selected_pool keys:", list(selected_pool.keys()))

    skip_plot = REQUIRE_IC_THRESHOLD_FOR_PLOT and not ((ic_mean > 0.02 or rank_ic > 0.02) and t_stat > 2)
    if skip_plot:
        print("未滿足 IC 門檻（任一>0.02 且 t>2），略過畫圖；可將 REQUIRE_IC_THRESHOLD_FOR_PLOT 設為 False")
    else:
        _orig_show = plt.show
        plt.show = lambda: None
        alpha_fb.draw_pct()
        plt.gcf().suptitle(title)
        plt.show = _orig_show
        plt.show()
        plt.close()
        _orig_show = plt.show
        plt.show = lambda: None
        alpha_fb.draw_ic(0)
        plt.gcf().suptitle(title + " — IC (normal)")
        plt.show = _orig_show
        plt.show()
        plt.close()
        _orig_show = plt.show
        plt.show = lambda: None
        alpha_fb.draw_ic(1)
        plt.gcf().suptitle(title + " — IC (rank)")
        plt.show = _orig_show
        plt.show()
        plt.close()
        _orig_show = plt.show
        plt.show = lambda: None
        alpha_fb.draw_ic_dacay()
        plt.gcf().suptitle(title + " — IC decay")
        plt.show = _orig_show
        plt.show()
        plt.close()
    return


if __name__ == "__main__":
    app.run()
