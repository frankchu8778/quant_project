import json
import warnings
from datetime import date
from pathlib import Path

import polars as pl


_TIMELINE_CONFIGS = {
    "industry": {
        "initial": "首次掛牌TSE產業",
        "changes": [
            ("前三次TSE產業變更", "前三次TSE產業變更日"),
            ("前二次TSE產業變更", "前二次TSE產業變更日"),
            ("前一次TSE產業變更", "前一次TSE產業變更日"),
        ],
    },
    "subindustry": {
        "initial": "首次掛牌TEJ子產業",
        "changes": [
            ("前四次TEJ子產業變更", "前四次TEJ子產業變更日"),
            ("前三次TEJ子產業變更", "前三次TEJ子產業變更日"),
            ("前二次TEJ子產業變更", "前二次TEJ子產業變更日"),
            ("前一次TEJ子產業變更", "前一次TEJ子產業變更日"),
        ],
    },
}

INDUSTRY_MAP_REBUILD_NAME = "industry_master_map_rebuild.json"
SUBINDUSTRY_MAP_REBUILD_NAME = "subindustry_master_map_rebuild.json"


def _label_expr(column: str) -> pl.Expr:
    # 只去頭尾空白；不補 M、不壓內部空白，保留 TEJ 原字串
    return pl.col(column).cast(pl.String).str.strip_chars()


def _change_date(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .cast(pl.Int64, strict=False)
        .cast(pl.String)
        .str.strptime(pl.Date, "%Y%m%d", strict=False)
    )


def _build_events(
    company_info_df: pl.DataFrame,
    *,
    company_symbol_col: str,
    output_col: str,
) -> pl.DataFrame:
    config = _TIMELINE_CONFIGS[output_col]

    events = [
        company_info_df.select(
            pl.col(company_symbol_col).cast(pl.String).str.strip_chars().alias("symbol"),
            pl.lit(date.min).alias("effective_date"),
            _label_expr(config["initial"]).alias(output_col),
            pl.lit(0).alias("_event_order"),
        )
    ]
    for order, (value_col, date_col) in enumerate(config["changes"], start=1):
        events.append(
            company_info_df.select(
                pl.col(company_symbol_col).cast(pl.String).str.strip_chars().alias("symbol"),
                _change_date(date_col).alias("effective_date"),
                _label_expr(value_col).alias(output_col),
                pl.lit(order).alias("_event_order"),
            )
        )

    return (
        pl.concat(events)
        .filter(
            pl.col("symbol").is_not_null()
            & pl.col("effective_date").is_not_null()
            & pl.col(output_col).is_not_null()
            & (pl.col(output_col) != "")
        )
        .sort(["symbol", "effective_date", "_event_order"])
        .unique(["symbol", "effective_date"], keep="last", maintain_order=True)
        .select("symbol", "effective_date", output_col)
        .sort(["symbol", "effective_date"])
    )


def add_industry_timelines(
    ohlcv_df: pl.DataFrame,
    company_info_df: pl.DataFrame,
    *,
    symbol_col: str = "symbol",
    date_col: str = "date",
    company_symbol_col: str = "公司簡稱",
) -> pl.DataFrame:
    """把 TSE 產業與 TEJ 子產業歷史加到逐日 OHLCV。

    標籤保留 TEJ 原字串（只 strip 頭尾），不補 ``M``、不改內部空白。
    變更日當天起採用新分類；若當天無該股 OHLCV，從其後第一筆生效。
    """
    required_ohlcv = {symbol_col, date_col}
    required_info = {company_symbol_col}
    for config in _TIMELINE_CONFIGS.values():
        required_info.add(config["initial"])
        required_info.update(col for pair in config["changes"] for col in pair)

    missing_ohlcv = required_ohlcv - set(ohlcv_df.columns)
    missing_info = required_info - set(company_info_df.columns)
    if missing_ohlcv or missing_info:
        raise ValueError(
            f"缺少欄位：OHLCV={sorted(missing_ohlcv)}；"
            f"company_info={sorted(missing_info)}"
        )

    duplicated_symbols = (
        company_info_df.group_by(company_symbol_col)
        .len()
        .filter(pl.col("len") > 1)
    )
    if duplicated_symbols.height:
        raise ValueError(
            f"company_info 有 {duplicated_symbols.height} 個重複公司代碼，"
            "無法唯一建立分類時間軸"
        )

    result = (
        ohlcv_df.with_row_index("_original_order")
        .with_columns(
            pl.col(symbol_col).cast(pl.String).str.strip_chars().alias(symbol_col),
            pl.col(date_col).cast(pl.Date).alias(date_col),
        )
        .sort([symbol_col, date_col])
    )

    for output_col in _TIMELINE_CONFIGS:
        events = _build_events(
            company_info_df,
            company_symbol_col=company_symbol_col,
            output_col=output_col,
        )
        result = result.join_asof(
            events,
            left_on=date_col,
            right_on="effective_date",
            by_left=symbol_col,
            by_right="symbol",
            strategy="backward",
            check_sortedness=False,
        ).drop("effective_date")

    return result.sort("_original_order").drop("_original_order")


def _collect_labels(company_info_df: pl.DataFrame, output_col: str) -> list[str]:
    config = _TIMELINE_CONFIGS[output_col]
    cols = [config["initial"], *(value_col for value_col, _ in config["changes"])]
    labels: set[str] = set()
    for col in cols:
        for value in company_info_df.get_column(col).drop_nulls().to_list():
            text = str(value).strip()
            if text:
                labels.add(text)
    return sorted(labels)


def build_rebuild_master_maps(
    company_info_df: pl.DataFrame,
    setting_dir: str | Path,
) -> tuple[dict[str, int], dict[str, int]]:
    """用本次 company_info 的產業／子產業字串建新 map，寫入 ``*_rebuild.json``。"""
    setting_dir = Path(setting_dir)
    setting_dir.mkdir(parents=True, exist_ok=True)

    industry_map = {label: i for i, label in enumerate(_collect_labels(company_info_df, "industry"))}
    subindustry_map = {
        label: i for i, label in enumerate(_collect_labels(company_info_df, "subindustry"))
    }

    industry_path = setting_dir / INDUSTRY_MAP_REBUILD_NAME
    subindustry_path = setting_dir / SUBINDUSTRY_MAP_REBUILD_NAME
    industry_path.write_text(
        json.dumps(industry_map, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    subindustry_path.write_text(
        json.dumps(subindustry_map, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    return industry_map, subindustry_map


def load_rebuild_master_maps(setting_dir: str | Path) -> tuple[dict, dict]:
    setting_dir = Path(setting_dir)
    industry = json.loads((setting_dir / INDUSTRY_MAP_REBUILD_NAME).read_text(encoding="utf-8"))
    subindustry = json.loads(
        (setting_dir / SUBINDUSTRY_MAP_REBUILD_NAME).read_text(encoding="utf-8")
    )
    return industry, subindustry


def _encode_column(
    df: pl.DataFrame,
    column: str,
    master_map: dict,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"缺少欄位：{column}")

    mapping = {str(k): int(v) for k, v in master_map.items()}
    uniques = df.get_column(column).drop_nulls().unique().to_list()
    unmapped = [str(v) for v in uniques if str(v) not in mapping]
    if unmapped:
        preview = ", ".join(repr(x) for x in unmapped[:20])
        more = f" …共 {len(unmapped)} 個" if len(unmapped) > 20 else ""
        warnings.warn(
            f"{column} 有 {len(unmapped)} 個值不在 master map：{preview}{more}",
            stacklevel=2,
        )

    return df.with_columns(
        pl.col(column)
        .cast(pl.String)
        .replace_strict(mapping, default=None)
        .cast(pl.Int16)
        .alias(column)
    )


def encode_industry_columns(
    df: pl.DataFrame,
    industry_master_map: dict,
    subindustry_master_map: dict,
    *,
    industry_col: str = "industry",
    subindustry_col: str = "subindustry",
) -> pl.DataFrame:
    """用 master map 把 industry / subindustry 字串編成整數；未命中 → null 並 warnings。"""
    df = _encode_column(df, industry_col, industry_master_map)
    df = _encode_column(df, subindustry_col, subindustry_master_map)
    return df


if __name__ == "__main__":
    import tempfile

    bars = pl.DataFrame(
        {
            "symbol": ["A", "A", "A", "A"],
            "date": [
                date(2020, 1, 2),
                date(2020, 1, 3),
                date(2020, 1, 6),
                date(2020, 1, 7),
            ],
        }
    )
    info = pl.DataFrame(
        {
            "公司簡稱": ["A"],
            "首次掛牌TSE產業": ["M1100 水泥工業"],
            "前三次TSE產業變更": [None],
            "前三次TSE產業變更日": [None],
            "前二次TSE產業變更": [None],
            "前二次TSE產業變更日": [None],
            "前一次TSE產業變更": ["M1200 食品工業"],
            "前一次TSE產業變更日": [20200104],
            "首次掛牌TEJ子產業": ["11A   水泥製造"],
            "前四次TEJ子產業變更": [None],
            "前四次TEJ子產業變更日": [None],
            "前三次TEJ子產業變更": [None],
            "前三次TEJ子產業變更日": [None],
            "前二次TEJ子產業變更": [None],
            "前二次TEJ子產業變更日": [None],
            "前一次TEJ子產業變更": ["12A   罐頭加工"],
            "前一次TEJ子產業變更日": [20200104],
        }
    )
    out = add_industry_timelines(bars, info)
    assert out["industry"].to_list() == [
        "M1100 水泥工業",
        "M1100 水泥工業",
        "M1200 食品工業",
        "M1200 食品工業",
    ]
    assert out["subindustry"].to_list() == [
        "11A   水泥製造",
        "11A   水泥製造",
        "12A   罐頭加工",
        "12A   罐頭加工",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        ind_map, sub_map = build_rebuild_master_maps(info, tmp)
        assert ind_map["M1100 水泥工業"] == 0
        assert "11A   水泥製造" in sub_map
        encoded = encode_industry_columns(out, ind_map, sub_map)
        assert encoded["industry"].null_count() == 0
        assert encoded["subindustry"].null_count() == 0
    print("ok")
