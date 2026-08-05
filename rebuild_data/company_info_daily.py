# TEJ 公司基本資料（每日增量）：只留代碼＋目前產業／子產業
# 全量歷史時間軸仍用 Company_Info.add_industry_timelines
from __future__ import annotations

from pathlib import Path

TEJ_DATE_FORMAT = '%Y%m%d'

# rebuild subindustry map 鍵：code 左對齊寬 6 + 名稱（如 '11A   水泥製造'）
_SUBINDUSTRY_CODE_WIDTH = 6

COMPANY_INFO_DAILY_KEEP_SCHEMA = {
    '公司簡稱': ('symbol', 'string'),
    'TSE產業名': ('industry', 'string'),
    'TEJ子產業名': ('subindustry', 'string'),
}

COMPANY_INFO_DAILY_SCHEMA = dict(COMPANY_INFO_DAILY_KEEP_SCHEMA)

RENAME_MAP = {zh: en for zh, (en, _) in COMPANY_INFO_DAILY_SCHEMA.items()}
DTYPE_MAP = {en: dtype for _, (en, dtype) in COMPANY_INFO_DAILY_SCHEMA.items()}

keep_col = [en for en, _ in COMPANY_INFO_DAILY_KEEP_SCHEMA.values()]


def process_company_info_daily(df):
    """每日公司資料入口：只保留 symbol / industry / subindustry。"""
    import polars as pl

    out = df.select(keep_col)
    # strip 頭尾空白；空字串當 null
    return out.with_columns(
        pl.col(c).str.strip_chars().replace('', None)
        for c in keep_col
    )


def to_rebuild_subindustry_label(label: str) -> str:
    """Daily TEJ『M11A 水泥製造』→ rebuild map『11A   水泥製造』。"""
    text = str(label).strip()
    if not text:
        return text
    # daily 現況欄帶 M；rebuild 歷史欄無 M
    if text.startswith('M') and len(text) > 1 and text[1].isdigit():
        text = text[1:]
    parts = text.split(None, 1)
    if len(parts) != 2:
        return text
    code, name = parts
    return f'{code:<{_SUBINDUSTRY_CODE_WIDTH}}{name}'


def encode_daily_company_info(df, setting_dir: str | Path):
    """用既有 ``*_rebuild.json`` 編碼 industry／subindustry。

    Returns
    -------
    encoded_df, new_industries, new_subindustries
        未在對照表的字串會編成 null，並以 list 回傳供呼叫端提示。
    """
    import polars as pl
    import Company_Info

    industry_map, subindustry_map = Company_Info.load_rebuild_master_maps(setting_dir)

    # industry 已與 rebuild 鍵一致；subindustry 需對齊格式
    subs = df.get_column('subindustry').to_list()
    norm_subs = [
        None if v is None else to_rebuild_subindustry_label(v) for v in subs
    ]
    aligned = df.with_columns(pl.Series('subindustry', norm_subs, dtype=pl.String))

    new_industries = sorted(
        {
            str(v)
            for v in aligned.get_column('industry').drop_nulls().unique().to_list()
            if str(v) not in industry_map
        }
    )
    new_subindustries = sorted(
        {
            str(v)
            for v in aligned.get_column('subindustry').drop_nulls().unique().to_list()
            if str(v) not in subindustry_map
        }
    )

    encoded = Company_Info.encode_industry_columns(
        aligned, industry_map, subindustry_map
    )
    return encoded, new_industries, new_subindustries


if __name__ == '__main__':
    import polars as pl

    assert len(COMPANY_INFO_DAILY_SCHEMA) == 3
    assert keep_col == ['symbol', 'industry', 'subindustry']
    assert COMPANY_INFO_DAILY_SCHEMA['TSE產業名'] == ('industry', 'string')
    assert COMPANY_INFO_DAILY_SCHEMA['TEJ子產業名'] == ('subindustry', 'string')

    # ponytail: 最小自檢
    _out = process_company_info_daily(
        pl.DataFrame(
            {
                'symbol': ['1101', ' 2330 '],
                'industry': ['水泥工業', '  '],
                'subindustry': ['水泥製造', '半導體'],
                'extra': [1, 2],
            }
        )
    )
    assert _out.columns == keep_col
    assert _out['symbol'].to_list() == ['1101', '2330']
    assert _out['industry'].to_list() == ['水泥工業', None]
    assert to_rebuild_subindustry_label('M11A 水泥製造') == '11A   水泥製造'
    assert to_rebuild_subindustry_label('M13A1 泛用塑膠') == '13A1  泛用塑膠'
    print('ok')
