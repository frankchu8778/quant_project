"""把 `run_deep_eval_alphagen.py` 產出的 JSON 轉成一份可讀的 Markdown 報告。

JSON 是給程式吃的，欄位全、順序固定但難讀；這支腳本只做呈現，不重算任何數字，
所有值都直接取自 JSON。**不做任何四捨五入以外的加工**——報告與 JSON 對不上的話
就是這裡有 bug，不是回測有兩套口徑。

用法：

    python -m src.factor.report_deep_eval_md \\
        /dev/shm/deep_eval_alphagen/<實驗名>/deep_eval_hp5.json \\
        --out-dir src/factor/test_result/alphagen

輸出檔名固定為 `<實驗名>.md`（實驗名取自 JSON 的 experiment 欄位）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

#: 排名表要呈現的指標，以及表頭。gross 與 net 並列，不取代。
_RANK_COLS: tuple[tuple[str, str], ...] = (
    ("Rank_IC_mean", "Rank IC"),
    ("Rank_IC_ir", "ICIR"),
    ("Rank_IC_t", "t"),
    ("Rank_IC_nw_t", "NW t"),
    ("P_rank_ic_abs_gt", "有訊號比例"),
    ("monotonicity", "單調性"),
    ("long_short_mean", "多空/期"),
    ("net_long_short_mean", "扣成本後"),
)

#: 分組表的欄位。net_* 緊跟在對應的 gross 之後，方便一眼看出成本吃掉多少。
_GROUP_COLS: tuple[tuple[str, str], ...] = (
    ("label", "組別"),
    ("annual_return", "年化報酬"),
    ("net_annual_return", "扣成本"),
    ("annual_volatility", "年化波動"),
    ("sharpe", "夏普"),
    ("net_sharpe", "扣成本"),
    ("max_drawdown", "最大回撤"),
    ("net_max_drawdown", "扣成本"),
    ("monthly_win_rate", "月勝率"),
    ("avg_names", "平均檔數"),
    ("turnover", "名冊換手"),
    ("buy_weight", "買進權重"),
    ("cost_annual", "年化成本"),
)


def _fmt(x: Any, digits: int = 4) -> str:
    """數值一律固定小數位；null（JSON 對 NaN 的表示）印成 `-`。"""
    if x is None:
        return "-"
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def _config_section(payload: dict) -> list[str]:
    cfg = payload["config"]
    fee, tax = cfg.get("fee_rate"), cfg.get("tax_rate")
    slip = cfg.get("slippage_bps")
    lines = [
        "## 執行設定",
        "",
        f"- 實驗：`{payload['experiment']}`",
        f"- 產生時間：{payload['generated_at']}",
        f"- 持有期：{cfg['holding_period']} 交易日（統計只在換倉日上做，ADR-0003）",
        f"- 分組數：{cfg['group_count']}；一天至少 {cfg['min_names']} 檔",
        f"- 資料範圍：{cfg['data_range'][0]} ~ {cfg['data_range'][1]}",
        f"- 評估範圍：{cfg['eval_range'][0] or '不限'} ~ {cfg['eval_range'][1] or '不限'}",
        f"- 種子：{cfg['seed']}；因子數：{payload['n_factors']}",
    ]
    if fee is not None:
        buy = fee + (slip or 0.0) / 10_000.0
        sell = fee + (tax or 0.0) + (slip or 0.0) / 10_000.0
        lines += [
            f"- 交易成本：手續費 {fee:.5%}（買賣皆收）、證交稅 {tax:.3%}（僅賣出）、"
            f"滑點 {slip:.0f} bps（單邊，買賣各收）",
            f"  → 買一單位權重 {buy:.3%}、賣一單位 {sell:.3%}，來回 {buy + sell:.3%}",
        ]
    else:
        lines.append("- 交易成本：此份 JSON 產生於成本層之前，`net_*` 欄位不存在")
    return lines + [""]


def _ranking_section(payload: dict) -> list[str]:
    factors = payload["factors"]
    ordered = sorted(
        factors.values(), key=lambda e: e.get("rank") or len(factors) + 1
    )
    rows = []
    for entry in ordered:
        m = entry["metrics"]
        rows.append(
            [
                str(entry.get("rank") or "-"),
                f"`{entry['name']}`",
                *[_fmt(m.get(key)) for key, _ in _RANK_COLS],
                _fmt(entry["coverage"]["coverage"], 3),
                "-" if m.get("n_days") is None else str(int(m["n_days"])),
            ]
        )
    return [
        "## 因子排名",
        "",
        "依 |Rank IC| 由大到小。「多空/期」是每一次換倉的平均多空價差，"
        "「扣成本後」是同一條序列逐次換倉扣掉交易成本再平均。",
        "",
        *_table(
            ["#", "因子", *[h for _, h in _RANK_COLS], "覆蓋率", "換倉次數"], rows
        ),
        "",
    ]


def _dates(rows: Sequence[dict]) -> list[date]:
    return [date.fromisoformat(r["date"]) for r in rows]


def _draw_ic(rows: Sequence[dict], key: str, title: str, ax) -> None:
    """單日 IC 長條 + 右軸累積 IC 折線（panda_factor 的 IC 時序圖就是這兩層）。"""
    xs = _dates(rows)
    ys = [r.get(key) or 0.0 for r in rows]
    ax.bar(xs, ys, width=2.0, color="#4878a8", label="單期")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_ylabel(title)
    cum, total = [], 0.0
    for y in ys:
        total += y
        cum.append(total)
    twin = ax.twinx()
    twin.plot(xs, cum, color="#c44e52", linewidth=1.5, label="累積")
    twin.set_ylabel("累積")
    ax.set_title(f"{title} 時序（左：單期，右：累積）")


def _draw_groups(entry: dict, ax) -> None:
    """分組累積收益 + 多空價差。與 group_stats 同源，只是把序列攤開來看。"""
    rows = entry["group_returns_daily"]
    labels = sorted({r["group"] for r in rows})
    for g in labels:
        sub = sorted((r for r in rows if r["group"] == g), key=lambda r: r["date"])
        cum, total = [], 1.0
        for r in sub:
            total *= 1.0 + (r.get("ret") or 0.0)
            cum.append(total - 1.0)
        ax.plot(_dates(sub), cum, label=f"group {g}")
    ls = sorted(entry.get("long_short_daily") or [], key=lambda r: r["date"])
    if ls:
        cum, total = [], 1.0
        for r in ls:
            total *= 1.0 + (r.get("ret") or 0.0)
            cum.append(total - 1.0)
        ax.plot(_dates(ls), cum, color="black", linewidth=2.0, label="多空價差")
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.legend(fontsize=8)
    ax.set_title("分組累積收益（未扣成本）")


def _draw_decay(entry: dict, ax) -> None:
    rows = sorted(entry.get("decay") or [], key=lambda d: d["lag"])
    ax.bar([d["lag"] for d in rows], [d.get("rank_ic") or 0.0 for d in rows],
           color="#4878a8")
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel("lag（交易日）")
    ax.set_ylabel("平均 Rank IC")
    ax.set_title("IC 衰減")


def save_charts(entry: dict, out_dir: Path, subdir: str) -> list[tuple[str, str]]:
    """畫圖並存檔，回傳 [(小標, 相對於 md 的路徑)]。缺序列就少畫幾張，不報錯。

    圖只從 JSON 的序列畫，不重跑回測——報告與 JSON 對不上就是這裡有 bug。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from src.factor.components.deep_eval import use_cjk_font

    if not use_cjk_font():
        print("[note] 找不到中文字型，圖上的中文會顯示成方框（數據不受影響）")

    plan: list[tuple[str, str, Any]] = []
    if entry.get("group_returns_daily"):
        plan.append(("分組收益", "group_returns", _draw_groups))
    if entry.get("ic_daily"):
        plan += [
            ("IC 時序（normal）", "ic", lambda e, ax: _draw_ic(e["ic_daily"], "ic", "IC", ax)),
            ("IC 時序（rank）", "rank_ic",
             lambda e, ax: _draw_ic(e["ic_daily"], "rank_ic", "Rank IC", ax)),
        ]
    if entry.get("decay"):
        plan.append(("IC 衰減", "ic_decay", _draw_decay))

    if not plan:
        return []
    chart_dir = out_dir / subdir
    chart_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for title, stem, draw in plan:
        fig, ax = plt.subplots(figsize=(11, 4))
        draw(entry, ax)
        fig.tight_layout()
        fig.savefig(chart_dir / f"{stem}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        out.append((title, f"{subdir}/{stem}.png"))
    return out


def _factor_section(entry: dict, *, with_exprs: bool, charts: Sequence[tuple[str, str]] = ()) -> list[str]:
    m = entry["metrics"]
    lines = [
        f"### {entry.get('rank') or '-'}. `{entry['name']}`",
        "",
        f"- Rank IC {_fmt(m.get('Rank_IC_mean'))}（ICIR {_fmt(m.get('Rank_IC_ir'))}，"
        f"t {_fmt(m.get('Rank_IC_t'))}，NW t {_fmt(m.get('Rank_IC_nw_t'))}）",
        f"- IC {_fmt(m.get('IC_mean'))}（t {_fmt(m.get('IC_t'))}）",
        f"- 多空每期 {_fmt(m.get('long_short_mean'))}，"
        f"扣成本後 {_fmt(m.get('net_long_short_mean'))}",
        f"- 覆蓋率 {_fmt(entry['coverage']['coverage'], 3)}"
        f"（{entry['coverage']['evaluated_rows']:,} 列進入統計）"
        f"；提前出清 {entry['early_exit_count']} 筆；整天丟棄 {entry['dropped_days']} 天",
        "",
    ]

    rows = [[_fmt(row.get(key)) for key, _ in _GROUP_COLS] for row in entry["group_stats"]]
    lines += _table([h for _, h in _GROUP_COLS], rows) + [""]

    decay = entry.get("decay") or []
    if decay:
        head = decay[: min(11, len(decay))]
        lines += [
            "IC 衰減（lag 0 起）：",
            "",
            *_table(
                ["lag", *[str(d["lag"]) for d in head]],
                [["rank_ic", *[_fmt(d["rank_ic"]) for d in head]]],
            ),
            "",
        ]

    for title, rel in charts:
        lines += [f"**{title}**", "", f"![{title}]({rel})", ""]

    if with_exprs and entry.get("exprs"):
        lines += ["<details><summary>合成表達式</summary>", ""]
        for w, e in zip(entry.get("weights") or [], entry["exprs"]):
            lines.append(f"- `{w:+.4f}` × `{e}`")
        lines += ["", "</details>", ""]
    return lines


def render(
    payload: dict,
    *,
    detail_top: int,
    charts: Sequence[tuple[str, str]] = (),
) -> str:
    factors = payload["factors"]
    ordered = sorted(
        factors.values(), key=lambda e: e.get("rank") or len(factors) + 1
    )
    lines = [
        f"# 深度回測：{payload['experiment']}",
        "",
        "由 `src/factor/run_deep_eval_alphagen.py` 產出的 JSON 轉寫，數字未經二次計算。",
        "口徑見 `src/factor/components/usage.md`。",
        "",
        *_config_section(payload),
        *_ranking_section(payload),
        "## 逐因子明細",
        "",
    ]
    if detail_top > 0:
        ordered = ordered[:detail_top]
        lines += [f"只列前 {detail_top} 名。", ""]
    for i, entry in enumerate(ordered):
        # 圖只畫排名第一的那個因子，所以只掛在第一節上
        lines += _factor_section(entry, with_exprs=True, charts=charts if i == 0 else ())
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("json_path", type=Path, help="deep_eval_hp*.json 的路徑")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("src/factor/test_result/alphagen"),
        help="輸出目錄；檔名固定為 <實驗名>.md",
    )
    p.add_argument(
        "--detail-top",
        type=int,
        default=1,
        help="逐因子明細只列前幾名；0 為全列",
    )
    p.add_argument(
        "--no-charts",
        action="store_true",
        help="不畫圖（JSON 沒帶逐日序列時本來就畫不出來，這只是明確關掉）",
    )
    args = p.parse_args()

    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    best = min(
        payload["factors"].values(),
        key=lambda e: e.get("rank") or len(payload["factors"]) + 1,
    )
    charts: list[tuple[str, str]] = []
    if not args.no_charts:
        charts = save_charts(best, args.out_dir, f"{payload['experiment']}_charts")
        if not charts:
            print("[note] JSON 沒有逐日序列，跳過畫圖；重跑時加 --series-top 1")

    out = args.out_dir / f"{payload['experiment']}.md"
    out.write_text(
        render(payload, detail_top=args.detail_top, charts=charts), encoding="utf-8"
    )
    print(f"Markdown：{out}")
    for _, rel in charts:
        print(f"  圖：{args.out_dir / rel}")


if __name__ == "__main__":
    main()
