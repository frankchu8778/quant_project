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

keep_col = [
    *[en for en, _ in CASH_DIVIDENDS_KEEP_SCHEMA.values()],
    'adj_factor',
]



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


def add_adj_factor(df):
    """adj_factor = prev_close / ex_div_ref_price；價缺或 ≤0 → null。"""
    import polars as pl

    ok = (
        pl.col('prev_close').is_not_null()
        & (pl.col('prev_close') > 0)
        & pl.col('ex_div_ref_price').is_not_null()
        & (pl.col('ex_div_ref_price') > 0)
    )
    return df.with_columns(
        pl.when(ok)
        .then(pl.col('prev_close') / pl.col('ex_div_ref_price'))
        .otherwise(None)
        .alias('adj_factor')
    )


def process_cash_dividends(df):
    """現金股息處理入口：查價空值 → 算 adj_factor → 保留 keep_col。"""
    check_price_nulls(df)
    return add_adj_factor(df).select(keep_col)


def align_to_ohlcv(df, ohlcv_df):
    """只留 OHLCV 有 (symbol, date) 的除息列（停牌日無價無法掛 adj）。"""
    import polars as pl

    pairs = ohlcv_df.select(['symbol', 'date']).unique()
    before = df.height
    out = df.join(pairs, on=['symbol', 'date'], how='semi')
    dropped = before - out.height
    if dropped:
        print(f'cash dividend 無 OHLCV pair：drop {dropped} 筆')
    return out


def dedupe_same_day(df):
    """同日多筆：prev_close / ex_div_ref_price / adj_factor 皆一致 → keep first；否則 raise。"""
    import polars as pl

    if df.height == 0:
        return df
    dup = (
        df.group_by(['symbol', 'date'])
        .len()
        .filter(pl.col('len') > 1)
        .sort(['symbol', 'date'])
    )
    if dup.height == 0:
        return df

    price_bad = (
        df.join(dup.select(['symbol', 'date']), on=['symbol', 'date'], how='inner')
        .group_by(['symbol', 'date'])
        .agg(
            pl.col('prev_close').n_unique().alias('n_prev'),
            pl.col('ex_div_ref_price').n_unique().alias('n_ref'),
            pl.col('adj_factor').n_unique().alias('n_adj'),
        )
        .filter(
            (pl.col('n_prev') > 1)
            | (pl.col('n_ref') > 1)
            | (pl.col('n_adj') > 1)
        )
    )
    if price_bad.height:
        print('同日重複配息但價格／adj 不一致：')
        print(price_bad)
        print(
            df.join(price_bad.select(['symbol', 'date']), on=['symbol', 'date'], how='inner')
            .sort(['symbol', 'date'])
        )
        raise ValueError(
            f'cash dividend 有 {price_bad.height} 組同日價格不一致，無法自動去重'
        )

    print(f'同日重複配息 {dup.height} 組：價格相同 → keep first')
    return df.unique(subset=['symbol', 'date'], keep='first')


def prepare_for_merge(df, ohlcv_df):
    """日更合併前：對齊 OHLCV → 同日去重 → 只留有 adj 的列（含 ex_div_ref_price）。"""
    import polars as pl

    out = align_to_ohlcv(df, ohlcv_df)
    out = dedupe_same_day(out)
    out = out.filter(pl.col('adj_factor').is_not_null()).select(
        ['symbol', 'date', 'adj_factor', 'ex_div_ref_price']
    )
    return out


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
    assert keep_col[:-1] == [en for en, _ in CASH_DIVIDENDS_KEEP_SCHEMA.values()]
    assert keep_col[-1] == 'adj_factor'
    assert list(CASH_DIVIDENDS_SCHEMA)[: len(CASH_DIVIDENDS_KEEP_SCHEMA)] == list(
        CASH_DIVIDENDS_KEEP_SCHEMA
    )

    # ponytail: 最小自檢
    _t = pl.DataFrame(
        {
            'symbol': ['1101', '1102', '1103'],
            'date': [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            'dividend_per_share': [1.0, 2.0, 3.0],
            'prev_close': [50.0, None, 40.0],
            'ex_div_ref_price': [49.0, 48.0, 0.0],
        }
    )
    _bad = check_price_nulls(_t)
    assert _bad.height == 1 and _bad['symbol'].to_list() == ['1102']
    assert check_price_nulls(_t.filter(pl.col('prev_close').is_not_null())).height == 0

    _adj = add_adj_factor(_t)['adj_factor'].to_list()
    assert _adj[0] == 50.0 / 49.0 and _adj[1] is None and _adj[2] is None

    _out = process_cash_dividends(_t)
    assert _out.columns == keep_col
    assert _out.height == 3

    _ohlcv = pl.DataFrame(
        {'symbol': ['1101'], 'date': [date(2024, 1, 1)]}
    )
    _prep = prepare_for_merge(_out, _ohlcv)
    assert _prep.height == 1 and _prep.columns == [
        'symbol',
        'date',
        'adj_factor',
        'ex_div_ref_price',
    ]
    _dup = pl.concat([_out.filter(pl.col('symbol') == '1101')] * 2)
    assert dedupe_same_day(_dup).height == 1
    print('ok')
