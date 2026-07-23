# TEJ 借券餘額：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wborrow.html
TEJ_DATE_FORMAT = '%Y%m%d'

SECURITIES_LENDING_SCHEMA = {
    # tej_symbol：空白前為代碼（如 "0050 元大台灣50" → "0050"）
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '收盤價(元)': ('close', 'float64'),
    '合計-借券(千股)': ('lend_total_borrow', 'float64'),
    '合計-還券(千股)': ('lend_total_return', 'float64'),
    '合計-借券餘額(千股)': ('lend_total_balance', 'float64'),
    '合計-借券餘額市值(元)': ('lend_total_balance_mkt_value', 'float64'),
    '証交所-借券(千股)': ('lend_exch_borrow', 'float64'),
    '証交所-還券(千股)': ('lend_exch_return', 'float64'),
    '証交所-借券餘額(千股)': ('lend_exch_balance', 'float64'),
    '証交所-借券餘額市值(元)': ('lend_exch_balance_mkt_value', 'float64'),
    '證商/證金-借券(千股)': ('lend_broker_borrow', 'float64'),
    '證商/證金-還券(千股)': ('lend_broker_return', 'float64'),
    '證商/證金-借券餘額(千股)': ('lend_broker_balance', 'float64'),
    '證商/證金借券餘額市值(元)': ('lend_broker_balance_mkt_value', 'float64'),
    '市場別': ('market', 'string'),
}

RENAME_MAP = {zh: en for zh, (en, _) in SECURITIES_LENDING_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in SECURITIES_LENDING_SCHEMA.items()}

# TEJ 借券餘額
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wborrow.html'

# 先跑 add_lend_net_flow，再依 keep_col 篩選（borrow/return 僅供算淨流向）
keep_col = [
    'symbol',
    'date',
    'lend_exch_balance',
    'lend_broker_balance',
    'lend_exch_net',
    'lend_broker_net',
]


def add_lend_net_flow(df):
    """每日淨借券流向：借券−還券；正=當日借出多，負=還券多。

    需已有英文欄 lend_exch_borrow/return、lend_broker_borrow/return（read_tej_txt 後）。
    """
    import polars as pl

    return df.with_columns(
        (pl.col('lend_exch_borrow') - pl.col('lend_exch_return')).alias('lend_exch_net'),
        (pl.col('lend_broker_borrow') - pl.col('lend_broker_return')).alias('lend_broker_net'),
    )


if __name__ == '__main__':
    import polars as pl

    assert len(SECURITIES_LENDING_SCHEMA) == 16
    assert set(RENAME_MAP) == set(SECURITIES_LENDING_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in SECURITIES_LENDING_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert SECURITIES_LENDING_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複

    # ponytail: 最小自檢；邏輯破了會 fail
    _t = add_lend_net_flow(
        pl.DataFrame(
            {
                'lend_exch_borrow': [10.0, 1.0],
                'lend_exch_return': [3.0, 5.0],
                'lend_broker_borrow': [2.0, 8.0],
                'lend_broker_return': [2.0, 1.0],
            }
        )
    )
    assert _t['lend_exch_net'].to_list() == [7.0, -4.0]
    assert _t['lend_broker_net'].to_list() == [0.0, 7.0]
    print('ok')
