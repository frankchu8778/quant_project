# TEJ 籌碼動向＆報酬(2008年起)：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（買賣超／連續區間報酬與累計）— 順序在完整 SCHEMA 最前
INSTITUTIONAL_RETURN_KEEP_SCHEMA = {
    # tej_symbol：空白前為代碼（如 "0050 元大台灣50" → "0050"）
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '外資買賣超(張)': ('foreign_net_buy_lot', 'float64'),
    '投信買賣超(張)': ('it_net_buy_lot', 'float64'),
    '合計買賣超(張)': ('inst_net_buy_lot', 'float64'),
    '信用交易買賣超(張)': ('margin_net_buy_lot', 'float64'),
    '一般現股買賣超(張)': ('cash_net_buy_lot', 'float64'),
    '外資買賣超日數': ('foreign_net_buy_days', 'float64'),
    '投信買賣超日數': ('it_net_buy_days', 'float64'),
    '自營買賣超日數': ('dealer_net_buy_days', 'float64'),
    '法人買賣超日數': ('inst_net_buy_days', 'float64'),
    '資券買賣超日數': ('margin_net_buy_days', 'float64'),
    '現股買賣超日數': ('cash_net_buy_days', 'float64'),
    '外資連續買賣超區間報酬': ('foreign_streak_return', 'float64'),
    '投信連續買賣超區間報酬': ('it_streak_return', 'float64'),
    '自營連續買賣超區間報酬': ('dealer_streak_return', 'float64'),
    '法人連續買賣超區間報酬': ('inst_streak_return', 'float64'),
    '資券連續買賣超區間報酬': ('margin_streak_return', 'float64'),
    '現股連續買賣超區間報酬': ('cash_streak_return', 'float64'),
    '外資連續累計買賣超(張)': ('foreign_streak_cum_lot', 'float64'),
    '投信連續累計買賣超(張)': ('it_streak_cum_lot', 'float64'),
    '自營連續累計買賣超(張)': ('dealer_streak_cum_lot', 'float64'),
    '法人連續累計買賣超(張)': ('inst_streak_cum_lot', 'float64'),
    '資券連續累計買賣超(張)': ('margin_streak_cum_lot', 'float64'),
    '現股連續累計買賣超(張)': ('cash_streak_cum_lot', 'float64'),
    # (千) ≈ 千元：連續累計張數 × 未調整收盤價
    '外資連續累計買賣超(千)': ('foreign_streak_cum_amt_thousand', 'float64'),
    '投信連續累計買賣超(千)': ('it_streak_cum_amt_thousand', 'float64'),
    '自營連續累計買賣超(千)': ('dealer_streak_cum_amt_thousand', 'float64'),
    '法人連續累計買賣超(千)': ('inst_streak_cum_amt_thousand', 'float64'),
    '資券連續累計買賣超(千)': ('margin_streak_cum_amt_thousand', 'float64'),
    '現股連續累計買賣超(千)': ('cash_streak_cum_amt_thousand', 'float64'),
}

# 其餘欄位（不進 keep_col）
# close_unadj：OHLCV 已有；dealer_net_buy_lot：改用 net_flow 自行+避險淨額
_INSTITUTIONAL_RETURN_REST_SCHEMA = {
    '未調整收盤價(元)': ('close_unadj', 'float64'),
    '自營買賣超(張)': ('dealer_net_buy_lot', 'float64'),
}

# 完整 schema：保留欄位在上
INSTITUTIONAL_RETURN_SCHEMA = {
    **INSTITUTIONAL_RETURN_KEEP_SCHEMA,
    **_INSTITUTIONAL_RETURN_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in INSTITUTIONAL_RETURN_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in INSTITUTIONAL_RETURN_SCHEMA.items()}

# TEJ 籌碼動向＆報酬(2008年起)；文件代號請自行對 TEJ 補上
db_doc_url = ' https://www.tej.com.tw/tejdoc/db-document/tw/wshr1a.html'

keep_col = [en for en, _ in INSTITUTIONAL_RETURN_KEEP_SCHEMA.values()]


if __name__ == '__main__':
    assert len(INSTITUTIONAL_RETURN_SCHEMA) == 33
    assert len(INSTITUTIONAL_RETURN_KEEP_SCHEMA) == 31
    assert set(RENAME_MAP) == set(INSTITUTIONAL_RETURN_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in INSTITUTIONAL_RETURN_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert INSTITUTIONAL_RETURN_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == [en for en, _ in INSTITUTIONAL_RETURN_KEEP_SCHEMA.values()]
    assert list(INSTITUTIONAL_RETURN_SCHEMA)[: len(INSTITUTIONAL_RETURN_KEEP_SCHEMA)] == list(
        INSTITUTIONAL_RETURN_KEEP_SCHEMA
    )
    assert set(keep_col).isdisjoint({'close_unadj', 'dealer_net_buy_lot'})
    print('ok')
