# TEJ Daily_Unadjusted_Price：中文欄位 → (英文名, pandas dtype)
TEJ_DATE_FORMAT = '%Y%m%d'

OHLCV_SCHEMA = {
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
    '流通在外股數(千股)': ('shares_outstanding_thousand', 'float64'),
    '市值(百萬元)': ('market_value_million', 'float64'),
    '最後揭示買價': ('last_bid', 'float64'),
    '最後揭示賣價': ('last_ask', 'float64'),
    '報酬率-Ln': ('log_return_day', 'float64'),
    '市值比重％': ('market_value_pct', 'float64'),
    '成交值比重％': ('trading_value_pct', 'float64'),
    '成交筆數(筆)': ('numtrades', 'float64'),
    '本益比-TSE': ('pe_ratio_tse', 'float64'),
    '本益比-TEJ': ('pe_ratio_tej', 'float64'),
    '股價淨值比-TSE': ('pb_ratio_tse', 'float64'),
    '股價淨值比-TEJ': ('pb_ratio_tej', 'float64'),
    '漲跌停': ('limit_status', 'string'),
    '股價營收比-TEJ': ('ps_ratio_tej', 'float64'),
    '股利殖利率-TSE': ('div_yield_tse', 'float64'),
    '現金股利率': ('cash_div_yield', 'float64'),
    '股價漲跌(元)': ('price_change', 'float64'),
    '高低價差%': ('spread', 'float64'),
    '次日開盤參考價': ('next_open_ref', 'float64'),
    '次日漲停價': ('next_limit_up', 'float64'),
    '次日跌停價': ('next_limit_down', 'float64'),
    '注意股票(A)': ('attention_stock', 'string'),
    '處置股票(D)': ('disposed_stock', 'string'),
    '全額交割(Y)': ('full_delivery', 'string'),
    '市場別': ('market', 'string'),
}

UNUSE_COLUMNS = ['注意股票(A)', '處置股票(D)', '全額交割(Y)', '市場別']

RENAME_MAP = {zh: en for zh, (en, _) in OHLCV_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in OHLCV_SCHEMA.items()}

db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wprcd.html'


def parse_tej_date(series):
    """TEJ 年月日為 YYYYMMDD 數值（如 20150601.0）→ datetime64[ns]。"""
    import pandas as pd

    return pd.to_datetime(
        series.astype('Int64').astype(str),
        format=TEJ_DATE_FORMAT,
        errors='coerce',
    )
    


if __name__ == '__main__':
    import pandas as pd

    assert len(OHLCV_SCHEMA) == 35
    assert set(RENAME_MAP) == set(OHLCV_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in OHLCV_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert OHLCV_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    parsed = parse_tej_date(pd.Series([20150601.0, 20150602.0]))
    assert pd.api.types.is_datetime64_any_dtype(parsed)
    assert str(parsed.iloc[0].date()) == '2015-06-01'
    print('ok')
