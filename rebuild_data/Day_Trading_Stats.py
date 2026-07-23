# TEJ 當日沖銷交易統計資訊（當沖資料）：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wdt.html
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（橫截面可比的當沖比重）— 順序在完整 SCHEMA 最前
DAY_TRADING_STATS_KEEP_SCHEMA = {
    # tej_symbol：空白前為代碼（如 "0050 元大台灣50" → "0050"）
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '當日沖銷交易總成交股數占市場比重%': ('day_trade_volume_mkt_pct', 'float64'),
    '當沖比重(資券互抵)': ('day_trade_margin_short_offset_pct', 'float64'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
_DAY_TRADING_STATS_REST_SCHEMA = {
    '收盤價(元)': ('close', 'float64'),
    '成交量(千股)': ('volume', 'float64'),
    '成交值(千元)': ('amount', 'float64'),
    '當日沖銷交易總成交股數(千股)': ('day_trade_volume', 'float64'),
    '當日沖銷交易總買進成交金額(千元)': ('day_trade_buy_amount', 'float64'),
    '當日沖銷交易總買進成交金額占市場比重%': ('day_trade_buy_amount_mkt_pct', 'float64'),
    '當日沖銷交易總賣出成交金額(千元)': ('day_trade_sell_amount', 'float64'),
    '當日沖銷交易總賣出成交金額占市場比重%': ('day_trade_sell_amount_mkt_pct', 'float64'),
    '報酬率％': ('return_day', 'float64'),
    '週轉率％': ('turnover', 'float64'),
    '現沖+當沖比重': ('cash_plus_day_trade_pct', 'float64'),
}

# 完整 schema：保留欄位在上
DAY_TRADING_STATS_SCHEMA = {
    **DAY_TRADING_STATS_KEEP_SCHEMA,
    **_DAY_TRADING_STATS_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in DAY_TRADING_STATS_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in DAY_TRADING_STATS_SCHEMA.items()}

# TEJ 當日沖銷交易統計資訊（當沖資料）
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wdt.html'

keep_col = [en for en, _ in DAY_TRADING_STATS_KEEP_SCHEMA.values()]


if __name__ == '__main__':
    assert len(DAY_TRADING_STATS_SCHEMA) == 15
    assert len(DAY_TRADING_STATS_KEEP_SCHEMA) == 4
    assert set(RENAME_MAP) == set(DAY_TRADING_STATS_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in DAY_TRADING_STATS_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert DAY_TRADING_STATS_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == [en for en, _ in DAY_TRADING_STATS_KEEP_SCHEMA.values()]
    assert list(DAY_TRADING_STATS_SCHEMA)[: len(DAY_TRADING_STATS_KEEP_SCHEMA)] == list(
        DAY_TRADING_STATS_KEEP_SCHEMA
    )
    print('ok')
