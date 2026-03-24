"""
任務產生器 — 在主機上執行，從 qlib 資料檔產生每日下載任務。

每天產出一個 JSON 檔到 pi_task/ 資料夾：
    pi_task/2026-03-06.json  →  ["1101", "1102", ...]
    pi_task/2026-03-05.json  →  ["1101", "1102", ...]

產生前會檢查：
  1. 本地 parquet 是否已存在（已下載則跳過）｀
  2. 任務 JSON 是否已存在（避免重複產生）

用法：
    python -m src.manage_database.TW_stock.generate_task \\
        --start 2026-01-01 --end 2026-03-06

    # 自訂路徑
    python -m src.manage_database.TW_stock.generate_task \\
        --start 20260101 --end 20260306 \\
        --task-dir ./pi_task \\
        --data-dir /home/newt/quant_project/1min_data/finMind

產出的 pi_task/ 資料夾整個複製到樹莓派上，供 get_min_finmind_pi.py 使用。
"""

import argparse
import json
import os

from src.config import SSD_PATH, RAM_PATH

DEFAULT_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "1min_data", "finMind")
)
DEFAULT_TASK_DIR = "/dev/shm/pi_task"


def resolve_qlib_path():
    env = os.environ.get("QLIB_DATA_PATH")
    if env and os.path.isdir(os.path.join(env, "calendars")):
        return env
    if os.path.isdir(os.path.join(RAM_PATH, "calendars")):
        return RAM_PATH
    return str(SSD_PATH)


def read_calendar(qlib_path, start_date, end_date):
    cal_file = os.path.join(qlib_path, "calendars", "day.txt")
    dates = []
    with open(cal_file, "r") as f:
        for line in f:
            d = line.strip()
            if not d:
                continue
            if d < start_date or d > end_date:
                continue
            dates.append(d)
    dates.sort(reverse=True)
    return dates


def read_instruments(qlib_path, instrument="all"):
    inst_file = os.path.join(qlib_path, "instruments", f"{instrument}.txt")
    mapping = {}
    with open(inst_file, "r") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                mapping[parts[0]] = (parts[1], parts[2])
    return mapping


def get_codes_for_date(instruments, date_str):
    return [code for code, (s, e) in instruments.items() if s <= date_str <= e]


def normalize_date(s):
    s = s.strip()
    if "-" not in s and len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def main():
    parser = argparse.ArgumentParser(description="產生 FinMind 每日下載任務")
    parser.add_argument("--start", required=True, help="起始日期 (yyyymmdd 或 yyyy-mm-dd)")
    parser.add_argument("--end", required=True, help="結束日期 (yyyymmdd 或 yyyy-mm-dd)")
    parser.add_argument("--task-dir", default=DEFAULT_TASK_DIR, help=f"任務輸出資料夾 (預設: {DEFAULT_TASK_DIR})")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help=f"已下載 parquet 資料夾 (預設: {DEFAULT_DATA_DIR})")
    args = parser.parse_args()

    start_date = normalize_date(args.start)
    end_date = normalize_date(args.end)
    task_dir = os.path.normpath(args.task_dir)
    data_dir = os.path.normpath(args.data_dir)

    os.makedirs(task_dir, exist_ok=True)

    qlib_path = resolve_qlib_path()
    print(f"qlib 資料目錄: {qlib_path}")
    print(f"任務輸出目錄: {task_dir}")
    print(f"parquet 檢查目錄: {data_dir}")

    dates = read_calendar(qlib_path, start_date, end_date)
    instruments = read_instruments(qlib_path)
    print(f"日期範圍: {dates[-1] if dates else '?'} ~ {dates[0] if dates else '?'} ({len(dates)} 天)")
    print(f"股票總數: {len(instruments)}")
    print()

    created = 0
    skipped_parquet = 0
    skipped_task_exists = 0

    for d in dates:
        parquet_path = os.path.join(data_dir, f"{d}.parquet")
        task_path = os.path.join(task_dir, f"{d}.json")

        if os.path.exists(parquet_path):
            skipped_parquet += 1
            continue

        if os.path.exists(task_path):
            skipped_task_exists += 1
            continue

        codes = get_codes_for_date(instruments, d)
        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(codes, f, ensure_ascii=False)
        created += 1

    print(f"結果:")
    print(f"  新建任務: {created} 天")
    print(f"  跳過 (parquet 已存在): {skipped_parquet} 天")
    print(f"  跳過 (任務檔已存在): {skipped_task_exists} 天")

    total_tasks = len([f for f in os.listdir(task_dir) if f.endswith(".json")])
    print(f"  pi_task/ 內目前共 {total_tasks} 個待處理任務")


if __name__ == "__main__":
    main()
#python -m src.manage_database.TW_stock.generate_task --start 2021-11-01 --end 2021-12-31