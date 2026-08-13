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
from pathlib import Path
from typing import Any, Iterable, Sequence

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


def _factor_section(entry: dict, *, with_exprs: bool) -> list[str]:
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

    if with_exprs and entry.get("exprs"):
        lines += ["<details><summary>合成表達式</summary>", ""]
        for w, e in zip(entry.get("weights") or [], entry["exprs"]):
            lines.append(f"- `{w:+.4f}` × `{e}`")
        lines += ["", "</details>", ""]
    return lines


def render(payload: dict, *, detail_top: int) -> str:
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
    for entry in ordered:
        lines += _factor_section(entry, with_exprs=True)
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
        default=0,
        help="逐因子明細只列前幾名；0 為全列",
    )
    args = p.parse_args()

    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{payload['experiment']}.md"
    out.write_text(render(payload, detail_top=args.detail_top), encoding="utf-8")
    print(f"Markdown：{out}")


if __name__ == "__main__":
    main()
