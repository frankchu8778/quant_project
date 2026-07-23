# TEJ 交易日曆：中文欄位 → (英文名, dtype)
# dtype 支援 string / float64 / datetime64[ns] / tej_symbol（供 parse.read_tej_txt）
TEJ_DATE_FORMAT = '%Y%m%d'

CALENDAR_KEEP_SCHEMA = {
    '年月日': ('date', 'datetime64[ns]'),
}

_CALENDAR_REST_SCHEMA = {
    '證券代碼': ('symbol', 'tej_symbol'),
    '名稱': ('name', 'string'),
    '成交金額': ('amount', 'float64'),
}

CALENDAR_SCHEMA = {
    **CALENDAR_KEEP_SCHEMA,
    **_CALENDAR_REST_SCHEMA,
}

RENAME_MAP = {zh: en for zh, (en, _) in CALENDAR_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in CALENDAR_SCHEMA.items()}

keep_col = [en for en, _ in CALENDAR_KEEP_SCHEMA.values()]


if __name__ == '__main__':
    assert len(CALENDAR_SCHEMA) == 4
    assert len(CALENDAR_KEEP_SCHEMA) == 1
    assert keep_col == ['date']
    assert DTYPE_MAP['date'] == 'datetime64[ns]'
    print('ok')
