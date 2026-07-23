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


if __name__ == '__main__':
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
    print('ok')
