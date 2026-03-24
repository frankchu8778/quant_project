import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "."))
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR_NAME", "data")

#台灣市場目錄
MARKET_TW_DIR = DATA_DIR / os.getenv("MARKET_TW", "tw")
RAW_DIR_TW = MARKET_TW_DIR / os.getenv("RAW_DIR_NAME", "raw")
METADATA_DIR_TW = MARKET_TW_DIR / os.getenv("METADATA_DIR_NAME", "metadata")
FACTORS_DIR_TW = MARKET_TW_DIR / os.getenv("FACTORS_DIR_NAME", "factors")
DB_PATH_TW = METADATA_DIR_TW / os.getenv("DB_NAME", "factor_catalog.db")

# OHLCV 資料目錄 (Qlib 相容格式)
OHLCV_DIR_TW = RAW_DIR_TW / "stock" / "OHLCV" # 分鐘數據位置
QLIB_DATA_DIR_TW = RAW_DIR_TW / "stock" / "daily_update" # 日頻數據位置

#TEJ 資料目錄
TEJ_DATA_PATH = PROJECT_ROOT / "TEJ_processed_data"

# FINMIND TOKEN
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")

#telegram 
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

#shioaji
SHIOAJI_API_KEY = os.getenv("SHIOAJI_API_KEY", "")
SHIOAJI_SECRET_KEY = os.getenv("SHIOAJI_SECRET_KEY", "")

# 基礎路徑設定
SSD_PATH = QLIB_DATA_DIR_TW
RAM_PATH = "/dev/shm/qlib_ram"


class RuntimeConfig:
    # 全域單例儲存區
    ACTIVE_MARKET = "all"
    ACTIVE_FILTER = None
    

def init_qlib_fast(market="all", filter_rule=None):
    import qlib
    from qlib.config import REG_TW
    from src.my_extensions.custom_ops import all_custom_ops
    from src.my_extensions.rename_ops import all_rename_ops
    # 1. 鎖定全域配置
    RuntimeConfig.ACTIVE_MARKET = market
    RuntimeConfig.ACTIVE_FILTER = filter_rule
    
    
    # 邏輯：如果 RAMDisk 裡有數據，就用 RAMDisk；否則用 SSD
    if os.path.exists(os.path.join(RAM_PATH, "calendars")):
        provider_uri = RAM_PATH
        print(f"🚀 偵測到記憶體數據，使用超高速模式: {provider_uri}")
    else:
        provider_uri = SSD_PATH
        print(f"⚠️ 未偵測到記憶體數據，回退至 SSD 模式: {provider_uri}")

    qlib.init(
        provider_uri=provider_uri,
        region=REG_TW,  # 或是 'tw' 取決於你的設定
        expression_cache=None,  # 既然都在 RAM 了，不需要再寫硬碟快取
        dataset_cache=None,
        custom_ops=all_custom_ops + all_rename_ops,
        n_jobs=os.cpu_count() // 2  # 128G 記憶體下，可以適度開啟並行
    )
    from qlib.data.cache import H
    H.init_kernel()
    H.create_shared_cache({})
