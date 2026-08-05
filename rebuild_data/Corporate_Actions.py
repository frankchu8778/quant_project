# TEJ 資本形成（Corporate_Actions）：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 說明：https://www.tej.com.tw/tejdoc/db-document/tw/wstk1.html
# 注意：TEJ 原始欄名「股份轉換(仟股」缺右括號，必須照檔頭寫
TEJ_DATE_FORMAT = '%Y%m%d'

# 保留欄位（除權／減資／配股復權常用）— 順序在完整 SCHEMA 最前
CORPORATE_ACTIONS_KEEP_SCHEMA = {
    # tej_symbol：空白前為代碼（如 "1268 漢來美食" → "1268"）
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('date', 'datetime64[ns]'),
    '現金增資(仟股)': ('cash_capital_increase_thousand', 'float64'),
    '盈餘增資(仟股)': ('retained_earnings_increase_thousand', 'float64'),
    '公積增資(仟股)': ('capital_reserve_increase_thousand', 'float64'),
    '減資(仟股)': ('capital_reduction_thousand', 'float64'),
    '減資每股退還現金': ('capital_reduction_cash_per_share', 'float64'),
    '減資率 %': ('capital_reduction_rate', 'float64'),
    '變更股票面額股數(仟股)': ('par_value_change_shares_thousand', 'float64'),
    '變更股票面額換股率': ('par_value_change_ratio', 'float64'),
    '現金認購率 %': ('cash_subscription_rate', 'float64'),
    '現金認購價（元）': ('cash_subscription_price', 'float64'),
    '盈餘配股率 %': ('retained_earnings_stock_rate', 'float64'),
    '公積配股率 %': ('capital_reserve_stock_rate', 'float64'),
    '除權參考價（元）': ('ex_rights_ref_price', 'float64'),
    '前日收盤價（元）': ('prev_close', 'float64'),
    '配股(Y/N)': ('stock_dividend_yn', 'string'),
    '私募(Y/N)': ('private_placement_yn', 'string'),
}

# 其餘欄位（讀檔仍可用完整 SCHEMA；不進 keep_col）
_CORPORATE_ACTIONS_REST_SCHEMA = {
    '總股本(仟元)': ('total_capital_thousand', 'float64'),
    '面額': ('par_value', 'float64'),
    '幣別': ('currency', 'string'),
    '總股數(仟股)': ('total_shares_thousand', 'float64'),
    '可配股總股數(仟股)': ('distributable_shares_thousand', 'float64'),
    '員工分紅(仟股)': ('employee_bonus_shares_thousand', 'float64'),
    '証券轉換_可轉債(仟股)': ('cb_conversion_shares_thousand', 'float64'),
    '証券轉換_特別股(仟股)': ('pref_conversion_shares_thousand', 'float64'),
    # TEJ 原始欄名缺右括號
    '股份轉換(仟股': ('share_swap_thousand', 'float64'),
    '庫藏股註銷(仟股)': ('treasury_cancel_thousand', 'float64'),
    '限制員工權利新股註銷(仟股)': ('rsa_cancel_thousand', 'float64'),
    '合併(仟股)': ('merger_shares_thousand', 'float64'),
    '受讓(仟股)': ('transfer_shares_thousand', 'float64'),
    '員工認股權證(仟股)': ('eso_shares_thousand', 'float64'),
    '限制員工權利新股(仟股)': ('rsa_shares_thousand', 'float64'),
    '其它(仟股)': ('other_shares_thousand', 'float64'),
    '員工配股率 %': ('employee_stock_rate', 'float64'),
    'CB轉換價 (元)': ('cb_conversion_price', 'float64'),
    '員工認購率 %': ('employee_subscription_rate', 'float64'),
    '公開承銷率 %': ('public_underwriting_rate', 'float64'),
    '圈購比率 %': ('book_building_rate', 'float64'),
    'GDR 比率 %': ('gdr_rate', 'float64'),
    '特定比率 %': ('specific_rate', 'float64'),
    '增減資公告日': ('capital_change_announce_date', 'datetime64[ns]'),
    '股東會決議日': ('shareholder_meeting_date', 'datetime64[ns]'),
    '證管會核准日': ('sfc_approval_date', 'datetime64[ns]'),
    '停止過戶-起': ('book_closure_start', 'datetime64[ns]'),
    '停止過戶-迄': ('book_closure_end', 'datetime64[ns]'),
    '原股東繳款-起': ('shareholder_payment_start', 'datetime64[ns]'),
    '原股東繳款-迄': ('shareholder_payment_end', 'datetime64[ns]'),
    '現增催繳起日': ('cash_call_start', 'datetime64[ns]'),
    '現增催繳迄日': ('cash_call_end', 'datetime64[ns]'),
    '繳款憑證公告日': ('payment_certificate_announce_date', 'datetime64[ns]'),
    '繳款憑證發放日': ('payment_certificate_issue_date', 'datetime64[ns]'),
    '繳款憑證上市日': ('payment_certificate_list_date', 'datetime64[ns]'),
    '現增股票公告日': ('cash_increase_stock_announce_date', 'datetime64[ns]'),
    '現增股票發放日': ('cash_increase_stock_issue_date', 'datetime64[ns]'),
    '現增股票上市日': ('cash_increase_stock_list_date', 'datetime64[ns]'),
    '權利證書公告日': ('rights_certificate_announce_date', 'datetime64[ns]'),
    '權利證書發放日': ('rights_certificate_issue_date', 'datetime64[ns]'),
    '權利證書上市日': ('rights_certificate_list_date', 'datetime64[ns]'),
    '員工紅利增資股公告日': ('employee_bonus_announce_date', 'datetime64[ns]'),
    '員工紅利增資股發放日': ('employee_bonus_issue_date', 'datetime64[ns]'),
    '員工紅利增資股上市日': ('employee_bonus_list_date', 'datetime64[ns]'),
    '股票股利公告日': ('stock_dividend_announce_date', 'datetime64[ns]'),
    '股票股利發放日': ('stock_dividend_issue_date', 'datetime64[ns]'),
    '股票股利上市日': ('stock_dividend_list_date', 'datetime64[ns]'),
    '最後過戶日': ('last_transfer_date', 'datetime64[ns]'),
    '停止融資日-起': ('margin_buy_suspend_start', 'datetime64[ns]'),
    '停止融資(券)日-迄': ('margin_suspend_end', 'datetime64[ns]'),
    '停止融券日-起': ('margin_sell_suspend_start', 'datetime64[ns]'),
    '融券最後回補日': ('short_cover_deadline', 'datetime64[ns]'),
    '現金增資失敗否': ('cash_increase_failed', 'string'),
    '增資失敗原因': ('capital_increase_fail_reason', 'string'),
    '其他-說明': ('other_note', 'string'),
    '減資現金退款日': ('capital_reduction_refund_date', 'datetime64[ns]'),
}

# 完整 schema：保留欄位在上
CORPORATE_ACTIONS_SCHEMA = {
    **CORPORATE_ACTIONS_KEEP_SCHEMA,
    **_CORPORATE_ACTIONS_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in CORPORATE_ACTIONS_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in CORPORATE_ACTIONS_SCHEMA.items()}

db_doc_url = 'https://www.tej.com.tw/tejdoc/db-document/tw/wstk1.html'

keep_col = [en for en, _ in CORPORATE_ACTIONS_KEEP_SCHEMA.values()]


def process_stock_dividend(df):
    """配股復權入口：盈餘／公積增資 → adj_factor = prev_close / ex_rights_ref_price。

    排除私募；現金增資不納入。輸出 symbol / date / adj_factor / ref_price；
    (symbol, date) 重複則 raise。
    回傳 (df, has_stock_dividend)；無資料時 has_stock_dividend=False，後續合併可跳過。
    """
    import polars as pl

    has_stock_dividend_increase = (
        (
            pl.col('retained_earnings_increase_thousand').is_not_null()
            & (pl.col('retained_earnings_increase_thousand') != 0)
        )
        | (
            pl.col('capital_reserve_increase_thousand').is_not_null()
            & (pl.col('capital_reserve_increase_thousand') != 0)
        )
    )
    has_prices = (
        pl.col('ex_rights_ref_price').is_not_null()
        & (pl.col('ex_rights_ref_price') > 0)
        & pl.col('prev_close').is_not_null()
        & (pl.col('prev_close') > 0)
    )

    out = (
        df.filter(pl.col('private_placement_yn').fill_null('N') != 'Y')
        .filter(has_stock_dividend_increase & has_prices)
        .select(
            [
                'symbol',
                'date',
                (pl.col('prev_close') / pl.col('ex_rights_ref_price')).alias('adj_factor'),
                pl.col('ex_rights_ref_price').alias('ref_price'),
            ]
        )
        .sort(['symbol', 'date'])
    )

    has_stock_dividend = out.height > 0
    if not has_stock_dividend:
        print('無配股資料，跳過後續配股合併')
        return out, False

    dup = out.group_by(['symbol', 'date']).len().filter(pl.col('len') > 1)
    if dup.height:
        print(dup)
        print(out.join(dup.select(['symbol', 'date']), on=['symbol', 'date'], how='inner'))
        raise ValueError(f'配股 adj_factor 有 {dup.height} 組重複 (symbol, date)')
    print(f'配股 adj_factor 唯一 OK，筆數: {out.height}')
    return out, True


_HALT_ADJ_ONLY_COLS = [
    'symbol',
    'date',
    'adj_factor',
    'ref_price',
    'event_date',
    'start_halt',
    'resume_trading_date',
]
_HALT_ADJ_HALT_COLS = [
    'symbol',
    'event_date',
    'start_halt',
    'resume_trading_date',
    'adj_factor',
    'ref_price',
]
# 舊名別名（自檢／外部若仍引用）
_CAP_RED_ONLY_COLS = _HALT_ADJ_ONLY_COLS
_CAP_RED_HALT_COLS = _HALT_ADJ_HALT_COLS


def _empty_halt_adj_frames(pl):
    """無事件時回傳同欄位空表。"""
    only = pl.DataFrame(
        schema={
            'symbol': pl.Utf8,
            'date': pl.Date,
            'adj_factor': pl.Float64,
            'ref_price': pl.Float64,
            'event_date': pl.Date,
            'start_halt': pl.Date,
            'resume_trading_date': pl.Date,
        }
    )
    halt = pl.DataFrame(
        schema={
            'symbol': pl.Utf8,
            'event_date': pl.Date,
            'start_halt': pl.Date,
            'resume_trading_date': pl.Date,
            'adj_factor': pl.Float64,
            'ref_price': pl.Float64,
        }
    )
    return only, halt


def _process_halt_adj_events(event_rows, trading_halt_df, label):
    """共用：算 adj_factor → 對停牌 → 掛恢復日／事件日 → 唯一檢查。

    event_rows 已篩好事件列。回傳 (only_df, halt_df, has_data)。
    """
    import polars as pl

    total_rows = event_rows.height
    if total_rows == 0:
        print(f'無{label}資料，跳過後續{label}流程')
        only, halt = _empty_halt_adj_frames(pl)
        return only, halt, False

    ok = (
        pl.col('prev_close').is_not_null()
        & (pl.col('prev_close') > 0)
        & pl.col('ex_rights_ref_price').is_not_null()
        & (pl.col('ex_rights_ref_price') > 0)
    )
    ev = event_rows.with_columns(
        pl.when(ok)
        .then(pl.col('prev_close') / pl.col('ex_rights_ref_price'))
        .otherwise(None)
        .alias('adj_factor'),
        pl.col('ex_rights_ref_price').alias('ref_price'),
    )
    bad = ev.filter(pl.col('adj_factor').is_null())
    if bad.height:
        print(f'{label} adj_factor null：{bad.height} 筆（仍可進停牌對照，但無因子）')
        print(bad.select(['symbol', 'date', 'prev_close', 'ex_rights_ref_price']))

    pairs = ev.select(['symbol', 'date', 'adj_factor', 'ref_price']).with_row_index('row_idx')
    joined = pairs.join(
        trading_halt_df.select(['symbol', 'start_halt', 'resume_trading_date']),
        on='symbol',
        how='inner',
    )
    in_suspension = joined.filter(
        (pl.col('date') >= pl.col('start_halt'))
        & (
            pl.col('resume_trading_date').is_null()
            | (pl.col('date') < pl.col('resume_trading_date'))
        )
    )
    halt_df = (
        in_suspension.select(
            [
                'symbol',
                pl.col('date').alias('event_date'),
                'start_halt',
                'resume_trading_date',
                'adj_factor',
                'ref_price',
            ]
        )
        .unique()
        .sort(['symbol', 'event_date', 'start_halt'])
    )
    print(
        f'{label}總筆數：{ev.height}；'
        f'落在停牌區間：{halt_df.height}；'
        f'有恢復日：{halt_df.filter(pl.col("resume_trading_date").is_not_null()).height}；'
        f'有 adj_factor：{halt_df.filter(pl.col("adj_factor").is_not_null()).height}'
    )

    suspended = halt_df.filter(
        pl.col('resume_trading_date').is_not_null() & pl.col('adj_factor').is_not_null()
    ).select(
        [
            'symbol',
            pl.col('resume_trading_date').alias('date'),
            'adj_factor',
            'ref_price',
            pl.col('event_date'),
            'start_halt',
            'resume_trading_date',
        ]
    )
    in_halt_events = halt_df.select(['symbol', pl.col('event_date').alias('date')]).unique()
    not_suspended = (
        ev.filter(pl.col('adj_factor').is_not_null())
        .join(in_halt_events, on=['symbol', 'date'], how='anti')
        .select(
            [
                'symbol',
                'date',
                'adj_factor',
                'ref_price',
                pl.col('date').alias('event_date'),
                pl.lit(None).cast(pl.Date).alias('start_halt'),
                pl.lit(None).cast(pl.Date).alias('resume_trading_date'),
            ]
        )
    )
    only_df = (
        pl.concat([suspended, not_suspended], how='diagonal_relaxed')
        .select(_HALT_ADJ_ONLY_COLS)
        .sort(['symbol', 'date'])
    )
    print(
        f'{label}_only：{suspended.height} 筆掛恢復日、'
        f'{not_suspended.height} 筆掛事件日、合計 {only_df.height}'
    )

    dup = (
        only_df.group_by(['symbol', 'date'])
        .len()
        .filter(pl.col('len') > 1)
        .sort(['symbol', 'date'])
    )
    if dup.height:
        print(f'{label}_only 重複 (symbol, date)：')
        print(dup)
        print(
            only_df.join(dup.select(['symbol', 'date']), on=['symbol', 'date'], how='inner').sort(
                ['symbol', 'date']
            )
        )
        raise ValueError(f'{label}_only 有 {dup.height} 組重複 (symbol, date)')
    print(f'{label}_only 唯一 OK，筆數: {only_df.height}')

    has_data = only_df.height > 0
    if not has_data:
        print(f'{label}無有效 adj_factor，跳過後續{label}合併')
    return only_df, halt_df.select(_HALT_ADJ_HALT_COLS), has_data


def filter_rights_vs_cash_overlap(rights_df, cash_df, *, cash_ref_col='ex_div_ref_price'):
    """同日除息×權利：參考價相同 → 丟掉權利側；不同 → raise。

    rights_df 需有 ref_price；cash_df 需有 cash_ref_col（可空表）。
    回傳可 join 的 rights（symbol / date / adj_factor）。
    """
    import polars as pl

    base = rights_df.select(['symbol', 'date', 'adj_factor', 'ref_price'])
    if cash_df is None or cash_df.height == 0:
        return base.select(['symbol', 'date', 'adj_factor'])

    cash_meta = (
        cash_df.filter(pl.col('adj_factor').is_not_null())
        .select(
            [
                'symbol',
                'date',
                pl.col(cash_ref_col).alias('cash_ref'),
                pl.col('adj_factor').alias('cash_adj'),
            ]
        )
    )
    overlap = base.join(cash_meta, on=['symbol', 'date'], how='inner')
    same = overlap.filter(pl.col('ref_price') == pl.col('cash_ref'))
    diff = overlap.filter(pl.col('ref_price') != pl.col('cash_ref'))
    if same.height:
        print(f'同日同參考價 {same.height} 筆 → 丟掉權利側、保留現金除息')
        print(
            same.select(
                ['symbol', 'date', 'ref_price', 'cash_ref', 'adj_factor', 'cash_adj']
            ).sort(['symbol', 'date'])
        )
    if diff.height:
        print(
            diff.select(
                ['symbol', 'date', 'ref_price', 'cash_ref', 'adj_factor', 'cash_adj']
            ).sort(['symbol', 'date'])
        )
        raise ValueError(
            f'同日除息×權利參考價不同 {diff.height} 筆，禁止自動相乘'
        )
    return (
        base.join(same.select(['symbol', 'date']), on=['symbol', 'date'], how='anti')
        .select(['symbol', 'date', 'adj_factor'])
    )


def process_capital_reduction(ex_rights_df, trading_halt_df, exclude_pairs=None):
    """減資復權入口：算 adj_factor，停牌內事件掛恢復日，其餘掛事件日。

    trading_halt_df：日更請傳 load_halt_calendar（累積），勿只傳當日 zip。
    exclude_pairs：通常為配股已佔用的 (symbol, date)，anti-join 掉。
    回傳 (capital_reduction_only_df, capital_reduction_halt_df, has_capital_reduction)。
    """
    import polars as pl

    df = ex_rights_df
    if exclude_pairs is not None and exclude_pairs.height:
        df = df.join(exclude_pairs.select(['symbol', 'date']), on=['symbol', 'date'], how='anti')

    cap_rows = df.filter(
        pl.col('capital_reduction_thousand').is_not_null()
        & (pl.col('capital_reduction_thousand') > 0)
    )
    has_both = cap_rows.filter(
        pl.col('ex_rights_ref_price').is_not_null() & pl.col('prev_close').is_not_null()
    )
    print(f'capital_reduction_thousand 有值 (非空且大於0) 的資料筆數: {cap_rows.height}')
    print(f'其中 ex_rights_ref_price 和 prev_close 皆不為空的筆數: {has_both.height}')
    if cap_rows.height:
        print(f'比例: {has_both.height / cap_rows.height:.2%}')

    return _process_halt_adj_events(cap_rows, trading_halt_df, '減資')


def process_par_value_change(ex_rights_df, trading_halt_df, exclude_pairs=None):
    """面額變更復權入口：同減資流程（停牌掛恢復日／其餘掛事件日）。

    trading_halt_df：日更請傳 load_halt_calendar（累積），勿只傳當日 zip。
    exclude_pairs：通常為配股已佔用的 (symbol, date)，anti-join 掉。
    回傳 (par_value_change_only_df, par_value_change_halt_df, has_par_value_change)。
    """
    import polars as pl

    df = ex_rights_df
    if exclude_pairs is not None and exclude_pairs.height:
        df = df.join(exclude_pairs.select(['symbol', 'date']), on=['symbol', 'date'], how='anti')

    par_rows = df.filter(
        pl.col('par_value_change_shares_thousand').is_not_null()
        & (pl.col('par_value_change_shares_thousand') > 0)
    )
    return _process_halt_adj_events(par_rows, trading_halt_df, '面額變更')


def load_capital_reduction_calendar(calendar_path):
    """讀 pending 復權 JSON（減資／面額等）→ only_df 形狀（date = resume）。

    欄位：symbol / date / adj_factor / resume_trading_date（+ 可選 start_halt / event_date）。
    檔不存在或空 → 同 schema 空表。
    """
    import json
    from datetime import date as date_cls
    from pathlib import Path

    import polars as pl

    empty = _empty_halt_adj_frames(pl)[0]
    path = Path(calendar_path)
    if not path.is_file() or path.stat().st_size == 0:
        return empty

    records = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        return empty

    rows = []
    for r in records:
        resume = r.get('resume_trading_date')
        if not resume or r.get('adj_factor') is None:
            continue
        resume_d = date_cls.fromisoformat(resume)
        rows.append(
            {
                'symbol': str(r.get('symbol', '')),
                'date': resume_d,
                'adj_factor': float(r['adj_factor']),
                'ref_price': (
                    float(r['ref_price']) if r.get('ref_price') is not None else None
                ),
                'event_date': (
                    date_cls.fromisoformat(r['event_date'])
                    if r.get('event_date')
                    else None
                ),
                'start_halt': (
                    date_cls.fromisoformat(r['start_halt'])
                    if r.get('start_halt')
                    else None
                ),
                'resume_trading_date': resume_d,
            }
        )
    if not rows:
        return empty
    return pl.DataFrame(rows).select(_HALT_ADJ_ONLY_COLS).with_columns(
        pl.col('date').cast(pl.Date),
        pl.col('event_date').cast(pl.Date),
        pl.col('start_halt').cast(pl.Date),
        pl.col('resume_trading_date').cast(pl.Date),
    )


def update_capital_reduction_calendar(only_df, calendar_path):
    """把有 resume + adj_factor 的列 upsert 進 pending 復權 JSON。

    鍵：symbol + start_halt（無 start_halt 則 symbol + resume_trading_date）。
    回傳本次新增筆數。
    """
    import json
    from pathlib import Path

    import polars as pl

    path = Path(calendar_path)
    if only_df is None or only_df.height == 0:
        return 0

    to_save = only_df.filter(
        pl.col('resume_trading_date').is_not_null() & pl.col('adj_factor').is_not_null()
    )
    if to_save.height == 0:
        return 0

    records: list[dict] = []
    if path.is_file() and path.stat().st_size > 0:
        loaded = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(loaded, list):
            records = loaded

    def _key(r):
        return (
            str(r.get('symbol')),
            r.get('start_halt') or '',
            r.get('resume_trading_date') or '',
        )

    index = {_key(r): i for i, r in enumerate(records)}
    added = 0
    for row in to_save.iter_rows(named=True):
        start = (
            row['start_halt'].isoformat() if row.get('start_halt') is not None else None
        )
        resume = row['resume_trading_date'].isoformat()
        event = (
            row['event_date'].isoformat() if row.get('event_date') is not None else None
        )
        entry = {
            'symbol': str(row['symbol']),
            'start_halt': start,
            'resume_trading_date': resume,
            'adj_factor': float(row['adj_factor']),
            'event_date': event,
            'ref_price': (
                float(row['ref_price']) if row.get('ref_price') is not None else None
            ),
        }
        key = _key(entry)
        if key in index:
            records[index[key]] = entry
        else:
            index[key] = len(records)
            records.append(entry)
            added += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return added


def prune_capital_reduction_calendar(ref_date, calendar_path):
    """依參考日修剪 pending 復權 JSON。

    ``resume_trading_date <= ref_date`` → 視為已掛上復權、從 JSON 拿掉。
    回傳移除筆數。
    """
    import json
    from datetime import date as date_cls
    from pathlib import Path

    path = Path(calendar_path)
    if ref_date is None:
        return 0
    if not path.is_file() or path.stat().st_size == 0:
        return 0

    records = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        return 0

    if hasattr(ref_date, 'isoformat') and not isinstance(ref_date, date_cls):
        ref_date = date_cls.fromisoformat(str(ref_date)[:10])

    kept = []
    dropped = []
    for r in records:
        resume = r.get('resume_trading_date')
        if resume:
            resume_d = date_cls.fromisoformat(resume)
            if resume_d <= ref_date:
                dropped.append(r)
                continue
        kept.append(r)

    if not dropped:
        return 0

    path.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        f'{path.name} 依日期 {ref_date} 移除已恢復 {len(dropped)} 筆：'
        f'{[(d.get("symbol"), d.get("resume_trading_date")) for d in dropped[:10]]}'
        + (' …' if len(dropped) > 10 else '')
    )
    return len(dropped)


# 面額變更共用同一套 pending JSON 讀寫（路徑不同）
load_par_value_change_calendar = load_capital_reduction_calendar
update_par_value_change_calendar = update_capital_reduction_calendar
prune_par_value_change_calendar = prune_capital_reduction_calendar


if __name__ == '__main__':
    import polars as pl
    from datetime import date

    assert len(CORPORATE_ACTIONS_SCHEMA) == 74
    assert len(CORPORATE_ACTIONS_KEEP_SCHEMA) == 18
    assert set(RENAME_MAP) == set(CORPORATE_ACTIONS_SCHEMA)
    assert set(DTYPE_MAP) == {en for en, _ in CORPORATE_ACTIONS_SCHEMA.values()}
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    assert CORPORATE_ACTIONS_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert '股份轉換(仟股' in CORPORATE_ACTIONS_SCHEMA
    assert len(DTYPE_MAP) == len(set(DTYPE_MAP))  # 英文名不重複
    assert keep_col == [en for en, _ in CORPORATE_ACTIONS_KEEP_SCHEMA.values()]
    assert list(CORPORATE_ACTIONS_SCHEMA)[: len(CORPORATE_ACTIONS_KEEP_SCHEMA)] == list(
        CORPORATE_ACTIONS_KEEP_SCHEMA
    )

    # ponytail: 最小自檢 — 配股
    _t = pl.DataFrame(
        {
            'symbol': ['1101', '1102', '1103', '1104'],
            'date': [date(2024, 1, 1)] * 4,
            'retained_earnings_increase_thousand': [100.0, 0.0, 50.0, 80.0],
            'capital_reserve_increase_thousand': [0.0, 200.0, None, None],
            'prev_close': [50.0, 40.0, 30.0, 60.0],
            'ex_rights_ref_price': [49.0, 38.0, 0.0, 55.0],
            'private_placement_yn': ['N', 'N', 'N', 'Y'],
            'cash_capital_increase_thousand': [0.0, 0.0, 0.0, 0.0],
        }
    )
    _out, _has_sd = process_stock_dividend(_t)
    assert _has_sd is True
    assert _out.columns == ['symbol', 'date', 'adj_factor', 'ref_price']
    assert _out['symbol'].to_list() == ['1101', '1102']
    assert abs(_out['adj_factor'][0] - 50.0 / 49.0) < 1e-12
    assert abs(_out['adj_factor'][1] - 40.0 / 38.0) < 1e-12
    assert _out['ref_price'].to_list() == [49.0, 38.0]
    _empty_sd, _has_sd0 = process_stock_dividend(_t.head(0))
    assert _has_sd0 is False and _empty_sd.height == 0

    # ponytail: 同日重疊 — 同參考價丟權利側；異價 raise
    _rights = pl.DataFrame(
        {
            'symbol': ['1101', '1102'],
            'date': [date(2024, 1, 1), date(2024, 1, 2)],
            'adj_factor': [1.1, 1.2],
            'ref_price': [49.0, 38.0],
        }
    )
    _cash = pl.DataFrame(
        {
            'symbol': ['1101'],
            'date': [date(2024, 1, 1)],
            'adj_factor': [1.05],
            'ex_div_ref_price': [49.0],
        }
    )
    _joined = filter_rights_vs_cash_overlap(_rights, _cash)
    assert _joined.height == 1 and _joined['symbol'][0] == '1102'
    try:
        filter_rights_vs_cash_overlap(
            _rights,
            pl.DataFrame(
                {
                    'symbol': ['1101'],
                    'date': [date(2024, 1, 1)],
                    'adj_factor': [1.05],
                    'ex_div_ref_price': [48.0],
                }
            ),
        )
        raise AssertionError('expected ValueError on diff ref')
    except ValueError:
        pass

    _empty_halt = pl.DataFrame(
        {
            'symbol': pl.Series([], dtype=pl.Utf8),
            'start_halt': pl.Series([], dtype=pl.Date),
            'resume_trading_date': pl.Series([], dtype=pl.Date),
        }
    )

    # ponytail: 最小自檢 — 減資
    _empty_only, _empty_halt_out, _has_cr0 = process_capital_reduction(
        pl.DataFrame(
            {
                'symbol': ['1101'],
                'date': [date(2024, 1, 1)],
                'capital_reduction_thousand': [None],
                'prev_close': [50.0],
                'ex_rights_ref_price': [40.0],
            }
        ),
        _empty_halt,
    )
    assert _has_cr0 is False
    assert _empty_only.height == 0 and _empty_halt_out.height == 0
    assert list(_empty_only.columns) == _HALT_ADJ_ONLY_COLS

    _halt = pl.DataFrame(
        {
            'symbol': ['2330'],
            'start_halt': [date(2024, 1, 1)],
            'resume_trading_date': [date(2024, 1, 10)],
        }
    )
    _only, _halt_out, _has_cr = process_capital_reduction(
        pl.DataFrame(
            {
                'symbol': ['2330', '1101'],
                'date': [date(2024, 1, 5), date(2024, 2, 1)],
                'capital_reduction_thousand': [100.0, 50.0],
                'prev_close': [100.0, 50.0],
                'ex_rights_ref_price': [80.0, 40.0],
            }
        ),
        _halt,
    )
    assert _has_cr is True and _only.height == 2
    assert _only.filter(pl.col('symbol') == '2330')['date'][0] == date(2024, 1, 10)
    assert _halt_out.height == 1

    # ponytail: 最小自檢 — 面額變更
    _empty_par, _empty_par_halt, _has_par0 = process_par_value_change(
        pl.DataFrame(
            {
                'symbol': ['1101'],
                'date': [date(2024, 1, 1)],
                'par_value_change_shares_thousand': [None],
                'prev_close': [50.0],
                'ex_rights_ref_price': [40.0],
            }
        ),
        _empty_halt,
    )
    assert _has_par0 is False and _empty_par.height == 0

    _par_only, _par_halt, _has_par = process_par_value_change(
        pl.DataFrame(
            {
                'symbol': ['2330', '1101'],
                'date': [date(2024, 1, 5), date(2024, 3, 1)],
                'par_value_change_shares_thousand': [1000.0, 500.0],
                'prev_close': [200.0, 100.0],
                'ex_rights_ref_price': [100.0, 50.0],
            }
        ),
        _halt,
    )
    assert _has_par is True and _par_only.height == 2
    _p2330 = _par_only.filter(pl.col('symbol') == '2330').row(0, named=True)
    assert _p2330['date'] == date(2024, 1, 10)
    assert abs(_p2330['adj_factor'] - 2.0) < 1e-12
    assert _par_halt.height == 1

    # ponytail: 最小自檢 — capital_reduction.json
    import json
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as _tmp:
        _cal = Path(_tmp) / 'capital_reduction.json'
        _suspended = _only.filter(pl.col('resume_trading_date').is_not_null())
        assert update_capital_reduction_calendar(_suspended, _cal) == 1
        assert update_capital_reduction_calendar(_suspended, _cal) == 0  # upsert
        _loaded = load_capital_reduction_calendar(_cal)
        assert _loaded.height == 1
        assert _loaded['symbol'][0] == '2330'
        assert _loaded['date'][0] == date(2024, 1, 10)
        assert abs(_loaded['adj_factor'][0] - 100.0 / 80.0) < 1e-12
        # 未到恢復日 → 不刪
        assert prune_capital_reduction_calendar(date(2024, 1, 9), _cal) == 0
        assert load_capital_reduction_calendar(_cal).height == 1
        # 恢復當天 → 刪掉
        assert prune_capital_reduction_calendar(date(2024, 1, 10), _cal) == 1
        assert load_capital_reduction_calendar(_cal).height == 0
        assert json.loads(_cal.read_text(encoding='utf-8')) == []

    print('ok')
