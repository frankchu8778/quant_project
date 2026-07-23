# TEJ 籌碼分佈(2008年起)：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wshr1.html
# 注意：TEJ 文件標示歷史約最近 2 年，長樣本請另確認實際檔案範圍
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（橫截面可比為主；增減張數為痕跡，橫比前請標準化）— 順序在完整 SCHEMA 最前
SHARE_DISTRIBUTION_KEEP_SCHEMA = {
    # tej_symbol：空白前為代碼（如 "0050 元大台灣50" → "0050"）
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    # 成交結構
    '外資成交比重': ('foreign_trade_share_pct', 'float64'),
    '投信成交比重': ('it_trade_share_pct', 'float64'),
    '自營成交比重': ('dealer_trade_share_pct', 'float64'),
    '信用交易比重': ('credit_trade_share_pct', 'float64'),
    '一般現股成交比重': ('cash_trade_share_pct', 'float64'),
    # 流動性／持股／董監（投信／自營持股率改由 net_flow 保留）
    '實際週轉率％': ('free_float_turnover_pct', 'float64'),
    '外資總持股率_不含董監%': ('foreign_holding_ex_dir_pct', 'float64'),
    '董監持股％': ('director_holding_pct', 'float64'),
    '董監質押％': ('director_pledge_pct', 'float64'),
    '資券互抵比例': ('margin_short_offset_pct', 'float64'),
    # 增減拆分痕跡（絕對張數；橫比請另做標準化）
    # 融資／融券使用率、券資比改由 Credit_Transactions 保留
    '融資增加(張)': ('margin_increase_lot', 'float64'),
    '融資減少(張)': ('margin_decrease_lot', 'float64'),
    '融券增加(張)': ('short_increase_lot', 'float64'),
    '融券減少(張)': ('short_decrease_lot', 'float64'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
_SHARE_DISTRIBUTION_REST_SCHEMA = {
    '名稱': ('name', 'string'),
    '未調整收盤價(元)': ('close_unadj', 'float64'),
    '外資買賣超(張)': ('foreign_net_buy_lot', 'float64'),
    '投信買賣超(張)': ('it_net_buy_lot', 'float64'),
    '自營買賣超(張)': ('dealer_net_buy_lot', 'float64'),
    '合計買賣超(張)': ('inst_net_buy_lot', 'float64'),
    '外資買超(張)': ('foreign_buy_excess_lot', 'float64'),
    '外資賣超(張)': ('foreign_sell_excess_lot', 'float64'),
    '投信買超(張)': ('it_buy_excess_lot', 'float64'),
    '投信賣超(張)': ('it_sell_excess_lot', 'float64'),
    '自營買超(張)': ('dealer_buy_excess_lot', 'float64'),
    '自營賣超(張)': ('dealer_sell_excess_lot', 'float64'),
    '外資買進金額(百萬)': ('foreign_buy_amt_million', 'float64'),
    '外資賣出金額(百萬)': ('foreign_sell_amt_million', 'float64'),
    '投信買進金額(百萬)': ('it_buy_amt_million', 'float64'),
    '投信賣出金額(百萬)': ('it_sell_amt_million', 'float64'),
    '自營商買進金額(百萬)': ('dealer_buy_amt_million', 'float64'),
    '自營商賣出金額(百萬)': ('dealer_sell_amt_million', 'float64'),
    '三大法人買超(張)': ('inst_buy_excess_lot', 'float64'),
    '三大法人賣超(張)': ('inst_sell_excess_lot', 'float64'),
    '外資買賣超日數': ('foreign_net_buy_days', 'float64'),
    '投信買賣超日數': ('it_net_buy_days', 'float64'),
    '自營買賣超日數': ('dealer_net_buy_days', 'float64'),
    '法人買賣超日數': ('inst_net_buy_days', 'float64'),
    '外資連續累計買賣超(張)': ('foreign_streak_cum_lot', 'float64'),
    '投信連續累計買賣超(張)': ('it_streak_cum_lot', 'float64'),
    '自營連續累計買賣超(張)': ('dealer_streak_cum_lot', 'float64'),
    '法人連續累計買賣超(張)': ('inst_streak_cum_lot', 'float64'),
    '法人成交比重': ('inst_trade_share_pct', 'float64'),
    '資券互抵(張)': ('margin_short_offset_lot', 'float64'),
    '投信持股率％': ('it_holding_pct', 'float64'),
    '自營持股率％': ('dealer_holding_pct', 'float64'),
    '融資使用率': ('margin_usage_rate', 'float64'),
    '融券使用率': ('short_usage_rate', 'float64'),
    '券資比': ('short_to_margin_ratio', 'float64'),
    '外資總持股數': ('foreign_holding_lot', 'float64'),
    '投信持股數(張)': ('it_holding_lot', 'float64'),
    '自營持股數': ('dealer_holding_lot', 'float64'),
    '董監持股數': ('director_holding_lot', 'float64'),
    '融資餘額(張)': ('margin_balance_lot', 'float64'),
    '融資餘額(千元)': ('margin_balance_thousand', 'float64'),
    '融券餘額(張)': ('short_balance_lot', 'float64'),
    '融券餘額(千元)': ('short_balance_thousand', 'float64'),
    '流通在外股數(百萬股)': ('shares_outstanding_million', 'float64'),
}

# 完整 schema：保留欄位在上
SHARE_DISTRIBUTION_SCHEMA = {
    **SHARE_DISTRIBUTION_KEEP_SCHEMA,
    **_SHARE_DISTRIBUTION_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in SHARE_DISTRIBUTION_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in SHARE_DISTRIBUTION_SCHEMA.items()}

# TEJ 籌碼分佈(2008年起)
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wshr1.html'

keep_col = [en for en, _ in SHARE_DISTRIBUTION_KEEP_SCHEMA.values()]


if __name__ == '__main__':
    assert len(SHARE_DISTRIBUTION_SCHEMA) == 60
    assert len(SHARE_DISTRIBUTION_KEEP_SCHEMA) == 16
    assert set(RENAME_MAP) == set(SHARE_DISTRIBUTION_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in SHARE_DISTRIBUTION_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert SHARE_DISTRIBUTION_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == [en for en, _ in SHARE_DISTRIBUTION_KEEP_SCHEMA.values()]
    assert list(SHARE_DISTRIBUTION_SCHEMA)[: len(SHARE_DISTRIBUTION_KEEP_SCHEMA)] == list(
        SHARE_DISTRIBUTION_KEEP_SCHEMA
    )
    print('ok')
