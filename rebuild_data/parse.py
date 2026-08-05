import warnings

import polars as pl

# TEJ 缺值常寫成 na / 空白；UTF-16 匯出常見 lone \x00
TEJ_NA_VALUES = ['na', 'NA', 'N.A.', '\x00', '']
TEJ_DATE_FORMAT = '%Y%m%d'

# 每日下載 vs 全量重建匯出：同一語意欄位常見異名（exact 命中優先）
TEJ_COLUMN_ALIASES: dict[str, list[str]] = {
    '證券代碼': ['証券代碼', '公司', '公司代碼', '代碼'],
    '年月日': ['暫停交易起日', '除息日', '除權日', '日期'],
}


def _encodings_from_bom(bom: bytes):
    # FF FE = UTF-16 LE BOM；只試 utf-16（再試 cp950/utf-8 必敗且大檔很慢）
    if bom[:2] == b'\xff\xfe':
        return ('utf-16', 'utf-16-le')
    if bom[:2] == b'\xfe\xff':
        return ('utf-16', 'utf-16-be')
    return ('cp950', 'utf-16', 'utf-8')


def _encodings_for(file_path):
    with open(file_path, 'rb') as f:
        return _encodings_from_bom(f.read(2))


def _read_raw(source, columns=None):
    """source: 檔案路徑 (str) 或已讀入的 bytes（zip 記憶體解壓用）。"""
    import io

    if isinstance(source, (bytes, bytearray, memoryview)):
        raw = bytes(source)
        encodings = _encodings_from_bom(raw[:2])
        label = '<bytes>'

        def _open():
            return io.BytesIO(raw)
    else:
        encodings = _encodings_for(source)
        label = source

        def _open():
            return source

    last_err = None
    for encoding in encodings:
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
            return pl.read_csv(_open(), **kwargs)
        except Exception as e:
            last_err = e
    raise ValueError(f'無法讀取 TEJ 檔案: {label}') from last_err


def _peek_columns(source) -> list[str]:
    """只讀表頭欄名（n_rows=0）。"""
    import io

    if isinstance(source, (bytes, bytearray, memoryview)):
        raw = bytes(source)
        encodings = _encodings_from_bom(raw[:2])
        label = '<bytes>'

        def _open():
            return io.BytesIO(raw)
    else:
        encodings = _encodings_for(source)
        label = source

        def _open():
            return source

    last_err = None
    for encoding in encodings:
        try:
            return list(
                pl.read_csv(
                    _open(),
                    separator='\t',
                    encoding=encoding,
                    n_rows=0,
                    # 只取欄名：勿推型別；否則表頭後首列 N.A. 會被推成 f64 而炸
                    infer_schema_length=0,
                    null_values=TEJ_NA_VALUES,
                    truncate_ragged_lines=True,
                ).columns
            )
        except Exception as e:
            last_err = e
    raise ValueError(f'無法讀取 TEJ 表頭: {label}') from last_err


def _zh_variants(name: str) -> list[str]:
    """證/証 異體字展開。"""
    out = [name]
    if '證' in name:
        out.append(name.replace('證', '証'))
    if '証' in name:
        out.append(name.replace('証', '證'))
    return list(dict.fromkeys(out))


def _resolve_columns(
    schema_keys: list[str],
    actual_cols: list[str],
    aliases: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """schema 中文鍵 → 實際檔案欄名。"""
    actual = set(actual_cols)
    aliases = aliases or {}
    mapping: dict[str, str] = {}
    missing: list[str] = []

    for key in schema_keys:
        candidates: list[str] = []
        for c in [key, *aliases.get(key, [])]:
            candidates.extend(_zh_variants(c))
        candidates = list(dict.fromkeys(candidates))
        found = next((c for c in candidates if c in actual), None)
        if found is None:
            missing.append(key)
        else:
            mapping[key] = found

    if missing:
        raise ValueError(
            f'缺少欄位 {missing}；檔案有：{actual_cols}'
        )
    return mapping


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


# TEJ 下載常按市場拆檔：TSE/OTC，偶有 *_DE（同層 .txt 或同名子資料夾）
TEJ_MARKET_TXT = frozenset({'TSE.txt', 'OTC.txt', 'TSE_DE.txt', 'OTC_DE.txt'})
TEJ_MARKET_SUBDIRS = frozenset({'TSE', 'OTC', 'TSE_DE', 'OTC_DE'})


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
    allow_market_split=True：
      - 同層：TEJ_MARKET_TXT 子集（至少 TSE.txt 或 OTC.txt）
      - 或子資料夾：TSE / OTC / TSE_DE / OTC_DE，各內恰好 1 個 .txt
    """
    import os

    files = _list_txt_names(folder)
    if not allow_market_split:
        if len(files) != 1:
            raise ValueError(f'{folder} 預期恰好 1 個 .txt，實際 {len(files)}：{files}')
        return [os.path.join(folder, files[0])]

    if files:
        names = set(files)
        unexpected = names - TEJ_MARKET_TXT
        if unexpected:
            raise ValueError(
                f'{folder} 有非預期檔名 {sorted(unexpected)}；'
                f'允許：{sorted(TEJ_MARKET_TXT)}'
            )
        if not names & {'TSE.txt', 'OTC.txt'}:
            raise ValueError(f'{folder} 至少需要 TSE.txt 或 OTC.txt，實際：{files}')
        return [os.path.join(folder, f) for f in files]

    # 無同層 .txt → 嘗試市場子資料夾
    subdirs = sorted(
        d for d in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, d))
    )
    market_subs = [d for d in subdirs if d in TEJ_MARKET_SUBDIRS]
    unexpected_subs = set(subdirs) - TEJ_MARKET_SUBDIRS
    if unexpected_subs:
        raise ValueError(
            f'{folder} 有非預期子資料夾 {sorted(unexpected_subs)}；'
            f'允許：{sorted(TEJ_MARKET_SUBDIRS)}'
        )
    if not market_subs:
        raise ValueError(
            f'{folder} 內沒有 .txt，也沒有市場子資料夾 {sorted(TEJ_MARKET_SUBDIRS)}'
        )
    if not set(market_subs) & {'TSE', 'OTC'}:
        raise ValueError(f'{folder} 至少需要 TSE 或 OTC 子資料夾，實際：{market_subs}')
    return [one_txt(os.path.join(folder, d)) for d in market_subs]


def read_tej_txt(source, schema=None, *, column_aliases=None):
    """讀取 TEJ 製表符分隔 .txt。

    source: 檔案路徑，或已讀入的 bytes（不解壓落地時用）。
    schema 為 None 或空 dict 時：讀取全部欄位並由 polars 自動推斷型別，並提示建議 SCHEMA。
    schema 有值時：只讀指定欄位，轉成英文名與指定型別。
    schema 格式：{中文欄位: (英文欄位, dtype)}
    dtype 支援 string / float64 / datetime64[ns] / tej_symbol
    column_aliases: 額外 {schema鍵: [替代中文名, ...]}；會與 TEJ_COLUMN_ALIASES 合併。
    """
    if not schema:
        df = _read_raw(source)
        _warn_empty_schema(df)
        return df

    aliases = {**TEJ_COLUMN_ALIASES, **(column_aliases or {})}
    key_to_actual = _resolve_columns(
        list(schema), _peek_columns(source), aliases
    )
    read_cols = list(dict.fromkeys(key_to_actual[k] for k in schema))
    df = _read_raw(source, columns=read_cols)
    rename = {act: key for key, act in key_to_actual.items() if act != key}
    if rename:
        df = df.rename(rename)
    return df.select(
        _cast_expr(zh, dtype).alias(en)
        for zh, (en, dtype) in schema.items()
    )


def find_tej_zip(root: str, name: str) -> str:
    """在 root 下找檔名以 ``name`` 開頭的 .zip（恰好一個）。

    例：name='現金股息' 可命中 ``現金股息 - 2026-08-02 102425.zip``。
    """
    import os

    if not os.path.isdir(root):
        raise FileNotFoundError(f'資料夾不存在：{root}')
    hits = sorted(
        f for f in os.listdir(root)
        if f.endswith('.zip') and not f.startswith('.') and f.startswith(name)
    )
    if len(hits) == 0:
        raise FileNotFoundError(f'{root} 找不到以 {name!r} 開頭的 .zip')
    if len(hits) > 1:
        raise ValueError(
            f'{root} 有多個以 {name!r} 開頭的 .zip：{hits}'
        )
    return os.path.join(root, hits[0])


def read_tej_zip(root, name, schema=None, *, column_aliases=None):
    """從 root 下「檔名以 name 開頭」的 zip 讀取 .txt（只進記憶體，不寫磁碟）。

    zip 內須恰好一個 .txt（每日 TEJ 下載格式）。
    """
    import zipfile

    zip_path = find_tej_zip(root, name)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        txts = [
            n for n in zf.namelist()
            if n.endswith('.txt') and not n.endswith('/')
        ]
        if len(txts) != 1:
            raise ValueError(
                f'{zip_path} 預期恰好 1 個 .txt，實際 {len(txts)}：{txts}'
            )
        raw = zf.read(txts[0])
    return read_tej_txt(raw, schema, column_aliases=column_aliases)


def read_tej_folder(folder, schema=None, *, allow_market_split: bool = False):
    """讀取資料夾內全部合格 .txt 並 vertical concat。"""
    paths = list_txt(folder, allow_market_split=allow_market_split)
    dfs = [read_tej_txt(p, schema) for p in paths]
    return dfs[0] if len(dfs) == 1 else pl.concat(dfs)


def txt_to_parquet(
    src_folder: str,
    dest_folder: str,
    schema=None,
    *,
    allow_market_split: bool = False,
    name: str | None = None,
) -> str:
    """讀取 src_folder 內 .txt，寫成 dest_folder/{name}.parquet。

    dest_folder：使用者指定的新資料夾（不存在則建立）。
    name：parquet 檔名（不含副檔名）；預設用 src_folder 的資料夾名（原本資料名稱）。
    多檔（市場拆檔）時先 concat 再寫單一 parquet。
    回傳寫出的完整路徑。
    """
    import os

    os.makedirs(dest_folder, exist_ok=True)
    stem = name if name is not None else os.path.basename(os.path.abspath(src_folder))
    if not stem:
        raise ValueError(f'無法推得 parquet 名稱：src_folder={src_folder!r}, name={name!r}')
    out_path = os.path.join(dest_folder, f'{stem}.parquet')
    if os.path.exists(out_path):
        raise FileExistsError(f'parquet 已存在：{out_path}')
    df = read_tej_folder(src_folder, schema, allow_market_split=allow_market_split)
    df.write_parquet(out_path)
    return out_path


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

    # find_tej_zip：前綴命中
    zdir = tempfile.mkdtemp()
    try:
        open(os.path.join(zdir, '現金股息 - 2026-08-02 102425.zip'), 'wb').close()
        open(os.path.join(zdir, '資本形成 - 2026-08-02 102521.zip'), 'wb').close()
        hit = find_tej_zip(zdir, '現金股息')
        assert os.path.basename(hit).startswith('現金股息')
        try:
            find_tej_zip(zdir, '不存在')
            raise AssertionError('expected FileNotFoundError')
        except FileNotFoundError:
            pass
        print('find_tej_zip ok')
    finally:
        for name in os.listdir(zdir):
            os.remove(os.path.join(zdir, name))
        os.rmdir(zdir)

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

        # 市場子資料夾：TSE/OTC/... 各一個 .txt
        d_sub = tempfile.mkdtemp()
        try:
            for name in ('TSE', 'OTC'):
                sub = os.path.join(d_sub, name)
                os.makedirs(sub)
                with open(os.path.join(sub, f'{name}.txt'), 'wb') as f:
                    f.write(sample)
            paths = list_txt(d_sub, allow_market_split=True)
            assert [os.path.basename(os.path.dirname(p)) for p in paths] == ['OTC', 'TSE']
            joined = read_tej_folder(d_sub, schema, allow_market_split=True)
            assert joined.height == 6
            print('market_subdir ok')
        finally:
            for root, dirs, files in os.walk(d_sub, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(d_sub)

        # txt_to_parquet：指定 dest 名稱，parquet 用原本資料夾名；已存在則 raise
        dest = tempfile.mkdtemp()
        try:
            out = txt_to_parquet(d, dest, schema, allow_market_split=True)
            assert os.path.basename(out) == f'{os.path.basename(d)}.parquet'
            back = pl.read_parquet(out)
            assert back.height == 6
            assert back.columns == ['instrument', 'date', 'close', 'market']
            try:
                txt_to_parquet(d, dest, schema, allow_market_split=True)
                raise AssertionError('expected FileExistsError')
            except FileExistsError:
                pass
            print('txt_to_parquet ok')
        finally:
            for name in os.listdir(dest):
                os.remove(os.path.join(dest, name))
            os.rmdir(dest)
    finally:
        for name in os.listdir(d):
            os.remove(os.path.join(d, name))
        os.rmdir(d)
