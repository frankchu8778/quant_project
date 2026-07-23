import warnings

import polars as pl

# TEJ 缺值常寫成 na / 空白；UTF-16 匯出常見 lone \x00
TEJ_NA_VALUES = ['na', 'NA', 'N.A.', '\x00', '']
TEJ_DATE_FORMAT = '%Y%m%d'


def _encodings_for(file_path):
    with open(file_path, 'rb') as f:
        bom = f.read(2)
    # FF FE = UTF-16 LE BOM；只試 utf-16（再試 cp950/utf-8 必敗且大檔很慢）
    if bom == b'\xff\xfe':
        return ('utf-16', 'utf-16-le')
    if bom == b'\xfe\xff':
        return ('utf-16', 'utf-16-be')
    return ('cp950', 'utf-16', 'utf-8')


def _read_raw(file_path, columns=None):
    last_err = None
    for encoding in _encodings_for(file_path):
        try:
            kwargs = {
                'separator': '\t',
                'encoding': encoding,
                'null_values': TEJ_NA_VALUES,
                'infer_schema_length': 10_000,
                # TEJ 偶有欄位數不一致的殘缺列
                'truncate_ragged_lines': True,
            }
            if columns:
                kwargs['columns'] = columns
                # 有 schema 時先全當字串讀：TEJ 日期欄常混進備註（如「員工認股權轉換=…」），
                # 推成 i64 會直接 ComputeError；型別交給 _cast_expr(strict=False)
                kwargs['schema_overrides'] = dict.fromkeys(columns, pl.String)
                kwargs['infer_schema_length'] = 0
            return pl.read_csv(file_path, **kwargs)
        except Exception as e:
            last_err = e
    raise ValueError(f'無法讀取 TEJ 檔案: {file_path}') from last_err


def _schema_dtype_hint(dtype):
    if dtype in (pl.Float64, pl.Int64, pl.Int32, pl.UInt32):
        return 'float64'
    if dtype in (pl.Utf8, pl.String):
        return 'string'
    if dtype == pl.Date:
        return 'datetime64[ns]'
    return str(dtype)


def _warn_empty_schema(df):
    warnings.warn(
        'schema 未設定：已讀取全部欄位並由 polars 自動推斷型別；'
        '建立 SCHEMA 後傳入即可套用欄位篩選、英文命名與型別轉換。',
        UserWarning,
        stacklevel=3,
    )
    lines = ['# 以下供建立 SCHEMA 參考（英文名請自行填寫）：']
    for name, dtype in df.schema.items():
        hint = _schema_dtype_hint(dtype)
        lines.append(f"    '{name}': ('<english_name>', '{hint}'),")
    print('\n'.join(lines))


def _cast_expr(chinese_col, dtype):
    col = pl.col(chinese_col)
    if dtype == 'float64':
        return col.cast(pl.Float64, strict=False)
    if dtype == 'string':
        as_float = col.cast(pl.Float64, strict=False)
        return (
            pl.when(as_float.is_not_null())
            .then(as_float.round(0).cast(pl.Int64).cast(pl.Utf8))
            .otherwise(col.cast(pl.Utf8))
        )
    # TEJ 證券代碼常為 "代碼 名稱"；只取空白前段，不做數值轉換（否則 0050→50）
    # 尾端 .0 用字串去掉（TEJ 偶寫成 2330.0）
    if dtype == 'tej_symbol':
        return (
            col.cast(pl.Utf8)
            .str.split(' ')
            .list.first()
            .str.replace(r'\.0$', '')
        )
    if dtype in ('datetime64[ns]', 'date'):
        # TEJ 常寫成 20150601.0；字串讀入時需先經 Float 再取整
        return (
            col.cast(pl.Float64, strict=False)
            .round(0)
            .cast(pl.Int64)
            .cast(pl.Utf8)
            .str.strptime(pl.Date, TEJ_DATE_FORMAT, strict=False)
        )
    raise ValueError(f'不支援的 dtype: {dtype}')


# TEJ 下載常按市場拆檔：TSE/OTC，偶有 *_DE
TEJ_MARKET_TXT = frozenset({'TSE.txt', 'OTC.txt', 'TSE_DE.txt', 'OTC_DE.txt'})


def _list_txt_names(folder: str) -> list[str]:
    import os

    if not os.path.isdir(folder):
        raise FileNotFoundError(f'資料夾不存在：{folder}')
    return sorted(f for f in os.listdir(folder) if f.endswith('.txt'))


def one_txt(folder: str) -> str:
    """資料夾內必須恰好一個 .txt，回傳完整路徑；否則 raise。"""
    import os

    files = _list_txt_names(folder)
    if len(files) != 1:
        raise ValueError(f'{folder} 預期恰好 1 個 .txt，實際 {len(files)}：{files}')
    return os.path.join(folder, files[0])


def list_txt(folder: str, *, allow_market_split: bool = False) -> list[str]:
    """回傳資料夾內 .txt 完整路徑（已排序）。

    allow_market_split=False：恰好 1 個（同 one_txt）。
    allow_market_split=True：允許 TEJ_MARKET_TXT 子集，且至少含 TSE.txt 或 OTC.txt
    （常見：僅 TSE+OTC，或再加 TSE_DE+OTC_DE）。
    """
    import os

    files = _list_txt_names(folder)
    if not allow_market_split:
        if len(files) != 1:
            raise ValueError(f'{folder} 預期恰好 1 個 .txt，實際 {len(files)}：{files}')
        return [os.path.join(folder, files[0])]

    names = set(files)
    if not names:
        raise ValueError(f'{folder} 內沒有 .txt')
    unexpected = names - TEJ_MARKET_TXT
    if unexpected:
        raise ValueError(
            f'{folder} 有非預期檔名 {sorted(unexpected)}；'
            f'允許：{sorted(TEJ_MARKET_TXT)}'
        )
    if not names & {'TSE.txt', 'OTC.txt'}:
        raise ValueError(f'{folder} 至少需要 TSE.txt 或 OTC.txt，實際：{files}')
    return [os.path.join(folder, f) for f in files]


def read_tej_txt(file_path, schema=None):
    """讀取 TEJ 製表符分隔 .txt。

    schema 為 None 或空 dict 時：讀取全部欄位並由 polars 自動推斷型別，並提示建議 SCHEMA。
    schema 有值時：只讀指定欄位，轉成英文名與指定型別。
    schema 格式：{中文欄位: (英文欄位, dtype)}
    dtype 支援 string / float64 / datetime64[ns] / tej_symbol
    """
    if not schema:
        df = _read_raw(file_path)
        _warn_empty_schema(df)
        return df

    df = _read_raw(file_path, columns=list(schema))
    return df.select(
        _cast_expr(zh, dtype).alias(en)
        for zh, (en, dtype) in schema.items()
    )


def read_tej_folder(folder, schema=None, *, allow_market_split: bool = False):
    """讀取資料夾內全部合格 .txt 並 vertical concat。"""
    paths = list_txt(folder, allow_market_split=allow_market_split)
    dfs = [read_tej_txt(p, schema) for p in paths]
    return dfs[0] if len(dfs) == 1 else pl.concat(dfs)


if __name__ == '__main__':
    import os
    import tempfile
    from datetime import date

    schema = {
        '證券代碼': ('instrument', 'string'),
        '年月日': ('date', 'datetime64[ns]'),
        '收盤價(元)': ('close', 'float64'),
        '市場別': ('market', 'string'),
    }
    sample = (
        '證券代碼\t年月日\t收盤價(元)\t市場別\n'
        '1259.0\t20150601.0\t65.1\tOTC\n'
        '1264.0\t20150602.0\tna\tOTC\n'
        '1336.0\t20150603.0\tN.A.\tOTC\n'
    ).encode('cp950')
    with tempfile.NamedTemporaryFile('wb', suffix='.txt', delete=False) as f:
        f.write(sample)
        path = f.name
    try:
        df = read_tej_txt(path, schema)
        assert df.columns == ['instrument', 'date', 'close', 'market']
        assert df['instrument'].to_list() == ['1259', '1264', '1336']
        assert df['date'].to_list() == [
            date(2015, 6, 1), date(2015, 6, 2), date(2015, 6, 3),
        ]
        assert df['close'].to_list() == [65.1, None, None]
        assert df['market'].to_list() == ['OTC', 'OTC', 'OTC']

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            raw_df = read_tej_txt(path)
            assert len(caught) == 1
            assert issubclass(caught[0].category, UserWarning)
        assert raw_df.columns == ['證券代碼', '年月日', '收盤價(元)', '市場別']
        assert raw_df['收盤價(元)'].dtype == pl.Float64

        # tej_symbol：保留前導零，只切空白、去尾端 .0
        sym_schema = {'證券代碼': ('symbol', 'tej_symbol')}
        sym_sample = (
            '證券代碼\n'
            '0050 元大台灣50\n'
            '2330.0 台積電\n'
            'Y9999 加權指數\n'
        ).encode('cp950')
        with tempfile.NamedTemporaryFile('wb', suffix='.txt', delete=False) as sf:
            sf.write(sym_sample)
            sym_path = sf.name
        try:
            sym_df = read_tej_txt(sym_path, sym_schema)
            assert sym_df['symbol'].to_list() == ['0050', '2330', 'Y9999']
        finally:
            os.remove(sym_path)

        print('ok')
    finally:
        os.remove(path)

    # list_txt / read_tej_folder：市場拆檔
    d = tempfile.mkdtemp()
    try:
        for name in ('TSE.txt', 'OTC.txt'):
            with open(os.path.join(d, name), 'wb') as f:
                f.write(sample)
        paths = list_txt(d, allow_market_split=True)
        assert [os.path.basename(p) for p in paths] == ['OTC.txt', 'TSE.txt']
        joined = read_tej_folder(d, schema, allow_market_split=True)
        assert joined.height == 6  # 3 rows × 2 files
        try:
            list_txt(d)  # 非 market_split 應要求恰好 1
            raise AssertionError('expected ValueError')
        except ValueError:
            pass
        print('market_split ok')
    finally:
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
        os.rmdir(d)
