from datetime import datetime, timedelta
import shioaji as sj
import pandas as pd
import json
import time
from tqdm import tqdm
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.config import RAM_PATH ,TELEGRAM_BOT_TOKEN , TELEGRAM_CHAT_ID
from src.utils.RateLimiter import RateLimiter, retry_on_not_ready
import telebot 
from src.factor_engine.engine import FactorEngine

rate_limiter_shioaji = RateLimiter(max_requests=50, time_window=5)
@retry_on_not_ready(max_retries=3, delay=2, rate_limiter=rate_limiter_shioaji)
def fetch_kbars_with_retry_shioaji(api, code, start_date, end_date):
    """帶重試機制和速率限制的 kbars 請求"""    
    kbars = api.kbars(
        contract=api.Contracts.Stocks[code],
        start=start_date,
        end=end_date,
    )
    return kbars
MAX_WORKERS = 10  # 可依 API 延遲調整，以跑滿 48/5s 限速
MAX_USAGE = 0
#MAX_USAGE = 2000*1024*1024
def main(check_mode  , global_api ,start_date ,end_date , bot):
    try :
        engine = FactorEngine(
            qlib_data_path=RAM_PATH,
            instrument="all",
            start_time=start_date,
            end_time=end_date,
            device="cpu",               # 支援 "cpu" / "cuda:0" 字串或 torch.device
            max_backtrack_days=0,
            max_future_days=0,
            adjust_factor = 'back'
        )
        tej_df = engine.load_raw_df(['$open' , '$high' , '$low' , '$close' , '$volume' , '$is_tradable'])
        tej_df.reset_index(inplace=True)
        unique_dates = tej_df['datetime'].unique()
        unique_dates = [date.strftime("%Y-%m-%d") for date in unique_dates]

        
        for target_date in unique_dates:
            start_usage = global_api.usage().remaining_bytes
            target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
            next_date_obj = target_date_obj + timedelta(days=1)
            next_date_str = next_date_obj.strftime('%Y-%m-%d')

            result_df_list =[]
            fail_task = []
            no_trade_record = []

            shioaji_save_path = '/home/newt/quant_project/1min_data/shioaji'
            ohlcv_path = os.path.join(shioaji_save_path , f'{target_date}.parquet')
            fail_task_path = os.path.join(shioaji_save_path , f'{target_date}_fail.json')
            no_trade_json_path = os.path.join(shioaji_save_path, f'{target_date}_no_trade_record.json')

            instruments_copy = tej_df[tej_df['datetime']==target_date]['instrument'].unique().tolist()
            if os.path.exists(ohlcv_path) :
                print('已有檔案')
            else:
                if len(instruments_copy) > 0  :
                    def task(code):
                        """單檔請求，回傳 (code, df, status)：status 為 'ok' | 'empty' | 'fail'"""
                        try:
                            kbars = fetch_kbars_with_retry_shioaji(
                                global_api,
                                code,
                                target_date,
                                next_date_str,
                            )
                            df = pd.DataFrame({**kbars})
                            df.ts = pd.to_datetime(df.ts)
                            df['code'] = code
                            if df.empty:
                                return (code, df, 'empty')
                            return (code, df, 'ok')
                        except Exception:
                            return (code, None, 'fail')

                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {executor.submit(task, code): code for code in instruments_copy}
                        for future in tqdm(
                            as_completed(futures),
                            total=len(futures),
                            desc=f"日期: {target_date}",
                            unit="筆",
                            mininterval=1.0,
                            miniters=10,
                        ):
                            code, df, status = future.result()
                            if status == 'ok':
                                result_df_list.append(df)
                            elif status == 'empty':
                                no_trade_record.append(code)
                                if df is not None:
                                    result_df_list.append(df)
                            else:
                                fail_task.append(code)
                    df_result = pd.concat(result_df_list) if result_df_list else pd.DataFrame()
                    df_result.to_parquet(ohlcv_path)
            if len(fail_task) >0 :
                with open(fail_task_path, 'w', encoding='utf-8') as f:
                    json.dump(fail_task, f, ensure_ascii=False, indent=2)
            if len(no_trade_record) >0 :
                with open(no_trade_json_path, 'w', encoding='utf-8') as f:
                    json.dump(no_trade_record, f, ensure_ascii=False, indent=2)
            end_usage = global_api.usage().remaining_bytes
            # 用量 = 起始剩餘 - 結束剩餘（剩餘變少代表用掉了）
            current_usage = start_usage - end_usage
            remaining_bytes = end_usage
            if current_usage < 0:
                current_usage = 0  # API 若回傳變大（如重置），不計為負用量
            global MAX_USAGE
            MAX_USAGE = max(MAX_USAGE, current_usage)
            max_usage_limit = MAX_USAGE + (20 * 1024 * 1024)
            if remaining_bytes <= max_usage_limit:
                print('流量不足，程式結束')
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f'流量不足，程式結束' , )
                exit(0)

            if datetime.now().hour < 8 and datetime.now().hour > 2 :
                pass
            else:
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f'shioaji {target_date}完成 \n剩余流量: {remaining_bytes/1024/1024 :.2f} MB \n最大使用量: {MAX_USAGE/1024/1024 :.2f} MB' , )
    except Exception as e :
        global_api.logout()
        raise e
    
if __name__ == "__main__":
    from src.config import SHIOAJI_API_KEY , SHIOAJI_SECRET_KEY
    try :
        check_mode = input('檢查模式(y/n)')
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
        # 輸入 target_date，允許 yyyymmdd/self parsing
        start_date = input('請輸入 初始日期 (格式: yyyymmdd 或 yyyy-mm-dd): ')
        end_date = input('請輸入 結束日期 (格式: yyyymmdd 或 yyyy-mm-dd): ')
        if start_date.lower() == "self":
            start_date = "self"
        else:
            if '-' not in start_date and len(start_date) == 8:
                # 解析 yyyymmdd 格式
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            else:
                start_date = start_date
        if end_date.lower() == "self":
            end_date = "self"
        else:
            if '-' not in end_date and len(end_date) == 8:
                # 解析 yyyymmdd 格式
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
            else:
                end_date = end_date
        global_api = sj.Shioaji(simulation=True)
        global_api.login(
            api_key=SHIOAJI_API_KEY ,
            secret_key=SHIOAJI_SECRET_KEY ,
            fetch_contract=True
        )    
        if check_mode == 'y':
            main(check_mode = True, global_api = global_api, start_date = start_date, end_date = end_date, bot = bot)
        else:
            main(check_mode = False, global_api = global_api, start_date = start_date, end_date = end_date, bot = bot)

        global_api.logout()
    except Exception as e :

        global_api.logout()
        raise e
    finally:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f'程式結束' , )
    