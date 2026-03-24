# 重建 qlib 數據庫
import os
import pandas as pd
import json
from pathlib import Path
from qlib_source.scripts.dump_bin import DumpDataAllFromDataFrame
from src.config import TEJ_DATA_PATH, QLIB_DATA_DIR_TW

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "."))
"""
重建 qlib 數據庫
重建20260123以前的數據
"""
def update_master_map(df, col_name, mapping_file):
    """
    讀取、更新並儲存對照表，並回傳映射後的 Series
    """
    # 1. 載入現有對照表
    if mapping_file.exists():
        with open(mapping_file, "r", encoding="utf-8") as f:
            master_map = json.load(f)
    else:
        master_map = {}

    # 2. 獲取該欄位所有不重複的值 (處理 NaN)
    unique_values = df[col_name].fillna('Unknown').unique()

    # 3. 更新對照表 (如果新值不在對照表內，則追加編號)
    changed = False
    for val in unique_values:
        if val not in master_map:
            # 分配下一個整數編號
            master_map[val] = len(master_map)
            changed = True

    # 4. 如果有更新，存回 JSON
    if changed:
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(master_map, f, ensure_ascii=False, indent=4)
        print(f"已更新對照表: {mapping_file}")

    # 5. 回傳轉換後的數值序列 (float64 以符合 Qlib 需求)
    return df[col_name].fillna('Unknown').map(master_map).astype(float)

def main():
    # --- 1. 資料讀取 ---
    df_list = []
    print(f"正在從 {TEJ_DATA_PATH} 讀取數據...")
    before_20260123_folder = os.path.join(TEJ_DATA_PATH, 'before_20260123')
    for date_file in os.listdir(before_20260123_folder):
        if date_file.endswith('.parquet'):
            df_list.append(pd.read_parquet(os.path.join(before_20260123_folder , date_file)))

    
    if not df_list:
        print("沒有找到數據檔案。")
        return
        
    df = pd.concat(df_list)
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.normalize().dt.tz_localize(None)

    # --- 2. 處理三個欄位的 Mapping ---
    setting_dir = PROJECT_ROOT / "setting_files"
    mapping_configs = {
        'exchange': setting_dir / "exchange_master_map.json",
        'subindustry': setting_dir / "subindustry_master_map.json",
        'industry': setting_dir / "industry_master_map.json"
    }

    for col, map_file in mapping_configs.items():
        # 建立新的代碼欄位 (例如 exchange_code)
        df[f'{col}'] = update_master_map(df, col, map_file)

    # --- 3. 準備 Qlib Dump 欄位 ---
    # 找出所有數值型態欄位，並排除掉不屬於 Feature 的欄位
    # 關鍵：排除原始字串欄位 ('exchange', 'subindustry', 'industry')


    include_fields = ','.join(df.columns)
    # --- 4. 執行 Qlib Dump ---
    dumper = DumpDataAllFromDataFrame(
        df=df,
        qlib_dir=str(QLIB_DATA_DIR_TW),
        symbol_field_name='instrument',
        date_field_name='date',
        include_fields=include_fields,
        freq='day'
    )

    dumper.dump()
    print("Qlib 數據庫重建完成。")

if __name__ == '__main__':
    main()