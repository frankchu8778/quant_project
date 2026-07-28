"""
從 DuckDB daily_data 拉出資料，轉成 qlib 格式寫入 RAM_PATH（預設 /dev/shm/qlib_ram）。

入口（會 sudo 掛載 ramdisk）:
  bash /home/newt/quant_project/rebuild_data/dump_qlib_to_ramdisk.sh

或在其他 Python 裡:
  from rebuild_data.dump_qlib_to_ramdisk import run_shell
  run_shell()
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pandas as pd
from qlib_source.scripts.dump_bin import DumpDataAllFromDataFrame

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
SHELL_SCRIPT = Path(__file__).resolve().with_name("dump_qlib_to_ramdisk.sh")
DUCKDB_PATH = PROJECT_ROOT / "duckdb" / "daily_data.duckdb"
RAM_PATH = Path(os.getenv("QLIB_RAM_PATH", "/dev/shm/qlib_ram"))
TABLE_NAME = "daily_data"

# 與舊 qlib 欄位對齊（factor notebook 用 $is_tradable / $is_disposed / $exchange）
RENAME_FOR_QLIB = {"market": "exchange"}


def clear_qlib_dirs(qlib_dir: Path) -> None:
    for name in ("calendars", "features", "instruments"):
        p = qlib_dir / name
        if p.exists():
            shutil.rmtree(p)


def load_daily_data(duckdb_path: Path = DUCKDB_PATH, table: str = TABLE_NAME) -> pd.DataFrame:
    print(f"從 DuckDB 讀取: {duckdb_path}::{table}")
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        df = con.execute(f"SELECT * FROM {table}").fetchdf()
    finally:
        con.close()
    print(f"rows={len(df):,} cols={df.shape[1]}")
    return df


def _date_col_to_yyyymmdd_float(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    return (dt.dt.year * 10000 + dt.dt.month * 100 + dt.dt.day).astype(float)


def prepare_for_qlib(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=RENAME_FOR_QLIB)

    if "untradable" in df.columns and "is_tradable" not in df.columns:
        df["is_tradable"] = (df["untradable"].fillna(1) == 0).astype(float)
    if "disposed_stock" in df.columns and "is_disposed" not in df.columns:
        df["is_disposed"] = df["disposed_stock"].fillna(0).astype(float)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize().dt.tz_localize(None)
    df["symbol"] = df["symbol"].astype(str)

    for col in df.columns:
        if col in ("symbol", "date"):
            continue
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = _date_col_to_yyyymmdd_float(df[col])
        elif not pd.api.types.is_float_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

    return df


def dump_to_qlib(df: pd.DataFrame, qlib_dir: Path) -> None:
    feature_cols = [c for c in df.columns if c not in ("symbol", "date")]
    include_fields = ",".join(feature_cols)
    print(f"dump → {qlib_dir}（features={len(feature_cols)}）")
    dumper = DumpDataAllFromDataFrame(
        df=df,
        qlib_dir=str(qlib_dir),
        symbol_field_name="symbol",
        date_field_name="date",
        include_fields=include_fields,
        freq="day",
    )
    dumper.dump()


def run_shell() -> None:
    """從任意 cwd 呼叫：掛載 ramdisk + dump（sudo 會要密碼）。"""
    subprocess.run(["bash", str(SHELL_SCRIPT)], check=True)


def main() -> None:
    ram_path = RAM_PATH
    if not ram_path.exists():
        raise SystemExit(f"找不到 {ram_path}，請執行 run_shell() 或 bash {SHELL_SCRIPT}")

    clear_qlib_dirs(ram_path)
    df = prepare_for_qlib(load_daily_data())
    dump_to_qlib(df, ram_path)

    cal = ram_path / "calendars" / "day.txt"
    inst = ram_path / "instruments" / "all.txt"
    assert cal.exists() and inst.exists(), "qlib dump 未產生 calendars/instruments"
    print(f"完成: {ram_path}")
    print(f"  calendars: {sum(1 for _ in cal.open())} days")
    print(f"  instruments: {sum(1 for _ in inst.open())} symbols")


if __name__ == "__main__":
    main()
