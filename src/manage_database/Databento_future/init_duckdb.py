"""在 <data_root>/metadata/us.duckdb 建立查詢 data/us/raw 的 view (只放 view, 不存資料)。

用法:
    ~/miniconda3/envs/quant_research/bin/python init_duckdb.py [--data-root /home/newt/quant_project/data/us]

view 用本機絕對路徑; 資料從別台電腦複製過來後重跑一次即可。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

DEFAULT_DATA_ROOT = Path("/home/newt/quant_project/data/us")

# CME 交易日: 前一日 17:00 CT 開始的時段歸到下一個日曆日。
# 已知限制: 假日提前收盤的時段會標錯 (例如 Memorial Day 週日晚~週一中午, CME 歸週二, 此規則標週一)。
TRADE_DATE = "CAST(timezone('America/Chicago', ts_event) + INTERVAL 7 HOUR AS DATE) AS trade_date"

BAR_VIEWS = {
    "fut_bars": "futures/bars_1m",
    "fut_spreads": "futures/spread_bars_1m",
    "opt_bars": "options/bars_1m",
}
CONTRACT_VIEWS = {
    "fut_contracts": "futures/contracts",
    "fut_spread_contracts": "futures/spread_contracts",
    "opt_contracts": "options/contracts",
}


def _glob(data_root: Path, sub: str) -> str | None:
    d = data_root / "raw" / sub
    return f"{d}/**/*.parquet" if any(d.glob("**/*.parquet")) else None


def build(data_root: Path) -> list[str]:
    db = data_root / "metadata" / "us.duckdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    made = []
    for name, sub in BAR_VIEWS.items():
        con.execute(f"DROP VIEW IF EXISTS {name}")
        if (g := _glob(data_root, sub)) is None:
            print(f"  {name}: 沒有檔案, 略過")
            continue
        con.execute(f"CREATE VIEW {name} AS SELECT *, {TRADE_DATE} FROM read_parquet('{g}', hive_partitioning = true)")
        made.append(name)
    for name, sub in CONTRACT_VIEWS.items():
        con.execute(f"DROP VIEW IF EXISTS {name}")
        if (g := _glob(data_root, sub)) is None:
            print(f"  {name}: 沒有檔案, 略過")
            continue
        # 同一合約會出現在多個月份檔裡 -> 以 (instrument_id, raw_symbol) 去重, 留 ts_recv 最新的
        con.execute(f"""
            CREATE VIEW {name} AS
            SELECT * EXCLUDE (month) FROM read_parquet('{g}', hive_partitioning = true)
            QUALIFY row_number() OVER (PARTITION BY instrument_id, raw_symbol ORDER BY ts_recv DESC, month DESC) = 1
        """)
        made.append(name)
    con.execute("DROP VIEW IF EXISTS manifest")
    mdir = data_root / "metadata" / "manifest"
    if any(mdir.glob("**/*.parquet")):
        # root / month 已存在檔內, 不用 hive 分區
        con.execute(f"CREATE VIEW manifest AS SELECT * FROM read_parquet('{mdir}/**/*.parquet', hive_partitioning = false)")
        made.append("manifest")
    con.close()
    print(f"{db}: {made}")
    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    build(ap.parse_args().data_root)


if __name__ == "__main__":
    main()
