from datetime import datetime, timedelta
import pandas as pd
import json
from tqdm import tqdm
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.config import RAM_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FINMIND_TOKEN
from src.utils.RateLimiter import RateLimiter, retry_on_not_ready
import telebot
from src.factor_engine.engine import FactorEngine
from FinMind.data import DataLoader
from src.config import FINMIND_TOKEN
from FinMind.data import DataLoader
from loguru import logger
import sys
logger.remove()  # 移除預設 handler
logger.add(sys.stderr, level="WARNING")


rate_limiter_finmind = RateLimiter(max_requests=100, time_window=60)


@retry_on_not_ready(max_retries=3, delay=2, rate_limiter=rate_limiter_finmind)
def fetch_data_finmind(api, code, date):
    """帶重試機制和速率限制的 kbars 請求"""
    return api.taiwan_stock_kbar(stock_id=code, date=date)




MAX_WORKERS = 22  # 可依 API 延遲調整，約 15~30 以跑滿 100/60s 限速


def main(finmind_api, start_date, end_date , n_days , bot ):
    try:
        engine = FactorEngine(
            qlib_data_path=RAM_PATH,
            instrument="all",
            start_time=start_date,
            end_time=end_date,
            device="cpu",
            max_backtrack_days=0,
            max_future_days=0,
            adjust_factor="back",
        )
        tej_df = engine.load_raw_df(
            ["$open", "$high", "$low", "$close", "$volume", "$is_tradable"]
        )
        tej_df.reset_index(inplace=True)
        unique_dates = tej_df["datetime"].unique()
        unique_dates = [date.strftime("%Y-%m-%d") for date in unique_dates]

        unique_dates = unique_dates[::-1] # 反轉日期，從最新到最舊

        
        finMind_save_path = "/home/newt/quant_project/1min_data/finMind"

        # 如果 n_days = 0，則設為全部 unique_dates；否則取前 n_days
        finish_days = 0
        for target_date in unique_dates:
            if finish_days >= n_days:
                break
            result_df_list_finMind = []
            fail_task_finMind = []
            no_trade_record_finMind = []

            ohlcv_path = os.path.join(finMind_save_path, f"{target_date}.parquet")
            fail_task_path = os.path.join(finMind_save_path, f"{target_date}_fail.json")
            no_trade_json_path = os.path.join(
                finMind_save_path, f"{target_date}_no_trade_record.json"
            )

            code_list = (
                tej_df[tej_df["datetime"] == target_date]["instrument"]
                .unique()
                .tolist()
            )

            if os.path.exists(ohlcv_path):
                print(f"已有檔案: {target_date} 跳過")
                continue
            else:
                finish_days += 1
                if len(code_list) > 0:
                    def task(code):
                        """單檔請求，回傳 (code, df, status)：status 為 'ok' | 'empty' | 'fail'"""
                        try:
                            df = fetch_data_finmind(finmind_api, code, target_date)
                            if df is None or df.empty:
                                return (code, df, "empty")
                            return (code, df, "ok")
                        except Exception:
                            return (code, None, "fail")

                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(task, code): code for code in code_list
                        }
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
                                result_df_list_finMind.append(df)
                            elif status == "empty":
                                no_trade_record_finMind.append([code])
                                if df is not None:
                                    result_df_list_finMind.append(df)
                            else:
                                fail_task_finMind.append(code)
                    df_result = (
                        pd.concat(result_df_list_finMind)
                        if result_df_list_finMind
                        else pd.DataFrame()
                    )
                    df_result.to_parquet(ohlcv_path)

            if len(fail_task_finMind) > 0:
                with open(fail_task_path, "w", encoding="utf-8") as f:
                    json.dump(fail_task_finMind, f, ensure_ascii=False, indent=2)
            if len(no_trade_record_finMind) > 0:
                with open(no_trade_json_path, "w", encoding="utf-8") as f:
                    json.dump(
                        no_trade_record_finMind, f, ensure_ascii=False, indent=2
                    )

            if datetime.now().hour >= 8 or datetime.now().hour <= 2:
                bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=f"finMind {target_date} 完成",
                )
    except Exception as e:
        raise e


if __name__ == "__main__":
    try:
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
        start_date = input("請輸入 初始日期 (格式: yyyymmdd 或 yyyy-mm-dd): ")
        end_date = input("請輸入 結束日期 (格式: yyyymmdd 或 yyyy-mm-dd): ")
        n_days = int(input("請輸入 抓取天數 : "))
        if start_date.lower() == "self":
            start_date = "self"
        else:
            if "-" not in start_date and len(start_date) == 8:
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        if end_date.lower() == "self":
            end_date = "self"
        else:
            if "-" not in end_date and len(end_date) == 8:
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

        finmind_api = DataLoader()
        finmind_api.login_by_token(api_token=FINMIND_TOKEN)
        main(finmind_api=finmind_api, start_date=start_date, end_date=end_date, n_days=n_days, bot = bot)
    except Exception as e:
        raise e
    finally:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f'程式結束')
