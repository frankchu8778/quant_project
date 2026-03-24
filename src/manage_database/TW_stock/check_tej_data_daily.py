import marimo

__generated_with = "0.20.4"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import pandas as pd 
    folder = "/mnt/c/Users/Ultra7/TEJ__data_daily"
    date = '20260324'
    return date, folder, pd


@app.cell
def _():
    # 手動審核是否通過（True 才允許進入提交流程）
    review_passed = True 
    # 是否寫出 parquet（True 才會執行 to_parquet）
    commit_changes = True
    # 是否移動原始資料夾到 processed（True 才會執行 shutil.move）
    move_processed_folders = True
    return


@app.cell
def _():
    from FinMind.data import DataLoader
    from src.config import FINMIND_TOKEN
    finmind_api = DataLoader()
    finmind_api.login_by_token(api_token=FINMIND_TOKEN)
    taiwan_stock_info_df = finmind_api.taiwan_stock_info()
    taiwan_stock_info_df.head()
    return finmind_api, taiwan_stock_info_df


@app.cell
def _(date, pd, taiwan_stock_info_df):
    # 將 date 轉換為 yyyy-mm-dd 格式
    date_yyyy_mm_dd = pd.to_datetime(date, format='%Y%m%d').strftime('%Y-%m-%d')

    # 先根據日期和市場篩選出資料（type 不是 'emerging'）
    filtered_tmp = taiwan_stock_info_df[
        (taiwan_stock_info_df['date'] == date_yyyy_mm_dd) &
        (taiwan_stock_info_df['type'] != 'emerging')
    ]

    # 再找出 industry_category 為 '創新板股票' 的 stock_id
    xinban_stock_ids = set(filtered_tmp.loc[filtered_tmp['industry_category'] == '創新板股票', 'stock_id'])

    # 最後排除 stock_id 為創新板股票的資料
    filtered_df = filtered_tmp[~filtered_tmp['stock_id'].isin(list(xinban_stock_ids))]
    filtered_df
    return date_yyyy_mm_dd, filtered_df


@app.cell
def _():
    # taiwan_stock_info_df[taiwan_stock_info_df['stock_id'] == '9103']
    return


@app.cell
def _():
    # filtered_df[filtered_df['stock_id']=='9103']
    return


@app.cell
def _():
    import os
    def unzip_and_delete_file(date_dir):
        import zipfile
        # 解壓縮檔案到與 zip 同一個目錄
        zip_file_path = os.path.join(f"{date_dir}.zip")

        if not  os.path.exists(zip_file_path):
            print(f"壓縮檔案 {zip_file_path} 不存在，無需解壓縮。")
            return

        with zipfile.ZipFile(zip_file_path, "r") as zf:
            zf.extractall(date_dir)
            print(f"已解壓縮 {zip_file_path} 到 {date_dir}")
        # 刪除 zip_file_path 指定的壓縮檔案
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)
            print(f"已刪除壓縮檔案 {zip_file_path}")
        else:
            print(f"壓縮檔案 {zip_file_path} 不存在，無需刪除。")

    return os, unzip_and_delete_file


@app.cell
def _(
    date,
    date_yyyy_mm_dd,
    filtered_df,
    finmind_api,
    folder,
    os,
    pd,
    unzip_and_delete_file,
):
    # 組合欲讀取的資料夾路徑
    OHLCV_dir = os.path.join(folder, 'OHLCV')
    OHLCV_date_dir = os.path.join(OHLCV_dir, date)
    unzip_and_delete_file(OHLCV_date_dir)
    # 取得資料夾內所有 .txt 檔案
    txt_files = [_f for _f in os.listdir(OHLCV_date_dir) if _f.endswith('.txt')]
    for fname in txt_files:
        file_path = os.path.join(OHLCV_date_dir, fname)
        try:
    # 若需個別讀取檔案內容，可如此處理：
            df = pd.read_csv(file_path, sep='\t', encoding='cp950', na_values=['na', 'NA'])
        except Exception:
            with open(file_path, 'r', encoding='utf-8') as _f:
                content = _f.read()
            df = content  # 嘗試以 pandas 讀取（假設為 tabular 格式）
    dividend_dir = os.path.join(folder, 'dividend')
    dividend_date_dir = os.path.join(dividend_dir, date)
    unzip_and_delete_file(dividend_date_dir)  # 若非標準表格檔，如需僅讀內容
    dividend_files = [_f for _f in os.listdir(dividend_date_dir) if _f.endswith('.txt')]
    for fname in dividend_files:
        file_path = os.path.join(dividend_date_dir, fname)  # 或直接存字串
        try:
            df_dividend = pd.read_csv(file_path, sep='\t', encoding='cp950', na_values=['na', 'NA'])
        except Exception:
            with open(file_path, 'r', encoding='utf-8') as _f:
                content = _f.read()
            df_dividend = content
    print("dividend rows:", 0 if isinstance(df_dividend, str) else len(df_dividend))
    process_div = False
    if not df_dividend.empty:
        print('合併dividend')
        process_div = True
        df = pd.merge(df, df_dividend, on=['證券代碼', '年月日'], how='left')
        df['除息(權)參考價(元)'] = df['除息(權)參考價(元)'].fillna(1)
        df['前一日收盤價'] = df['前一日收盤價'].fillna(1)  # 嘗試以 pandas 讀取（假設為 tabular 格式）
    df['證券代碼'] = df['證券代碼'].astype(str).str.split(' ').str[0]
    codemask = df['證券代碼'].str.match('^[1-9]\\d{3}$')
    df = df[codemask].copy()  # 若非標準表格檔，如需僅讀內容
    if '證券代碼' in filtered_df.columns:
        filtered_codes_raw = filtered_df['證券代碼'].astype(str)
    elif 'stock_id' in filtered_df.columns:
        filtered_codes_raw = filtered_df['stock_id'].astype(str)
    else:
        raise ValueError("filtered_df 缺少 '證券代碼' 或 'stock_id' 欄位，無法比對代碼集合")
    filtered_codemask = filtered_codes_raw.str.match('^[1-9]\\d{3}$')
    df_codes = set(df['證券代碼'].astype(str).unique())
    filtered_codes = set(filtered_codes_raw.loc[filtered_codemask].unique())
    only_in_filtered = sorted(filtered_codes - df_codes)
    if only_in_filtered:
        kept_codes = []
        for stk in only_in_filtered[:]:
            check_df = finmind_api.taiwan_stock_daily(
                stock_id=str(stk),
                start_date=date_yyyy_mm_dd,
                end_date=date_yyyy_mm_dd,
            )
            if check_df is None or getattr(check_df, 'empty', False):
                continue
            kept_codes.append(stk)
        only_in_filtered = sorted(set(kept_codes))
    if only_in_filtered:
        raise ValueError(
            "filtered_df 存在但 df 缺失的四碼股票代碼\n"
            f"只在 filtered_df 出現: {only_in_filtered[:20]}"
            f"{(' ...' if len(only_in_filtered) > 20 else '')}"
        )
    df['is_disposed'] = 0
    df.loc[df['處置股票(D)'] == 'D', 'is_disposed'] = 1
    # 可以選擇把多餘的欄位丟掉，只保留原本的 證券代碼 欄位
    # df.head()
    df.loc[df['全額交割(Y)'] == 'Y', 'is_disposed'] = 1  # 第二層檢核：若差異只存在於 filtered_df 且數量很小，嘗試從 finMind 複查
    return df, process_div


@app.cell
def _():
    # only_in_filtered
    return


@app.cell
def _():
    # for col in df.columns:
    #     print(col)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 同步產業/上市別對照表
    將當日資料中出現的 **上市別**、**TEJ子產業名**、**TEJ產業名** 與 `setting_files` 內的三個 master map 同步；若有新值則自動加入並寫入 JSON（與 `rebuilde_qlib.py` 的 `update_master_map` 邏輯一致）。
    """)
    return


@app.cell
def _(df, os):
    # 與 setting_files 內產業/上市別對照表同步：當日 df 若有新產業或新上市別則寫入對照表
    import json
    from pathlib import Path
    PROJECT_ROOT = Path(os.getenv('PROJECT_ROOT', '.'))
    if not (PROJECT_ROOT / 'setting_files').exists():
        PROJECT_ROOT = Path.cwd()
    setting_dir = PROJECT_ROOT / 'setting_files'

    def update_master_map_sync(df, col_name, mapping_file):
        """
        與 rebuilde_qlib.update_master_map 相同邏輯：讀取對照表，將 df 中該欄位出現的新值加入對照表並存檔。
        若有新值則分配下一個整數編號並寫入 JSON。
        """
        if col_name not in df.columns:
            return None
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as _f:
                master_map = json.load(_f)
        else:
            master_map = {}
        unique_values = df[col_name].fillna('Unknown').astype(str).unique()
        changed = False
        for val in unique_values:
            if val not in master_map:
                master_map[val] = len(master_map)
                changed = True
        if changed:
            mapping_file.parent.mkdir(parents=True, exist_ok=True)
            with open(mapping_file, 'w', encoding='utf-8') as _f:
                json.dump(master_map, _f, ensure_ascii=False, indent=4)
            print(f'已更新對照表: {mapping_file.name}')
        return master_map
    mapping_configs = {'exchange': ('上市別', setting_dir / 'exchange_master_map.json'), 'subindustry': ('TEJ子產業名', setting_dir / 'subindustry_master_map.json'), 'industry': ('TSE產業名', setting_dir / 'industry_master_map.json')}
    for (name, (_col, path)) in mapping_configs.items():
    # TEJ 原始欄位 → 對照表檔案（與 rebuilde_qlib 一致）
        master_map = update_master_map_sync(df, _col, path)
        if master_map is not None:
            df[name] = df[_col].fillna('Unknown').astype(str).map(master_map).astype(float)  # 將字串對應成代碼並寫入 df（與 rebuilde_qlib 一致，後續 dump 需要數值）
    return Path, json, setting_dir


@app.cell
def _(df, json, setting_dir):
    INDUSTRY_COL = 'TEJ產業名'
    SUBINDUSTRY_COL = 'TEJ子產業名'
    TEJ_MAPPING_PATH = setting_dir / 'tej_industry_to_subindustry.json'
    if INDUSTRY_COL not in df.columns or SUBINDUSTRY_COL not in df.columns:
        print(f' 跳過：df 缺少「{INDUSTRY_COL}」或「{SUBINDUSTRY_COL}」')
    else:
        sub = df[SUBINDUSTRY_COL].fillna('Unknown').astype(str)
        current_map = df.assign(_sub=sub).groupby(INDUSTRY_COL)['_sub'].apply(lambda s: sorted(s.unique().tolist())).to_dict()
        if TEJ_MAPPING_PATH.exists():
            with open(TEJ_MAPPING_PATH, 'r', encoding='utf-8') as _f:
                saved_map = json.load(_f)
        else:
            saved_map = {}
        changed_industries = []
        for (ind, sub_list) in current_map.items():
            if ind not in saved_map:
                saved_map[ind] = sub_list
                print(f' 新增產業映射: {ind} -> {len(sub_list)} 個子產業')
            else:
                old_set = set(saved_map[ind])
                new_set = set(sub_list)
                if old_set != new_set:
                    added = new_set - old_set
                    removed = old_set - new_set
                    changed_industries.append({'industry': ind, 'added': sorted(added), 'removed': sorted(removed), 'old': saved_map[ind], 'new': sub_list})
        if changed_industries:
            print('\n⚠️ 以下產業的「子產業」與既有映射不一致，請手動檢查並更新 JSON：')
            for _industry_change in changed_industries:
                print(f"  產業: {_industry_change['industry']}")
                if _industry_change['added']:
                    print(f"    本次新增子產業: {_industry_change['added']}")
                if _industry_change['removed']:
                    print(f"    本次消失子產業: {_industry_change['removed']}")
                print(f"    既有: {_industry_change['old']}")
                print(f"    當日: {_industry_change['new']}")
            print('  請手動編輯 setting_files/tej_industry_to_subindustry.json 後再執行本 cell 確認。')
        TEJ_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TEJ_MAPPING_PATH, 'w', encoding='utf-8') as _f:
            json.dump(saved_map, _f, ensure_ascii=False, indent=2)
        print(f' 已寫入 TEJ 產業↔子產業映射: {TEJ_MAPPING_PATH.name}（共 {len(saved_map)} 個產業）')
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 減資：第一天只存待處理，恢復交易日才寫入 df
    - **第一天**（`股票股利上市日` 不為空）：只計算恢復交易日與兩個復權因子，寫入 `setting_files/capital_reduction_pending.json`，**不寫回 df**（因停止交易期間無日資料）。
    - **恢復交易日**（股票股利上市日當天）：從 pending 讀出該批股票，將 `adj_factor_volume`（成交量調整因子）、`adj_factor_price`（價格調整因子）寫入當日 df，並自 pending 移除。
    - **公式**：成交量復權 = `1/(1 - 減資率%/100)`；價格調整 = `前日收盤價（元）/ 除權參考價（元）`。
    """)
    return


@app.cell
def _(Path, date, df, os, pd):
    # 減資：第一天只存待處理，恢復交易日（股票股利上市日）當天才寫入 df
    import numpy as np
    pending_path = Path(os.getenv('PROJECT_ROOT', '.')) / 'setting_files' / 'capital_reduction_pending.json'
    if not pending_path.parent.exists():
        pending_path = Path.cwd() / 'setting_files' / 'capital_reduction_pending.json'
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    mask_cap_red = df['股票股利上市日'].notna() & (df['減資率 %'].astype(float).fillna(0) != 0)
    today_dt = pd.to_datetime(date, format='%Y%m%d', errors='coerce')
    if mask_cap_red.any():
    # 僅當「股票股利上市日」有值且「減資率 %」不為 0 時才認定為減資
        next_td = pd.to_datetime(df.loc[mask_cap_red, '股票股利上市日'].astype(float).astype('Int64').astype(str), format='%Y%m%d', errors='coerce')
        rate = df.loc[mask_cap_red, '減資率 %'].fillna(0)
        denom = (1 - rate / 100).replace(0, np.nan)
    # --- 1) 本日為減資第一天：只計算並存入 pending，不寫回 df ---
        vol_factor = (1 / denom).values
        prev_close = df.loc[mask_cap_red, '前日收盤價（元）'].astype(float)
        ex_ref = df.loc[mask_cap_red, '除權參考價（元）'].astype(float).replace(0, np.nan)
        price_factor = (prev_close / ex_ref).values
        new_rows = pd.DataFrame({'instrument': df.loc[mask_cap_red, '證券代碼'].astype(str).values, 'next_trading_day': next_td.values, 'capital_reduction_volume_adj_factor': vol_factor, 'capital_reduction_price_adj_factor': price_factor})
        if pending_path.exists():
            try:
                pending = pd.read_json(pending_path, convert_dates=['next_trading_day'])
                pending = pd.concat([pending, new_rows], ignore_index=True)
            except (ValueError, pd.errors.EmptyDataError):
                pending = new_rows.copy()
        else:
            pending = new_rows.copy()
        pending.to_json(pending_path, orient='records', date_format='iso', indent=2, force_ascii=False)
        print('本日減資程序啟動第一天，已寫入待處理:', mask_cap_red.sum(), '筆')
    df['adj_factor_volume'] = 1
    df['adj_factor_price'] = 1
    if pending_path.exists():
        try:
            pending = pd.read_json(pending_path, convert_dates=['next_trading_day'])
        except (ValueError, pd.errors.EmptyDataError):
            pending = pd.DataFrame(columns=['instrument', 'next_trading_day', 'capital_reduction_volume_adj_factor', 'capital_reduction_price_adj_factor'])
        if not pending.empty:
            match = pending['next_trading_day'].dt.normalize() == today_dt.normalize()
            if match.any():
                to_apply = pending.loc[match]
                for (_, row) in to_apply.iterrows():
                    inst = str(row['instrument'])
    # --- 2) 每天檢查 capital_reduction_pending.json：若 next_trading_day 已到，將調整因子寫入 df ---
                    m = df['證券代碼'] == inst
                    if m.any():
                        df.loc[m, 'adj_factor_volume'] = row['capital_reduction_volume_adj_factor']
                        df.loc[m, 'adj_factor_price'] = row['capital_reduction_price_adj_factor']
                    else:
                        print('警告：pending 中 instrument', inst, '不在本日 df，略過寫入')
                pending = pending.loc[~match]
                pending.to_json(pending_path, orient='records', date_format='iso', indent=2, force_ascii=False)
                print('本日為恢復交易日，已寫入 adj_factor_volume/adj_factor_price 並自待處理移除:', to_apply['instrument'].tolist())  # 證券代碼在 df 為字串；JSON 讀回 instrument 可能為 int，需一致化再比對
    return


@app.cell
def _(df, process_div):
    if process_div:
        print('處理除息')
        df['adj_price_tmp' ] = df['前一日收盤價'] / df['除息(權)參考價(元)']
        df['adj_factor_price'] = df['adj_factor_price'] * df['adj_price_tmp']
        print(df[~(df['adj_factor_price']==1)]['證券代碼'].unique())
    return


@app.cell
def _():
    # row_2330 = df[df['證券代碼'] == '7716']

    # # row_2330 = df[df['instrument'] == '4174']
    # if not row_2330.empty:
    #     for col in row_2330.columns:
    #         print(f"{col}: {row_2330.iloc[0][col]}")
    # else:
    #     print("找不到證券代碼為 2330 的資料")
    return


@app.cell
def _(df):
    # 找到開盤價是na的資料
    volume_zero_rows = df[(df['成交量(千股)']==0) & (df['成交值(千元)']==0)]
    volume_zero_stock_id = volume_zero_rows['證券代碼'].unique().tolist()
    print("volume_zero_stock_id:", volume_zero_stock_id)
    return (volume_zero_stock_id,)


@app.cell
def _(volume_zero_stock_id):
    untradable_stock_id = ['3454']
    for stock_id in untradable_stock_id:
        if stock_id not in volume_zero_stock_id:
            raise ValueError(f"找不到 {stock_id} 的資料")
    print(len(untradable_stock_id))
    return (untradable_stock_id,)


@app.cell
def _():
    # df_4714 = df[df['instrument'] == '4174']
    # for col in df_4714.columns:
    #     print(f"{col}: {df_4714[col].values}")
    return


@app.cell
def _(df, untradable_stock_id):
    df['is_tradable'] = 1
    if '證券代碼' in df.columns:
        df.loc[df['證券代碼'].isin(untradable_stock_id), 'is_tradable'] = 0
    else:
        df.loc[df['instrument'].isin(untradable_stock_id), 'is_tradable'] = 0
    print(df['is_tradable'].value_counts())
    return


@app.cell
def _():
    rename_dict = {
        # --- 直接 rename（1 對 1）---
        '證券代碼': 'instrument',
        '年月日': 'date',
        '開盤價(元)': 'open',
        '最高價(元)': 'high',
        '最低價(元)': 'low',
        '收盤價(元)': 'close',
        '成交量(千股)': 'volume',
        '成交值(千元)': 'amount',
        '報酬率％': 'return_day',
        '週轉率％': 'turnover',
        '市值(百萬元)': 'market_value_million',
        '最後揭示買價': 'last_bid',
        '最後揭示賣價': 'last_ask',
        '報酬率-Ln': 'log_return_day',
        '市值比重％': 'market_value_pct',
        '成交值比重％': 'trading_value_pct',
        '成交筆數(筆)': 'numtrades',
        '本益比-TSE': 'pe_ratio_tse',
        '本益比-TEJ': 'pe_ratio_tej',
        '股價淨值比-TSE': 'pb_ratio_tse',
        '股價淨值比-TEJ': 'pb_ratio_tej',
        '股價營收比-TEJ': 'ps_Ratio_tej',
        '股利殖利率-TSE': 'div_yield_tse',
        '高低價差%': 'spread',
        # --- 需要額外處理（非單純 rename）---
        # '上市別'            → exchange        (需搭配變更市場歷史做時間序列 mapping)
        # 'TEJ子產業名'       → subindustry     (需搭配 TEJ子產業變更歷史做時間序列 mapping)
        # 'TSE產業名'         → industry        (需搭配 TSE產業變更歷史做時間序列 mapping)
        # adj_factor_price    → 由除權息資料計算得出
        # adj_factor_volume   → 由除權息資料計算得出
        # is_tradable         → 由全額交割、處置等多欄位綜合判斷
    }
    return (rename_dict,)


@app.cell
def _(date, df, rename_dict):
    save_path = f'/home/newt/quant_project/TEJ_processed_data/{date}'
    save_col = ['is_tradable', 'is_disposed', 'exchange', 'subindustry', 'industry', 'adj_factor_price', 'adj_factor_volume']
    save_col = save_col + list(rename_dict.values())
    df.rename(columns=rename_dict, inplace=True)
    df_1 = df[save_col]
    for _col in df_1.columns:
        if _col not in save_col:
            print(_col)
    return (df_1,)


@app.cell
def _(df_1):
    from datetime import datetime
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    df_1.head()
    return


@app.cell
def _(df_1):
    na_instruments = df_1[df_1.isna().any(axis=1)]['instrument'].tolist()
    print(len(na_instruments))
    print(na_instruments)
    return (na_instruments,)


@app.cell
def _(df_1, na_instruments):
    import random

    def na_instruments_na_cols_generator(df, instrument_list):
        """
        生成器：針對 instrument_list 中的每個 instrument，列出為 NA 的欄位
        """
        shuffled = instrument_list.copy()
        random.shuffle(shuffled)
        for instrument_id in shuffled:
            row = df[df['instrument'] == instrument_id]
            if row.empty:
                yield f'{instrument_id} 不存在於資料中'
            else:
                na_cols = row.columns[row.isna().any()].tolist()
                yield f'{instrument_id} 的 NA 欄位: {na_cols}'
    gen = na_instruments_na_cols_generator(df_1, na_instruments)
    # 每次運行此 cell 可獲得不同順序的結果
    ohlcv_cols = ['open', 'high', 'low', 'close', 'volume', 'adj_factor_price', 'adj_factor_volume', 'amount', 'market_value_million', 'is_tradable', 'is_disposed', 'exchange', 'subindustry', 'industry']
    ohlcv_not_na = df_1[ohlcv_cols].notna().all(axis=1)
    # # 範例：每次執行 next(gen) 可以檢查一個 instrument
    # # 若要一次看全部：
    # for result in gen:
    #     print(result)
    # 檢查是不是 ohlcv 欄位都不是 na
    # 若想顯示這些 rows
    # print(df[ohlcv_not_na])
    print(f'全部 ohlcv 欄位都不是 NA 的 row 數量: {ohlcv_not_na.sum()} / {len(df_1)}')
    return


@app.cell
def _():
    # import shutil
    # df.to_parquet(os.path.join(save_path, f"{date}.parquet"), index=False)


    # OHLCV_processed_folder = os.path.join(OHLCV_dir, "processed")
    # dividend_processed_folder = os.path.join(dividend_dir, "processed")
    # if not os.path.exists(OHLCV_processed_folder) or not os.path.exists(dividend_processed_folder):

    #     raise FileNotFoundError(f"目標資料夾{OHLCV_processed_folder} 或 {dividend_processed_folder} 不存在")
    # try:
    #     shutil.move(OHLCV_date_dir, OHLCV_processed_folder)
    #     print(f"{OHLCV_date_dir} 已移動到 {OHLCV_processed_folder}")
    # except Exception as e:
    #     print(f"移動過程中發生錯誤: {e}")
    # try:
    #     shutil.move(dividend_date_dir, dividend_processed_folder)
    #     print(f"{dividend_date_dir} 已移動到 {dividend_processed_folder}")
    # except Exception as e:
    #     print(f"移動過程中發生錯誤: {e}")
    return


@app.cell
def _(date, df_1, na_instruments):
    review_summary = {
        "date": date,
        "rows": int(len(df_1)),
        "instruments": int(df_1["instrument"].nunique()),
        "na_rows": int(len(na_instruments)),
    }
    manual_check_items = []
    if na_instruments:
        manual_check_items.append("存在 NA instruments，請先手工確認後再提交。")
    print("審核摘要:", review_summary)
    if manual_check_items:
        print("待確認事項:")
        for _check_item in manual_check_items:
            print("-", _check_item)
    return


app._unparsable_cell(
    r"""
    import shutil

    if not review_passed:
        print("review_passed=False：僅審核，不執行寫檔/移動。")
        return
    if manual_check_items:
        raise ValueError(f"仍有待確認項目：{manual_check_items}")
    if not commit_changes:
        print("commit_changes=False：已通過審核，但不執行寫檔/移動。")
        return

    os.makedirs(save_path, exist_ok=True)
    parquet_path = os.path.join(save_path, f"{date}.parquet")
    df_1.to_parquet(parquet_path, index=False)
    print(f"已寫入 {parquet_path}")

    if not move_processed_folders:
        print("move_processed_folders=False：略過資料夾移動。")
        return

    OHLCV_processed_folder = os.path.join(OHLCV_dir, "processed")
    dividend_processed_folder = os.path.join(dividend_dir, "processed")
    if not os.path.exists(OHLCV_processed_folder) or not os.path.exists(dividend_processed_folder):
        raise FileNotFoundError(
            f"目標資料夾{OHLCV_processed_folder} 或 {dividend_processed_folder} 不存在"
        )
    try:
        shutil.move(OHLCV_date_dir, OHLCV_processed_folder)
        print(f"{OHLCV_date_dir} 已移動到 {OHLCV_processed_folder}")
    except Exception as e:
        print(f"移動過程中發生錯誤: {e}")
    try:
        shutil.move(dividend_date_dir, dividend_processed_folder)
        print(f"{dividend_date_dir} 已移動到 {dividend_processed_folder}")
    except Exception as e:
        print(f"移動過程中發生錯誤: {e}")
    """,
    name="_"
)


if __name__ == "__main__":
    app.run()
