# TEJ 暫停交易：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
# 每日下載常見異名（証券代碼 / 暫停交易起日）由 parse.TEJ_COLUMN_ALIASES 對應
TEJ_DATE_FORMAT = '%Y%m%d'

TRADING_HALT_KEEP_SCHEMA = {
    '證券代碼': ('symbol', 'tej_symbol'),
    '年月日': ('start_halt', 'datetime64[ns]'),  # 停牌首日；每日檔＝暫停交易起日
    '恢復交易日': ('resume_trading_date', 'datetime64[ns]'),  # 恢復首日；空＝尚未恢復
    '暫停交易原因': ('reason', 'string'),
}

TRADING_HALT_SCHEMA = dict(TRADING_HALT_KEEP_SCHEMA)

RENAME_MAP = {zh: en for zh, (en, _) in TRADING_HALT_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in TRADING_HALT_SCHEMA.items()}

keep_col = [en for en, _ in TRADING_HALT_KEEP_SCHEMA.values()]

# halt_calendar.json：reason 含「減資」→ avoid_early=T，否則 F
AVOID_EARLY_DEFAULT = 'F'
AVOID_EARLY_CHOICES = frozenset({'T', 'F'})


def avoid_early_from_reason(reason):
    """reason 字串含「減資」→ 'T'，否則 'F'。"""
    if reason is not None and '減資' in str(reason):
        return 'T'
    return AVOID_EARLY_DEFAULT


def load_halt_calendar(calendar_path):
    """讀 halt_calendar.json → DataFrame（供減資／面額停牌對照）。

    欄位：symbol / start_halt / resume_trading_date / reason。
    檔不存在或空 → 同 schema 空表。
    """
    import json
    from datetime import date as date_cls
    from pathlib import Path

    import polars as pl

    empty = pl.DataFrame(
        schema={
            'symbol': pl.Utf8,
            'start_halt': pl.Date,
            'resume_trading_date': pl.Date,
            'reason': pl.Utf8,
        }
    )
    path = Path(calendar_path)
    if not path.is_file() or path.stat().st_size == 0:
        return empty

    records = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        return empty

    rows = []
    for r in records:
        if not r.get('start_halt'):
            continue
        rows.append(
            {
                'symbol': str(r.get('symbol', '')),
                'start_halt': date_cls.fromisoformat(r['start_halt']),
                'resume_trading_date': (
                    date_cls.fromisoformat(r['resume_trading_date'])
                    if r.get('resume_trading_date')
                    else None
                ),
                'reason': r.get('reason'),
            }
        )
    if not rows:
        return empty
    return pl.DataFrame(rows).with_columns(
        pl.col('resume_trading_date').cast(pl.Date)
    )


def update_halt_calendar(df, calendar_path):
    """若 df 有停牌列，upsert 進 halt_calendar.json（鍵：symbol + start_halt）。

    每筆保留 start_halt / resume_trading_date（結束＝恢復交易日，可為 null）。
    ``avoid_early``：reason 含「減資」→ T，否則 F（寫入時一併校正既有列）。
    回傳本次新增筆數（更新既有不算新增）。
    """
    import json
    from pathlib import Path

    path = Path(calendar_path)
    if df is None or df.height == 0:
        return 0

    records: list[dict] = []
    if path.is_file() and path.stat().st_size > 0:
        loaded = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(loaded, list):
            records = loaded

    # 既有列依 reason 校正 avoid_early
    for r in records:
        r['avoid_early'] = avoid_early_from_reason(r.get('reason'))

    index = {
        (str(r.get('symbol')), r.get('start_halt')): i
        for i, r in enumerate(records)
    }
    added = 0
    for row in df.select(keep_col).iter_rows(named=True):
        start = row['start_halt'].isoformat() if row['start_halt'] is not None else None
        end = (
            row['resume_trading_date'].isoformat()
            if row['resume_trading_date'] is not None
            else None
        )
        key = (str(row['symbol']), start)
        entry = {
            'symbol': str(row['symbol']),
            'start_halt': start,
            'resume_trading_date': end,
            'reason': row['reason'],
            'avoid_early': avoid_early_from_reason(row['reason']),
        }
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


def apply_halt_calendar_to_ohlcv(ohlcv_df, calendar_path):
    """依 halt_calendar.json 標記 OHLCV 的 untradable / avoid_early。

    - symbol 在 OHLCV，且 date ∈ [start_halt, resume_trading_date)
      （resume 為 null → 開區間）→ ``untradable = 1``
    - reason 含「減資」：該 symbol 在 OHLCV 裡、嚴格早於 start_halt
      的最後一個交易日 → ``avoid_early = 1``（可提前出清）
    """
    import json
    from datetime import date as date_cls
    from pathlib import Path

    import polars as pl

    path = Path(calendar_path)
    if ohlcv_df is None or ohlcv_df.height == 0:
        return ohlcv_df
    if not path.is_file() or path.stat().st_size == 0:
        return ohlcv_df

    records = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        return ohlcv_df

    syms = set(ohlcv_df.get_column('symbol').unique().to_list())
    rows = []
    missing = []
    for r in records:
        sym = str(r.get('symbol', ''))
        if not r.get('start_halt'):
            continue
        if sym not in syms:
            missing.append(sym)
            continue
        avoid = avoid_early_from_reason(r.get('reason'))
        rows.append(
            {
                'symbol': sym,
                'start_halt': date_cls.fromisoformat(r['start_halt']),
                'resume_trading_date': (
                    date_cls.fromisoformat(r['resume_trading_date'])
                    if r.get('resume_trading_date')
                    else None
                ),
                'cal_avoid_early': 1 if avoid == 'T' else 0,
            }
        )
    if missing:
        print(
            f'halt_calendar 有 {len(missing)} 檔 symbol 不在本批 OHLCV'
            f'（無法標記）：{missing[:20]}'
            + (' …' if len(missing) > 20 else '')
        )
    if not rows:
        return ohlcv_df

    halts = pl.DataFrame(rows).with_columns(
        pl.col('resume_trading_date').cast(pl.Date)
    )

    # 停牌區間 → untradable
    in_halt = (
        ohlcv_df.select(['symbol', 'date'])
        .join(halts, on='symbol', how='inner')
        .filter(
            (pl.col('date') >= pl.col('start_halt'))
            & (
                pl.col('resume_trading_date').is_null()
                | (pl.col('date') < pl.col('resume_trading_date'))
            )
        )
        .select(['symbol', 'date'])
        .unique()
        .with_columns(pl.lit(1).cast(pl.Int8).alias('_halt_untradable'))
    )

    # avoid_early=T → 該批 OHLCV 中、start_halt 前最後一個交易日
    pre_halt = (
        ohlcv_df.select(['symbol', 'date'])
        .join(
            halts.filter(pl.col('cal_avoid_early') == 1).select(
                ['symbol', 'start_halt']
            ),
            on='symbol',
            how='inner',
        )
        .filter(pl.col('date') < pl.col('start_halt'))
        .group_by(['symbol', 'start_halt'])
        .agg(pl.col('date').max().alias('date'))
        .select(['symbol', 'date'])
        .unique()
        .with_columns(pl.lit(1).cast(pl.Int8).alias('_halt_avoid'))
    )

    flags = in_halt.join(pre_halt, on=['symbol', 'date'], how='full', coalesce=True)

    return (
        ohlcv_df.join(flags, on=['symbol', 'date'], how='left')
        .with_columns(
            pl.max_horizontal(
                pl.col('untradable').cast(pl.Int8),
                pl.col('_halt_untradable').fill_null(0),
            ).alias('untradable'),
            pl.max_horizontal(
                pl.col('avoid_early').cast(pl.Int8),
                pl.col('_halt_avoid').fill_null(0),
            ).alias('avoid_early'),
        )
        .drop(['_halt_untradable', '_halt_avoid'])
    )


def prune_halt_calendar(ohlcv_df, calendar_path):
    """依 OHLCV 日期修剪 halt_calendar.json。

    以 ``ohlcv_df['date'].max()`` 為標準：若某筆 ``resume_trading_date`` 非空且
    ``<=`` 該日，視為已恢復、從 JSON 拿掉。無 resume（尚在停牌）保留。
    回傳移除筆數。
    """
    import json
    from datetime import date as date_cls
    from pathlib import Path

    path = Path(calendar_path)
    if ohlcv_df is None or ohlcv_df.height == 0:
        return 0
    if not path.is_file() or path.stat().st_size == 0:
        return 0

    records = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        return 0

    ref_date = ohlcv_df.get_column('date').max()
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
        f'halt_calendar 依 OHLCV 日期 {ref_date} 移除已恢復 {len(dropped)} 筆：'
        f'{[(d.get("symbol"), d.get("resume_trading_date")) for d in dropped[:10]]}'
        + (' …' if len(dropped) > 10 else '')
    )
    return len(dropped)


if __name__ == '__main__':
    import json
    import tempfile
    from datetime import date
    from pathlib import Path

    import polars as pl

    assert len(TRADING_HALT_SCHEMA) == 4
    assert TRADING_HALT_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert DTYPE_MAP['start_halt'] == 'datetime64[ns]'
    assert keep_col == ['symbol', 'start_halt', 'resume_trading_date', 'reason']

    # ponytail: 最小自檢
    assert avoid_early_from_reason('現金減資') == 'T'
    assert avoid_early_from_reason('減資') == 'T'
    assert avoid_early_from_reason('合併下市') == 'F'
    assert avoid_early_from_reason(None) == 'F'

    toy = pl.DataFrame(
        {
            'symbol': ['3426'],
            'start_halt': [date(2026, 6, 2)],
            'resume_trading_date': [date(2026, 6, 8)],
            'reason': ['現金減資'],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        cal = Path(tmp) / 'halt_calendar.json'
        assert update_halt_calendar(toy, cal) == 1
        data = json.loads(cal.read_text(encoding='utf-8'))
        assert data[0]['avoid_early'] == 'T'  # reason 含減資
        assert update_halt_calendar(toy, cal) == 0  # upsert 不重複加
        data = json.loads(cal.read_text(encoding='utf-8'))
        assert data[0]['avoid_early'] == 'T'
        assert data[0]['start_halt'] == '2026-06-02'
        assert data[0]['resume_trading_date'] == '2026-06-08'
        # 非減資 → 覆寫成 F（不再保留手工 T）
        toy_other = toy.with_columns(pl.lit('合併下市').alias('reason'))
        assert update_halt_calendar(toy_other, cal) == 0
        assert json.loads(cal.read_text(encoding='utf-8'))[0]['avoid_early'] == 'F'
        # 改回減資供 apply 測試
        assert update_halt_calendar(toy, cal) == 0
        assert update_halt_calendar(toy.head(0), cal) == 0

        bars = pl.DataFrame(
            {
                'symbol': ['3426', '3426', '3426', '3426', '1101'],
                'date': [
                    date(2026, 6, 1),  # start 前一日 → avoid_early
                    date(2026, 6, 2),
                    date(2026, 6, 5),
                    date(2026, 6, 8),
                    date(2026, 6, 1),
                ],
                'untradable': [0, 0, 0, 0, 0],
                'avoid_early': [0, 0, 0, 0, 0],
            }
        )
        out = apply_halt_calendar_to_ohlcv(bars, cal)
        # [6/2, 6/8)：6/2、6/5 untradable；6/8 已恢復
        assert out.filter(pl.col('symbol') == '3426').sort('date')[
            'untradable'
        ].to_list() == [0, 1, 1, 0]
        # reason 含減資 → 6/1（start 前最後一日）avoid_early=1
        assert out.filter(pl.col('symbol') == '3426').sort('date')[
            'avoid_early'
        ].to_list() == [1, 0, 0, 0]
        assert out.filter(pl.col('symbol') == '1101')['untradable'].to_list() == [0]

        loaded = load_halt_calendar(cal)
        assert loaded.height == 1
        assert loaded['symbol'][0] == '3426'
        assert loaded['start_halt'][0] == date(2026, 6, 2)
        assert loaded['resume_trading_date'][0] == date(2026, 6, 8)
        assert load_halt_calendar(Path(tmp) / 'missing.json').height == 0

        # prune：resume <= OHLCV 最大日 → 拿掉；尚無 resume 或尚未到 → 留
        cal2 = Path(tmp) / 'halt_calendar2.json'
        cal2.write_text(
            json.dumps(
                [
                    {
                        'symbol': '3426',
                        'start_halt': '2026-06-02',
                        'resume_trading_date': '2026-06-08',
                        'reason': '合併下市',
                        'avoid_early': 'T',
                    },
                    {
                        'symbol': '1101',
                        'start_halt': '2026-06-01',
                        'resume_trading_date': None,
                        'reason': '停牌中',
                        'avoid_early': 'F',
                    },
                    {
                        'symbol': '2330',
                        'start_halt': '2026-06-20',
                        'resume_trading_date': '2026-06-25',
                        'reason': '未來才恢復',
                        'avoid_early': 'F',
                    },
                ],
                ensure_ascii=False,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )
        bars2 = pl.DataFrame(
            {
                'symbol': ['1101'],
                'date': [date(2026, 6, 10)],
            }
        )
        n_drop = prune_halt_calendar(bars2, cal2)
        assert n_drop == 1
        kept = json.loads(cal2.read_text(encoding='utf-8'))
        assert {r['symbol'] for r in kept} == {'1101', '2330'}
    print('ok')
