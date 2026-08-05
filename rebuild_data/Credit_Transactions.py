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

# 其餘欄位（讀檔仍可用完整 SCHEMA；餘額張數僅供算償還／券資比，不進 keep_col）
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

# 預處理
""" 
margin_maintenance_ratio的na是因為沒有成本造成的 不處理
short_maintenance_ratio的na是因為沒有成本造成的 不處理
repay ratio同理
"""
 


# 無交易／成交量為 0／餘額未變 → 缺失視為 0
ZERO_FILL_COLS = (
    'margin_buy_lot',
    'margin_sell_lot',
    'margin_cash_repay_lot',
    'short_buy_lot',
    'short_sell_lot',
    'short_stock_repay_lot',
    'margin_volume_pct',
    'short_volume_pct',
    'margin_change_ratio',
    'short_change_ratio',
)


def add_credit_ratios(df):
    """缺失填 0（ZERO_FILL_COLS）後，算償還／餘額比率；餘額≤0 時比率為 null。

    需已有英文欄 margin_cash_repay_lot / margin_balance_lot、
    short_stock_repay_lot / short_balance_lot（read_tej_txt 後）。
    """
    import polars as pl

    df = df.with_columns(pl.col(c).fill_null(0) for c in ZERO_FILL_COLS)
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


def encode_marginable(df):
    """可信用交易 Y → 1，空值／其餘 → 0。"""
    import polars as pl

    return df.with_columns(
        pl.when(pl.col('marginable') == 'Y')
        .then(1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias('marginable')
    )


def fix_short_to_margin_ratio(df):
    """券資比＝融券餘額/融資餘額；融資餘額為 0 時 TEJ 留 null，補 0。

    僅在 margin_balance_lot==0 且 short_to_margin_ratio 為 null 時補 0；
    其餘 null（如有融資餘額卻缺值）保留，避免掩蓋真缺失。
    """
    import polars as pl

    return df.with_columns(
        pl.when(
            (pl.col('margin_balance_lot') == 0)
            & pl.col('short_to_margin_ratio').is_null()
        )
        .then(0.0)
        .otherwise(pl.col('short_to_margin_ratio'))
        .alias('short_to_margin_ratio')
    )


def summarize_cost_na_vs_maintenance(df):
    """打印：maintenance_ratio 為 NA 時，cost 為 NA／為 0 的比例。"""
    import polars as pl

    for label, cost_col, maint_col in (
        ('margin', 'margin_balance_lot', 'margin_cash_repay_ratio'),
        ('short', 'short_balance_lot', 'short_stock_repay_ratio'),
    ):
        subset = df.filter(pl.col(maint_col).is_null())
        n = subset.height
        if n == 0:
            print(f'{label}: repay_ratio_na=0, balance_lot=n/a, balance_0=n/a')
            continue
        cost_na = subset.filter(pl.col(cost_col).is_null()).height
        cost_0 = subset.filter(pl.col(cost_col) == 0).height
        print(
            f'{label}: repay_ratio_na={n}, '
            f'balance_lot={cost_na} ({cost_na / n:.2%}), '
            f'balance_0={cost_0} ({cost_0 / n:.2%})'
        )


def process_credit_transactions(df):
    """融資融券處理入口：可信用編碼 → 填 0／償還比率 → 券資比補 0 → 診斷打印 → 保留 keep_col。"""
    df = encode_marginable(df)
    df = add_credit_ratios(df)
    df = fix_short_to_margin_ratio(df)
    summarize_cost_na_vs_maintenance(df)
    return df.select(keep_col)


def fill_margin_net_buy_lot_with_zero(df):
    """untradable=0 且 marginable=1 → margin_net_buy_lot 填 0（對齊 rebuild）。"""
    import polars as pl

    if 'margin_net_buy_lot' not in df.columns:
        print("找不到欄位 'margin_net_buy_lot'，無法填入 0")
        return df
    mask = (pl.col('untradable') == 0) & (pl.col('marginable') == 1)
    return df.with_columns(
        pl.when(mask)
        .then(0)
        .otherwise(pl.col('margin_net_buy_lot'))
        .alias('margin_net_buy_lot')
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
    assert 'margin_balance_lot' not in keep_col  # 僅供中間計算

    # ponytail: 最小自檢；邏輯破了會 fail
    _n = 3
    _t = process_credit_transactions(
        pl.DataFrame(
            {
                **{en: [None] * _n for en, _ in CREDIT_TRANSACTIONS_KEEP_SCHEMA.values()},
                'marginable': ['Y', None, 'N'],
                'margin_buy_lot': [None, 1.0, 0.0],
                'margin_sell_lot': [None, 0.0, 0.0],
                'margin_cash_repay_lot': [None, 2.0, 5.0],
                'short_buy_lot': [None, 0.0, 0.0],
                'short_sell_lot': [None, 1.0, 0.0],
                'short_stock_repay_lot': [None, 3.0, 1.0],
                'margin_volume_pct': [None, 5.0, 0.0],
                'short_volume_pct': [None, 1.0, 0.0],
                'margin_change_ratio': [None, 0.1, 0.0],
                'short_change_ratio': [None, -0.2, 0.0],
                'short_to_margin_ratio': [None, 0.5, None],
                # 中間欄（不進 keep_col）；cost 供 process 末診斷打印
                'margin_balance_lot': [10.0, 10.0, 0.0],
                'short_balance_lot': [12.0, 12.0, -1.0],
                'margin_cost_per_share': [None, 0.0, 1.0],
                'short_cost_per_share': [None, 0.0, None],
                # KEEP 預設全 None；覆寫讓 short 有一筆非 NA maintenance
                'margin_maintenance_ratio': [None, None, None],
                'short_maintenance_ratio': [None, None, 110.0],
            }
        )
    )
    assert _t.columns == keep_col
    assert 'margin_balance_lot' not in _t.columns
    assert _t['marginable'].to_list() == [1, 0, 0]
    assert _t['margin_buy_lot'].to_list() == [0.0, 1.0, 0.0]
    assert _t['margin_cash_repay_lot'].to_list() == [0.0, 2.0, 5.0]
    assert _t['margin_volume_pct'].to_list() == [0.0, 5.0, 0.0]
    assert _t['margin_change_ratio'].to_list() == [0.0, 0.1, 0.0]
    assert _t['margin_cash_repay_ratio'].to_list() == [0.0, 0.2, None]
    assert _t['short_stock_repay_ratio'].to_list() == [0.0, 0.25, None]
    # 券資比：融資餘額 0 且 null → 0；有融資餘額的 null 保留；非 null 不動
    assert _t['short_to_margin_ratio'].to_list() == [None, 0.5, 0.0]
    print('ok')
