# TEJ 現金股息：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wstk2.html
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（除息日 + 復權因子所需價格）— 順序在完整 SCHEMA 最前
CASH_DIVIDENDS_KEEP_SCHEMA = {
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),  # 除息日
    '息值(元)': ('dividend_per_share', 'float64'),
    '前一日收盤價': ('prev_close', 'float64'),
    '除息(權)參考價(元)': ('ex_div_ref_price', 'float64'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
_CASH_DIVIDENDS_REST_SCHEMA = {
    '盈餘分派_迄日': ('earnings_dist_end', 'datetime64[ns]'),
    '盈餘分派_起日': ('earnings_dist_start', 'datetime64[ns]'),
    '股息分配型態': ('dividend_type', 'string'),
    '現金股利(元)_盈餘': ('cash_div_earnings', 'float64'),
    '現金股利(元)_公積': ('cash_div_capital_reserve', 'float64'),
    '特殊股利(元)': ('special_dividend', 'float64'),
    '發放幣別': ('currency', 'string'),
    '股息總額-盈餘(千元)': ('div_total_earnings_thousand', 'float64'),
    '股息總額-公積(千元)': ('div_total_reserve_thousand', 'float64'),
    '股息總額-特殊(千元)': ('div_total_special_thousand', 'float64'),
    '股息總額(千元)': ('div_total_thousand', 'float64'),
    '股息發放日': ('dividend_pay_date', 'datetime64[ns]'),
    '除息公告日': ('ex_div_announce_date', 'datetime64[ns]'),
    '最後過戶日': ('last_transfer_date', 'datetime64[ns]'),
    '停止過戶-起': ('book_closure_start', 'datetime64[ns]'),
    '停止過戶-迄': ('book_closure_end', 'datetime64[ns]'),
    '停資起始日': ('margin_halt_start', 'string'),
    '停資終止日': ('margin_halt_end', 'string'),
    '停券起始日': ('short_halt_start', 'datetime64[ns]'),
    '停券終止日': ('short_halt_end', 'datetime64[ns]'),
    '融券最後回補日': ('short_cover_deadline', 'datetime64[ns]'),
}

CASH_DIVIDENDS_SCHEMA = {
    **CASH_DIVIDENDS_KEEP_SCHEMA,
    **_CASH_DIVIDENDS_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in CASH_DIVIDENDS_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in CASH_DIVIDENDS_SCHEMA.items()}

db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wstk2.html'

keep_col = [en for en, _ in CASH_DIVIDENDS_KEEP_SCHEMA.values()]


def check_price_nulls(df):
    """檢查 prev_close / ex_div_ref_price 空值；有則打印並回傳該子集，無則空表。"""
    import polars as pl

    bad = df.filter(
        pl.col('prev_close').is_null() | pl.col('ex_div_ref_price').is_null()
    )
    if bad.height:
        print(f'prev_close / ex_div_ref_price 空值：{bad.height} 筆')
        cols = [
            c for c in ('symbol', 'date', 'dividend_per_share', 'prev_close', 'ex_div_ref_price')
            if c in bad.columns
        ]
        print(bad.select(cols))
    else:
        print('prev_close / ex_div_ref_price：無空值')
    return bad


if __name__ == '__main__':
    import polars as pl
    from datetime import date

    assert len(CASH_DIVIDENDS_SCHEMA) == 26
    assert len(CASH_DIVIDENDS_KEEP_SCHEMA) == 5
    assert set(RENAME_MAP) == set(CASH_DIVIDENDS_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in CASH_DIVIDENDS_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert CASH_DIVIDENDS_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))
    assert keep_col == [en for en, _ in CASH_DIVIDENDS_KEEP_SCHEMA.values()]
    assert list(CASH_DIVIDENDS_SCHEMA)[: len(CASH_DIVIDENDS_KEEP_SCHEMA)] == list(
        CASH_DIVIDENDS_KEEP_SCHEMA
    )

    # ponytail: 最小自檢
    _t = pl.DataFrame(
        {
            'symbol': ['1101', '1102'],
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'dividend_per_share': [1.0, 2.0],
            'prev_close': [50.0, None],
            'ex_div_ref_price': [49.0, 48.0],
        }
    )
    _bad = check_price_nulls(_t)
    assert _bad.height == 1 and _bad['symbol'].to_list() == ['1102']
    assert check_price_nulls(_t.drop_nulls('prev_close')).height == 0
    print('ok')
