from qlib_source.scripts.dump_bin import DumpDataUpdateFromDataFrame
from src.config import QLIB_DATA_DIR_TW , TEJ_DATA_PATH
import os
import pandas as pd
from pathlib import Path

def main(date: str, is_dry_run: bool):
    # 檢核：若輸入日期已存在 calendars 內，則中止並報錯，避免重複寫入
    try:
        target_dt = pd.to_datetime(date, format="%Y%m%d").normalize()
    except Exception as e:
        raise ValueError(f"日期格式錯誤，需為 YYYYMMDD，收到: {date}") from e

    cal_path = Path(QLIB_DATA_DIR_TW) / "calendars" / "day.txt"
    if cal_path.exists():
        cal_dates = pd.read_csv(cal_path, header=None, names=["date"])["date"]
        cal_dates = pd.to_datetime(cal_dates, errors="coerce").dropna().dt.normalize()
        if (cal_dates == target_dt).any():
            raise ValueError(
                f"輸入日期 {date} 已存在於 calendar(day.txt) 內，請勿重複寫入。"
            )

    new_data_path = os.path.join(TEJ_DATA_PATH, date)
    df = pd.read_parquet(os.path.join(new_data_path, f"{date}.parquet"))
    df['instrument'] = df['instrument'].astype(str)
    if df['date'].dtype == 'int64':
        print('date is int64 , converting to datetime')
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df.to_parquet(os.path.join(new_data_path, f"{date}.parquet"), index=False)
    else:
        print('date is already datetime , no need to convert')
    include_fields = ','.join(df.columns)
    print('start dumping data to qlib')
    dumper = DumpDataUpdateFromDataFrame(
        df=df,
        qlib_dir=str(QLIB_DATA_DIR_TW),
        symbol_field_name='instrument',
        date_field_name='date',
        include_fields=include_fields,
        dry_run=is_dry_run
    )
    dumper.dump()
    print('end dumping data to qlib')
if __name__ == "__main__":
    date = input("請輸入日期(格式: YYYYMMDD): ")
    is_dry_run =  input("是否為 dry run? (y/n): ")
    if is_dry_run == 'y':
        is_dry_run = True
    else:
        is_dry_run = False
    main(date, is_dry_run)