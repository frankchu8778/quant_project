# TEJ 三大法人買賣超：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wtinst1.html
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（持股／週轉率％＋自營自行／避險淨額）— 順序在完整 SCHEMA 最前
INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA = {
    # 此檔欄名為「證券名稱」（純代碼，非「代碼 名稱」）；名稱另欄
    '證券名稱': ('symbol', 'string'),
    '年月日': ('date', 'datetime64[ns]'),
    '外資總投資股率%': ('foreign_holding_pct', 'float64'),
    '投信持股率%': ('it_holding_pct', 'float64'),
    '自營持股率%': ('dealer_holding_pct', 'float64'),
    '外資週轉率%': ('foreign_turnover_pct', 'float64'),
    '投信週轉率%': ('it_turnover_pct', 'float64'),
    '自營商週轉率%': ('dealer_turnover_pct', 'float64'),
    '自營自行買賣超(千股)': ('dealer_prop_net_buy_thousand_shares', 'float64'),
    '自營避險買賣超(千股)': ('dealer_hedge_net_buy_thousand_shares', 'float64'),
}
# 自營當日淨額（取代 return.dealer_net_buy_lot）；買進−賣出已合併，不另留 buy/sell
# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
# shares_outstanding_thousand：與 OHLCV 撞名，以 OHLCV 為準不進 keep_col
_INSTITUTIONAL_NET_FLOW_REST_SCHEMA = {
    '流通在外股數(千股)': ('shares_outstanding_thousand', 'float64'),
    '外資買賣超(千股)': ('foreign_net_buy_thousand_shares', 'float64'),
    '外資買賣超市值(百萬)': ('foreign_net_buy_mkt_value_million', 'float64'),
    '外資總投資股數(千股)': ('foreign_holding_thousand_shares', 'float64'),
    '外資總投資市值(百萬)': ('foreign_holding_mkt_value_million', 'float64'),
    '投信買賣超(千股)': ('it_net_buy_thousand_shares', 'float64'),
    '投信買賣超市值(百萬)': ('it_net_buy_mkt_value_million', 'float64'),
    '投信持股數(千股)': ('it_holding_thousand_shares', 'float64'),
    '投信持股數市值(百萬)': ('it_holding_mkt_value_million', 'float64'),
    '自營買賣超(千股)': ('dealer_net_buy_thousand_shares', 'float64'),
    '自營買賣超市值(百萬)': ('dealer_net_buy_mkt_value_million', 'float64'),
    '自營自行買賣超(百萬)': ('dealer_prop_net_buy_mkt_value_million', 'float64'),
    '自營避險買賣超(百萬)': ('dealer_hedge_net_buy_mkt_value_million', 'float64'),
    '自營持股數(千股)': ('dealer_holding_thousand_shares', 'float64'),
    '自營持股數市值(百萬)': ('dealer_holding_mkt_value_million', 'float64'),
    '合計買賣超(千股)': ('inst_net_buy_thousand_shares', 'float64'),
    '合計買賣超市值(百萬)': ('inst_net_buy_mkt_value_million', 'float64'),
    '合計持股數(千股)': ('inst_holding_thousand_shares', 'float64'),
    '合計持股數市值(百萬)': ('inst_holding_mkt_value_million', 'float64'),
    '外資買進張數': ('foreign_buy_lot', 'float64'),
    '外資賣出張數': ('foreign_sell_lot', 'float64'),
    '投信買進張數': ('it_buy_lot', 'float64'),
    '投信賣出張數': ('it_sell_lot', 'float64'),
    '自營商買進張數': ('dealer_buy_lot', 'float64'),
    '自營商賣出張數': ('dealer_sell_lot', 'float64'),
    '自營商自行買進張數': ('dealer_prop_buy_lot', 'float64'),
    '自營商自行賣出張數': ('dealer_prop_sell_lot', 'float64'),
    '自營商避險買進張數': ('dealer_hedge_buy_lot', 'float64'),
    '自營商避險賣出張數': ('dealer_hedge_sell_lot', 'float64'),
    '合計持股率%': ('inst_holding_pct', 'float64'),
}

# 完整 schema：保留欄位在上
INSTITUTIONAL_NET_FLOW_SCHEMA = {
    **INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA,
    **_INSTITUTIONAL_NET_FLOW_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in INSTITUTIONAL_NET_FLOW_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in INSTITUTIONAL_NET_FLOW_SCHEMA.items()}

# TEJ 三大法人買賣超
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wtinst1.html'

keep_col = [en for en, _ in INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA.values()]

# 無持股／無週轉／無買賣超 → 缺失視為 0
ZERO_FILL_COLS = (
    'foreign_holding_pct',
    'it_holding_pct',
    'dealer_holding_pct',
    'foreign_turnover_pct',
    'it_turnover_pct',
    'dealer_turnover_pct',
    'dealer_prop_net_buy_thousand_shares',
    'dealer_hedge_net_buy_thousand_shares',
)


def fill_nulls(df):
    """ZERO_FILL_COLS 缺失填 0（read_tej_txt 後）。"""
    import polars as pl

    return df.with_columns(pl.col(c).fill_null(0) for c in ZERO_FILL_COLS)


if __name__ == '__main__':
    import polars as pl

    assert len(INSTITUTIONAL_NET_FLOW_SCHEMA) == 40
    assert len(INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA) == 10
    assert set(RENAME_MAP) == set(INSTITUTIONAL_NET_FLOW_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in INSTITUTIONAL_NET_FLOW_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert INSTITUTIONAL_NET_FLOW_SCHEMA['證券名稱'] == ('symbol', 'string')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == [en for en, _ in INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA.values()]
    assert 'shares_outstanding_thousand' not in keep_col  # 避免與 OHLCV join 撞名
    assert list(INSTITUTIONAL_NET_FLOW_SCHEMA)[: len(INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA)] == list(
        INSTITUTIONAL_NET_FLOW_KEEP_SCHEMA
    )

    # ponytail: 最小自檢；邏輯破了會 fail
    _t = fill_nulls(
        pl.DataFrame({c: [None, 1.0] for c in ZERO_FILL_COLS})
    )
    assert all(_t[c].to_list() == [0.0, 1.0] for c in ZERO_FILL_COLS)
    print('ok')
