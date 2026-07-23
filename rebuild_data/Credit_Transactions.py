# TEJ 融資融券：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wgin.html
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（比率／遮罩＋當日買賣／償還痕跡）— 順序在完整 SCHEMA 最前
CREDIT_TRANSACTIONS_KEEP_SCHEMA = {
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '是否可信用交易(Y)': ('marginable', 'string'),
    '融資使用率': ('margin_usage_rate', 'float64'),
    '融券使用率': ('short_usage_rate', 'float64'),
    '券資比': ('short_to_margin_ratio', 'float64'),
    '融資增減比率': ('margin_change_ratio', 'float64'),
    '融券增減比率': ('short_change_ratio', 'float64'),
    '融資(買+賣)/成交量 %': ('margin_volume_pct', 'float64'),
    '融券(買+賣)/成交量 %': ('short_volume_pct', 'float64'),
    '融資維持率': ('margin_maintenance_ratio', 'float64'),
    '融券維持率': ('short_maintenance_ratio', 'float64'),
    '整戶維持率': ('account_maintenance_ratio', 'float64'),
    # 當日交易痕跡（絕對張數；橫比請另做標準化）
    '融資買進(張)': ('margin_buy_lot', 'float64'),
    '融資賣出(張)': ('margin_sell_lot', 'float64'),
    '融資現金償還(張)': ('margin_cash_repay_lot', 'float64'),
    '融券買進(張)': ('short_buy_lot', 'float64'),
    '融券賣出(張)': ('short_sell_lot', 'float64'),
    '融券現券償還(張)': ('short_stock_repay_lot', 'float64'),
    '融券最後回補日': ('short_last_cover_date', 'datetime64[ns]'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；餘額張數僅供算償還比率）
_CREDIT_TRANSACTIONS_REST_SCHEMA = {
    '融資餘額(張)': ('margin_balance_lot', 'float64'),
    '融資餘額(千元)': ('margin_balance_thousand', 'float64'),
    '融資買進(千元)': ('margin_buy_thousand', 'float64'),
    '融資賣出(千元)': ('margin_sell_thousand', 'float64'),
    '融資現金償還(千元)': ('margin_cash_repay_thousand', 'float64'),
    '融資增減(張)': ('margin_change_lot', 'float64'),
    '融資增減(千元)': ('margin_change_thousand', 'float64'),
    '融資限額': ('margin_limit', 'float64'),
    '融券餘額(張)': ('short_balance_lot', 'float64'),
    '融券餘額(千元)': ('short_balance_thousand', 'float64'),
    '融券買進(千元)': ('short_buy_thousand', 'float64'),
    '融券賣出(千元)': ('short_sell_thousand', 'float64'),
    '融券現券償還(千元)': ('short_stock_repay_thousand', 'float64'),
    '融券增減(張)': ('short_change_lot', 'float64'),
    '融券增減(千元)': ('short_change_thousand', 'float64'),
    '融券限額': ('short_limit', 'float64'),
    '資券互抵': ('margin_short_offset', 'float64'),
    '當日收盤': ('close', 'float64'),
    '借券賣出餘額(張)': ('sbl_sell_balance_lot', 'float64'),
    '借券賣出餘額(千元)': ('sbl_sell_balance_thousand', 'float64'),
    '借券賣出(張)': ('sbl_sell_lot', 'float64'),
    '借券賣出(千元)': ('sbl_sell_thousand', 'float64'),
    '借券賣出庫存異動(張)': ('sbl_sell_inventory_change_lot', 'float64'),
    '借券賣出庫存異動(千元)': ('sbl_sell_inventory_change_thousand', 'float64'),
    '借券賣出可使用額度': ('sbl_sell_available', 'float64'),
    '借券賣出限額': ('sbl_sell_limit', 'float64'),
    '借券賣出(千元)_交易所': ('sbl_sell_thousand_exch', 'float64'),
    '融券賣出(千元)_交易所': ('short_sell_thousand_exch', 'float64'),
    '均價': ('avg_price', 'float64'),
    '每股融資成本': ('margin_cost_per_share', 'float64'),
    '每股融券成本': ('short_cost_per_share', 'float64'),
    '融資暫停交易起日': ('margin_halt_start', 'datetime64[ns]'),
    '融券暫停交易起日': ('short_halt_start', 'datetime64[ns]'),
    '資券暫停交易迄日': ('margin_short_halt_end', 'datetime64[ns]'),
}

# 完整 schema：保留欄位在上
CREDIT_TRANSACTIONS_SCHEMA = {
    **CREDIT_TRANSACTIONS_KEEP_SCHEMA,
    **_CREDIT_TRANSACTIONS_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in CREDIT_TRANSACTIONS_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in CREDIT_TRANSACTIONS_SCHEMA.items()}

# TEJ 融資融券
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wgin.html'

# 先跑 add_credit_ratios，再依 keep_col 篩選（餘額張數僅供算償還比率）
keep_col = [
    *[en for en, _ in CREDIT_TRANSACTIONS_KEEP_SCHEMA.values()],
    'margin_cash_repay_ratio',
    'short_stock_repay_ratio',
]


def add_credit_ratios(df):
    """償還／餘額比率（橫截面可比）；餘額≤0 時為 null。

    需已有英文欄 margin_cash_repay_lot / margin_balance_lot、
    short_stock_repay_lot / short_balance_lot（read_tej_txt 後）。
    """
    import polars as pl

    bal_m = pl.col('margin_balance_lot')
    bal_s = pl.col('short_balance_lot')
    return df.with_columns(
        pl.when(bal_m > 0)
        .then(pl.col('margin_cash_repay_lot') / bal_m)
        .otherwise(None)
        .alias('margin_cash_repay_ratio'),
        pl.when(bal_s > 0)
        .then(pl.col('short_stock_repay_lot') / bal_s)
        .otherwise(None)
        .alias('short_stock_repay_ratio'),
    )


if __name__ == '__main__':
    import polars as pl

    assert len(CREDIT_TRANSACTIONS_SCHEMA) == 54
    assert len(CREDIT_TRANSACTIONS_KEEP_SCHEMA) == 20
    assert set(RENAME_MAP) == set(CREDIT_TRANSACTIONS_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in CREDIT_TRANSACTIONS_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert CREDIT_TRANSACTIONS_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert list(CREDIT_TRANSACTIONS_SCHEMA)[: len(CREDIT_TRANSACTIONS_KEEP_SCHEMA)] == list(
        CREDIT_TRANSACTIONS_KEEP_SCHEMA
    )
    assert keep_col[:20] == [en for en, _ in CREDIT_TRANSACTIONS_KEEP_SCHEMA.values()]
    assert keep_col[-2:] == ['margin_cash_repay_ratio', 'short_stock_repay_ratio']

    # ponytail: 最小自檢；邏輯破了會 fail
    _t = add_credit_ratios(
        pl.DataFrame(
            {
                'margin_cash_repay_lot': [2.0, 1.0, 5.0],
                'margin_balance_lot': [10.0, 0.0, -1.0],
                'short_stock_repay_lot': [3.0, 4.0, 1.0],
                'short_balance_lot': [12.0, 0.0, 5.0],
            }
        )
    )
    assert _t['margin_cash_repay_ratio'].to_list() == [0.2, None, None]
    assert _t['short_stock_repay_ratio'].to_list() == [0.25, None, 0.2]
    print('ok')
