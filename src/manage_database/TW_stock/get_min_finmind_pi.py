"""
Raspberry Pi 版本 — 記憶體友善的 FinMind 分鐘線下載器。

掃描任務資料夾（由 generate_task.py 在主機產生），找出尚未完成的日期，逐天下載。

任務資料夾結構：
    pi_task/
        2026-03-06.json  →  ["1101", "1102", ...]
        2026-03-05.json  →  ["1101", "1102", ...]

判斷「已完成」：對應的 {save-path}/{date}.parquet 存在。

用法：
    python get_min_finmind_pi.py --task-dir ./pi_task [--n-days 5] [--save-path ./finmind_data]
"""

import argparse
import gc
import glob
import json
import os
import sys
import time
import threading
from datetime import datetime
from functools import wraps
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm
from FinMind.data import DataLoader
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

# ---------- 可調參數 ----------
MAX_WORKERS = 4
FLUSH_EVERY = 200

# ---------- config：Pi 上用環境變數或 .env ----------
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _init_telegram():
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        import telebot
        return telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    except ImportError:
        print("telebot 未安裝，跳過 Telegram 通知")
        return None


def _send(bot, text):
    if bot and TELEGRAM_CHAT_ID:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        except Exception as e:
            print(f"Telegram 發送失敗: {e}")


# ---------- Rate Limiter（內嵌輕量版，Pi 上不需 src.utils） ----------

class RateLimiter:
    def __init__(self, max_requests=100, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times = deque()
        self._lock = threading.Lock()

    def _clean_old(self, now):
        while self.request_times and now - self.request_times[0] >= self.time_window:
            self.request_times.popleft()

    def wait_if_needed(self):
        while True:
            with self._lock:
                now = time.time()
                self._clean_old(now)
                if len(self.request_times) < self.max_requests:
                    self.request_times.append(now)
                    return
                wait = self.request_times[0] + self.time_window - now
                if wait <= 0:
                    continue
            time.sleep(wait)


def retry_on_not_ready(max_retries=3, delay=2, rate_limiter=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    if rate_limiter is not None:
                        rate_limiter.wait_if_needed()
                    return func(*args, **kwargs)
                except Exception as e:
                    if "Not ready" in str(e) and attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
                    else:
                        raise
            return None
        return wrapper
    return decorator


rate_limiter_finmind = RateLimiter(max_requests=100, time_window=60)


@retry_on_not_ready(max_retries=3, delay=2, rate_limiter=rate_limiter_finmind)
def fetch_data_finmind(api, code, date):
    """帶重試機制和速率限制的 kbars 請求"""
    return api.taiwan_stock_kbar(stock_id=code, date=date)


# ---------- 批量 flush 工具 ----------

def _flush_batch(df_list, path):
    if not df_list:
        return
    pd.concat(df_list, copy=False).to_parquet(path)
    df_list.clear()


def _merge_temp_files(temp_files, dest_path):
    if not temp_files:
        pd.DataFrame().to_parquet(dest_path)
        return
    chunks = []
    for tf in temp_files:
        chunks.append(pd.read_parquet(tf))
    merged = pd.concat(chunks, copy=False)
    merged.to_parquet(dest_path)
    del merged, chunks
    gc.collect()
    for tf in temp_files:
        os.remove(tf)


# ---------- 掃描任務資料夾 ----------

def scan_pending_tasks(task_dir, save_path):
    """
    掃描 task_dir 內的 *.json，比對 save_path 內是否已有對應 parquet。
    回傳尚未完成的任務列表 [(date_str, task_file_path), ...]，日期由新到舊。
    """
    pattern = os.path.join(task_dir, "*.json")
    task_files = glob.glob(pattern)

    pending = []
    for tf in task_files:
        basename = os.path.basename(tf)
        date_str = basename.replace(".json", "")
        parquet_path = os.path.join(save_path, f"{date_str}.parquet")
        if not os.path.exists(parquet_path):
            pending.append((date_str, tf))

    pending.sort(key=lambda x: x[0], reverse=True)
    return pending


# ---------- 處理單天任務 ----------

def process_one_day(finmind_api, target_date, code_list, save_path, bot):
    ohlcv_path = os.path.join(save_path, f"{target_date}.parquet")
    fail_task_path = os.path.join(save_path, f"{target_date}_fail.json")
    no_trade_json_path = os.path.join(save_path, f"{target_date}_no_trade_record.json")

    if os.path.exists(ohlcv_path):
        print(f"已有檔案: {target_date} 跳過")
        return

    if not code_list:
        return

    fail_task_finMind = []
    no_trade_record_finMind = []
    result_buf = []
    temp_files = []
    batch_idx = 0

    def task_fn(code):
        try:
            df = fetch_data_finmind(finmind_api, code, target_date)
            if df is None or df.empty:
                return (code, df, "empty")
            return (code, df, "ok")
        except Exception:
            return (code, None, "fail")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(task_fn, code): code for code in code_list}
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc=f"日期: {target_date}",
            unit="筆",
            mininterval=1.0,
            miniters=10,
        ):
            code, df, status = future.result()
            if status == "ok":
                result_buf.append(df)
            elif status == "empty":
                no_trade_record_finMind.append([code])
                if df is not None:
                    result_buf.append(df)
            else:
                fail_task_finMind.append(code)

            if len(result_buf) >= FLUSH_EVERY:
                tmp = os.path.join(save_path, f".tmp_{target_date}_{batch_idx}.parquet")
                _flush_batch(result_buf, tmp)
                temp_files.append(tmp)
                batch_idx += 1
                gc.collect()

    if result_buf:
        tmp = os.path.join(save_path, f".tmp_{target_date}_{batch_idx}.parquet")
        _flush_batch(result_buf, tmp)
        temp_files.append(tmp)

    _merge_temp_files(temp_files, ohlcv_path)

    if fail_task_finMind:
        with open(fail_task_path, "w", encoding="utf-8") as f:
            json.dump(fail_task_finMind, f, ensure_ascii=False, indent=2)
    if no_trade_record_finMind:
        with open(no_trade_json_path, "w", encoding="utf-8") as f:
            json.dump(no_trade_record_finMind, f, ensure_ascii=False, indent=2)

    if datetime.now().hour >= 8 or datetime.now().hour <= 2:
        _send(bot, f"finMind {target_date} 完成")

    gc.collect()


# ---------- 主流程 ----------

def main(finmind_api, task_dir, n_days, save_path, bot):
    os.makedirs(save_path, exist_ok=True)

    pending = scan_pending_tasks(task_dir, save_path)
    total_pending = len(pending)

    if total_pending == 0:
        print("沒有待處理的任務")
        return

    to_process = min(n_days, total_pending)
    print(f"待處理: {total_pending} 天, 本次處理: {to_process} 天")

    for i, (date_str, task_file) in enumerate(pending):
        if i >= n_days:
            break

        with open(task_file, "r", encoding="utf-8") as f:
            code_list = json.load(f)

        print(f"\n[{i + 1}/{to_process}] {date_str} ({len(code_list)} 支股票)")
        process_one_day(finmind_api, date_str, code_list, save_path, bot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pi 版 FinMind 分鐘線下載器")
    parser.add_argument("--task-dir", required=True, help="任務資料夾路徑 (內含每日 JSON)")
    parser.add_argument("--n-days", type=int, default=999999, help="最多處理幾天 (預設: 全部)")
    parser.add_argument("--save-path", default="./finmind_data", help="儲存路徑 (預設: ./finmind_data)")
    args = parser.parse_args()

    bot = _init_telegram()
    try:
        finmind_api = DataLoader()
        finmind_api.login_by_token(api_token=FINMIND_TOKEN)

        main(
            finmind_api=finmind_api,
            task_dir=args.task_dir,
            n_days=args.n_days,
            save_path=args.save_path,
            bot=bot,
        )
    except Exception as e:
        raise e
    finally:
        _send(bot, "程式結束")
