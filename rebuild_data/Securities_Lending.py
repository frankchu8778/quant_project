# TEJ 借券餘額：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wborrow.html
# 借券欄暫不進 daily_data（rebuild 標有問題）；KEEP 只留鍵欄。
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位 — 順序在完整 SCHEMA 最前
SECURITIES_LENDING_KEEP_SCHEMA = {
    # 此檔欄名為「公司代碼」（純代碼）；名稱另欄
    '公司代碼': ('symbol', 'string'),
    '年月日': ('date', 'datetime64[ns]'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；餘額／淨流向暫不保留）
_SECURITIES_LENDING_REST_SCHEMA = {
    '收盤價(元)': ('close', 'float64'),
    '合計-借券餘額(千股)': ('lend_total_balance', 'float64'),
    '合計-借券(千股)': ('lend_total_borrow', 'float64'),
    '合計-還券(千股)': ('lend_total_return', 'float64'),
    '合計-借券餘額市值(元)': ('lend_total_balance_mkt_value', 'float64'),
    '証交所-借券餘額(千股)': ('lend_exch_balance', 'float64'),
    '証交所-借券(千股)': ('lend_exch_borrow', 'float64'),
    '証交所-還券(千股)': ('lend_exch_return', 'float64'),
    '証交所-借券餘額市值(元)': ('lend_exch_balance_mkt_value', 'float64'),
    '證商/證金-借券餘額(千股)': ('lend_broker_balance', 'float64'),
    '證商/證金-借券(千股)': ('lend_broker_borrow', 'float64'),
    '證商/證金-還券(千股)': ('lend_broker_return', 'float64'),
    '證商/證金借券餘額市值(元)': ('lend_broker_balance_mkt_value', 'float64'),
    '市場別': ('market', 'string'),
}

# 完整 schema：保留欄位在上
SECURITIES_LENDING_SCHEMA = {
    **SECURITIES_LENDING_KEEP_SCHEMA,
    **_SECURITIES_LENDING_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in SECURITIES_LENDING_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in SECURITIES_LENDING_SCHEMA.items()}

# TEJ 借券餘額
db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wborrow.html'

keep_col = [en for en, _ in SECURITIES_LENDING_KEEP_SCHEMA.values()]


def fill_lend_balance_na_if_sum_matches(df):
    """若 NA 暫當 0 時 証交所+證商/證金 == 合計，則把兩側餘額的 NA 設為 0。

    需已有英文欄 lend_total_balance / lend_exch_balance / lend_broker_balance。
    """
    import polars as pl

    exch = pl.col('lend_exch_balance')
    broker = pl.col('lend_broker_balance')
    total = pl.col('lend_total_balance')
    ok = exch.fill_null(0) + broker.fill_null(0) == total
    return df.with_columns(
        pl.when(ok).then(exch.fill_null(0)).otherwise(exch).alias('lend_exch_balance'),
        pl.when(ok).then(broker.fill_null(0)).otherwise(broker).alias('lend_broker_balance'),
    )


def add_lend_net_flow(df):
    """每日淨借券流向：借券−還券；正=當日借出多，負=還券多。

    需已有英文欄 lend_exch_borrow/return、lend_broker_borrow/return（read_tej_txt 後）。
    """
    import polars as pl

    return df.with_columns(
        (pl.col('lend_exch_borrow') - pl.col('lend_exch_return')).alias('lend_exch_net'),
        (pl.col('lend_broker_borrow') - pl.col('lend_broker_return')).alias('lend_broker_net'),
    )


def process_securities_lending(df):
    """借券處理入口：目前只保留 symbol / date（餘額欄暫不進 DB）。"""
    return df.select(keep_col)


if __name__ == '__main__':
    import polars as pl

    assert len(SECURITIES_LENDING_SCHEMA) == 16
    assert len(SECURITIES_LENDING_KEEP_SCHEMA) == 2
    assert set(RENAME_MAP) == set(SECURITIES_LENDING_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in SECURITIES_LENDING_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert SECURITIES_LENDING_SCHEMA['公司代碼'] == ('symbol', 'string')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == ['symbol', 'date']
    assert list(SECURITIES_LENDING_SCHEMA)[: len(SECURITIES_LENDING_KEEP_SCHEMA)] == list(
        SECURITIES_LENDING_KEEP_SCHEMA
    )

    # ponytail: 最小自檢
    _out = process_securities_lending(
        pl.DataFrame(
            {
                'symbol': ['A', 'B'],
                'date': [None, None],
                'lend_exch_balance': [None, None],
                'lend_broker_balance': [5.0, 5.0],
                'lend_total_balance': [5.0, 10.0],
                'lend_total_return': [0.0, 0.0],
                'lend_exch_borrow': [10.0, 1.0],
                'lend_exch_return': [3.0, 5.0],
                'lend_broker_borrow': [2.0, 8.0],
                'lend_broker_return': [2.0, 1.0],
            }
        )
    )
    assert _out.columns == keep_col
    assert _out.height == 2
    print('ok')
