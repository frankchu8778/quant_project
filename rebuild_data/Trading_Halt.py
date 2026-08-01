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


if __name__ == '__main__':
    assert len(TRADING_HALT_SCHEMA) == 4
    assert TRADING_HALT_SCHEMA['證券代碼'] == ('symbol', 'tej_symbol')
    assert DTYPE_MAP['start_halt'] == 'datetime64[ns]'
    assert keep_col == ['symbol', 'start_halt', 'resume_trading_date', 'reason']
    print('ok')
