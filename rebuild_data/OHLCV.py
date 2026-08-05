# TEJ Daily_Unadjusted_Price：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wprcd.html
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位 — 順序在完整 SCHEMA 最前
OHLCV_KEEP_SCHEMA = {
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '開盤價(元)': ('open', 'float64'),
    '最高價(元)': ('high', 'float64'),
    '最低價(元)': ('low', 'float64'),
    '收盤價(元)': ('close', 'float64'),
    '成交量(千股)': ('volume', 'float64'),
    '成交值(千元)': ('amount', 'float64'),
    '報酬率％': ('return_day', 'float64'),
    '週轉率％': ('turnover', 'float64'),
    '市值(百萬元)': ('market_value_million', 'float64'),
    '報酬率-Ln': ('log_return_day', 'float64'),
    '成交筆數(筆)': ('numtrades', 'float64'),
    '漲跌停': ('limit_status', 'string'),
    '高低價差%': ('spread', 'float64'),
    '次日開盤參考價': ('next_open_ref', 'float64'),
    '次日漲停價': ('next_limit_up', 'float64'),
    '次日跌停價': ('next_limit_down', 'float64'),
    '注意股票(A)': ('attention_stock', 'string'),
    '處置股票(D)': ('disposed_stock', 'string'),
    '全額交割(Y)': ('full_delivery', 'string'),
    '市場別': ('market', 'string'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
_OHLCV_REST_SCHEMA = {
    '股價漲跌(元)': ('price_change', 'float64'),
    '市值比重％': ('market_value_pct', 'float64'),
    '成交值比重％': ('trading_value_pct', 'float64'),
    '股價營收比-TEJ': ('ps_ratio_tej', 'float64'),
    '股利殖利率-TSE': ('div_yield_tse', 'float64'),
    '現金股利率': ('cash_div_yield', 'float64'),
    '本益比-TSE': ('pe_ratio_tse', 'float64'),
    '本益比-TEJ': ('pe_ratio_tej', 'float64'),
    '股價淨值比-TSE': ('pb_ratio_tse', 'float64'),
    '股價淨值比-TEJ': ('pb_ratio_tej', 'float64'),
    '流通在外股數(千股)': ('shares_outstanding_thousand', 'float64'),
    '最後揭示買價': ('last_bid', 'float64'),
    '最後揭示賣價': ('last_ask', 'float64'),
}

# 完整 schema：保留欄位在上
OHLCV_SCHEMA = {
    **OHLCV_KEEP_SCHEMA,
    **_OHLCV_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in OHLCV_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in OHLCV_SCHEMA.items()}

db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wprcd.html'

keep_col = [en for en, _ in OHLCV_KEEP_SCHEMA.values()]


"""
備註:
    7769 20241101沒有 return_day / log_return_day 因為那是上興櫃第一天
    有318筆 open是空的是上市當天 但都是REG市場 暫不處理
    price change 拿掉 只保留報酬率 不保留絕對數值差距
"""


def parse_tej_date(series):
    
    """TEJ 年月日為 YYYYMMDD 數值（如 20150601.0）→ datetime64[ns]。"""
    import pandas as pd

    return pd.to_datetime(
        series.astype('Int64').astype(str),
        format=TEJ_DATE_FORMAT,
        errors='coerce',
    )


def fill_open_na_with_prev_close(df):
    """依 date 排序、以 symbol 分組，用前一交易日 close 填充 open 的 NA。"""
    import polars as pl

    return (
        df.sort(['symbol', 'date'])
        .with_columns(
            pl.when(pl.col('open').is_null())
            .then(pl.col('close').shift(1).over('symbol'))
            .otherwise(pl.col('open'))
            .alias('open')
        )
    )


def encode_limit_status(df):
    """漲停 '+' → 1，跌停 '-' → -1，缺失 → 0。"""
    import polars as pl

    return df.with_columns(
        pl.when(pl.col('limit_status') == '+')
        .then(1)
        .when(pl.col('limit_status') == '-')
        .then(-1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias('limit_status')
    )


def encode_special_stock_flags(df):
    """注意(A)／處置(D)／全額交割(Y) → 1，缺失 → 0。"""
    import polars as pl

    return df.with_columns(
        pl.when(pl.col(col) == mark)
        .then(1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias(col)
        for col, mark in (
            ('attention_stock', 'A'),
            ('disposed_stock', 'D'),
            ('full_delivery', 'Y'),
        )
    )


def load_exchange_master_map(setting_dir=None):
    """讀 ``setting_files/exchange_master_map.json``。"""
    import json
    from pathlib import Path

    setting_dir = Path(setting_dir) if setting_dir is not None else (
        Path(__file__).resolve().parents[1] / 'setting_files'
    )
    return json.loads(
        (setting_dir / 'exchange_master_map.json').read_text(encoding='utf-8')
    )


def encode_market(df, exchange_map=None, setting_dir=None):
    """market 字串 → Int8（未列在 map → null）。"""
    import polars as pl

    if exchange_map is None:
        exchange_map = load_exchange_master_map(setting_dir)
    return df.with_columns(
        pl.col('market').replace_strict(exchange_map, default=None).cast(pl.Int8)
    )


def encode_ohlcv_codes(df, *, exchange_map=None, setting_dir=None):
    """統一編碼入口：漲跌停／特殊股標記／市場 → DB 整數碼。

    每日增量用此函式（不重算 spread，避免缺前一日 next_open_ref）。
    """
    df = encode_limit_status(df)
    df = encode_special_stock_flags(df)
    df = encode_market(df, exchange_map=exchange_map, setting_dir=setting_dir)
    return df


def process_and_validate_spread(df):
    """高低價差% = (high - low) / 前一日 next_open_ref * 100。

    無前一日 next_open_ref（或缺／≤0）→ NA。
    與 TEJ 原 spread 以 round(2) 比對；不一致列回傳於 mismatch_df。
    回傳 (df, mismatch_df)：df.spread 覆寫為自算值。
    """
    import polars as pl

    out = (
        df.sort(['symbol', 'date'])
        .with_columns(
            pl.col('next_open_ref').shift(1).over('symbol').alias('_prev_next_open_ref'),
            pl.col('spread').alias('_spread_tej'),
        )
        .with_columns(
            pl.when(
                pl.col('_prev_next_open_ref').is_null()
                | (pl.col('_prev_next_open_ref') <= 0)
            )
            .then(None)
            .otherwise(
                (pl.col('high') - pl.col('low'))
                / pl.col('_prev_next_open_ref')
                * 100
            )
            .alias('spread')
        )
    )
    mismatch = (
        out.filter(
            # round(2) 後不相等；ne_missing 會把單邊 null 也算差異
            pl.col('_spread_tej').round(2).ne_missing(pl.col('spread').round(2))
        )
        .select(
            'symbol',
            'date',
            'high',
            'low',
            pl.col('_prev_next_open_ref').alias('prev_next_open_ref'),
            pl.col('_spread_tej').alias('spread_tej'),
            pl.col('spread').alias('spread_calc'),
        )
    )
    return out.drop(['_prev_next_open_ref', '_spread_tej']), mismatch


def process_OHLCV_df(df):
    """OHLCV 處理入口：填 open NA → encode 漲跌停／特殊標記 → 重算／驗證 spread → 保留 keep_col。"""
    df = fill_open_na_with_prev_close(df)
    df = encode_limit_status(df)
    df = encode_special_stock_flags(df)
    df, _ = process_and_validate_spread(df)
    return df.select(keep_col)


if __name__ == '__main__':
    import pandas as pd
    import polars as pl

    assert len(OHLCV_SCHEMA) == 35
    assert len(OHLCV_KEEP_SCHEMA) == 22
    assert set(RENAME_MAP) == set(OHLCV_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in OHLCV_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert OHLCV_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))
    assert keep_col == [en for en, _ in OHLCV_KEEP_SCHEMA.values()]
    assert list(OHLCV_SCHEMA)[: len(OHLCV_KEEP_SCHEMA)] == list(OHLCV_KEEP_SCHEMA)
    parsed = parse_tej_date(pd.Series([20150601.0, 20150602.0]))
    assert pd.api.types.is_datetime64_any_dtype(parsed)
    assert str(parsed.iloc[0].date()) == '2015-06-01'

    # fill_open_na_with_prev_close：同 symbol 前一日 close → 當日 open NA
    from datetime import date

    toy = pl.DataFrame({
        'symbol': ['A', 'A', 'A', 'B', 'B'],
        'date': [date(2020, 1, 3), date(2020, 1, 4), date(2020, 1, 5),
                 date(2020, 1, 2), date(2020, 1, 3)],
        'open': [10.0, None, 12.0, None, 20.0],
        'close': [10.5, 11.0, 12.5, 19.0, 20.5],
    })
    filled = fill_open_na_with_prev_close(toy)
    # A: day2 open NA → day1 close 10.5；B: 首日 open NA 無前日 → 仍 null
    a = filled.filter(pl.col('symbol') == 'A').sort('date')
    b = filled.filter(pl.col('symbol') == 'B').sort('date')
    assert a['open'].to_list() == [10.0, 10.5, 12.0]
    assert b['open'].to_list() == [None, 20.0]

    # encode_limit_status：+ → 1，- → -1，null → 0
    lim = encode_limit_status(pl.DataFrame({'limit_status': ['+', '-', None, '+']}))
    assert lim['limit_status'].to_list() == [1, -1, 0, 1]

    # encode_ohlcv_codes：含 market
    coded = encode_ohlcv_codes(
        pl.DataFrame(
            {
                'limit_status': ['+'],
                'attention_stock': ['A'],
                'disposed_stock': [None],
                'full_delivery': ['Y'],
                'market': ['TSE'],
            }
        )
    )
    assert coded['limit_status'].to_list() == [1]
    assert coded['attention_stock'].to_list() == [1]
    assert coded['disposed_stock'].to_list() == [0]
    assert coded['full_delivery'].to_list() == [1]
    assert coded['market'].to_list() == [1]

    # encode_special_stock_flags：A/D/Y → 1，null → 0
    flags = encode_special_stock_flags(pl.DataFrame({
        'attention_stock': ['A', None],
        'disposed_stock': [None, 'D'],
        'full_delivery': ['Y', None],
    }))
    assert flags['attention_stock'].to_list() == [1, 0]
    assert flags['disposed_stock'].to_list() == [0, 1]
    assert flags['full_delivery'].to_list() == [1, 0]

    # process_and_validate_spread：(high-low)/prev_next_open_ref*100；無前日 → NA
    spread_toy = pl.DataFrame({
        'symbol': ['S', 'S', 'S'],
        'date': [date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6)],
        'high': [11.0, 12.0, 13.0],
        'low': [9.0, 10.0, 12.0],
        'next_open_ref': [10.0, 11.0, 12.0],
        # day2: (12-10)/10*100=20；TEJ 給 20.0 → 一致
        # day3: (13-12)/11*100≈9.0909；TEJ 給 9.0 → round2 後 9.09 vs 9.0 → mismatch
        # day1: 無前日 → NA；TEJ 給 0.0 → mismatch
        'spread': [0.0, 20.0, 9.0],
    })
    spread_df, spread_mm = process_and_validate_spread(spread_toy)
    assert spread_df['spread'][0] is None
    assert abs(spread_df['spread'][1] - 20.0) < 1e-9
    assert abs(spread_df['spread'][2] - (1.0 / 11.0 * 100)) < 1e-9
    assert spread_mm.height == 2  # day1 null≠0、day3 9.09≠9.0
    assert set(spread_mm['date'].to_list()) == {date(2020, 1, 2), date(2020, 1, 6)}

    # process_OHLCV_df：串整條管線 + 只留 keep_col
    raw = pl.DataFrame({
        'symbol': ['X', 'X'],
        'date': [date(2020, 1, 2), date(2020, 1, 3)],
        'open': [10.0, None],
        'high': [11.0, 12.0],
        'low': [9.0, 10.0],
        'close': [10.5, 11.5],
        'volume': [1.0, 2.0],
        'amount': [1.0, 2.0],
        'return_day': [0.0, 0.0],
        'turnover': [0.0, 0.0],
        'market_value_million': [1.0, 1.0],
        'log_return_day': [0.0, 0.0],
        'numtrades': [1.0, 1.0],
        'limit_status': ['+', None],
        'spread': [0.0, 0.0],
        'next_open_ref': [10.0, 11.0],
        'next_limit_up': [0.0, 0.0],
        'next_limit_down': [0.0, 0.0],
        'attention_stock': ['A', None],
        'disposed_stock': [None, 'D'],
        'full_delivery': [None, None],
        'market': ['TSE', 'TSE'],
        'pe_ratio_tse': [1.0, 1.0],  # rest：應被丢掉
    })
    out = process_OHLCV_df(raw)
    assert out.columns == keep_col
    assert out['open'].to_list() == [10.0, 10.5]
    assert out['limit_status'].to_list() == [1, 0]
    assert out['attention_stock'].to_list() == [1, 0]
    assert out['disposed_stock'].to_list() == [0, 1]
    print('ok')
    