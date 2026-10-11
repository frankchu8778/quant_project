"""以商品為單位抓取 CME 期貨 + 期貨價差 + 月選的 1 分 K, 存成 data/us/raw/ 下的 Parquet。

用法:
    export DATABENTO_API_KEY=db-xxxx
    ~/miniconda3/envs/quant_research/bin/python fetch.py --products NQ,CL,GC --start 2020-03-01 --end 2020-05-01

每個 (商品, 月份) 獨立處理: 標記 running -> 抓定義與 K 線 -> 寫 Parquet -> 讀回核對 -> 寫 manifest -> 刪快取。
manifest 為 complete 且資料檔都在的 (商品, 月份) 會跳過 (除非 --force); 失敗的記為 failed,
停在 running 的表示上次被硬中斷 (kill / 關機); 兩者重跑都會接續。
日誌寫到 <data_root>/logs/fetch_<商品>_<開始時間>.log (含 traceback 與 Python 崩潰時的 stack)。
時間皆為 UTC, end 不含。
"""

from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import shutil
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable

import polars as pl
import yaml

from databento_client import (
    DatabentoRequestError,
    _clean_bars,
    _clean_definitions,
    _sample_days,
    get_range,
)

log = logging.getLogger("us_fetch")

HERE = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = Path("/home/newt/quant_project/data/us")
DEFAULT_CACHE_ROOT = Path("/dev/shm/databento_cache")
MIN_FREE_BYTES = 2 * 1024**3
# 此代理每次回應最多 10 萬筆, 超過的直接截掉、不報錯 (實例: CL 2020-03 期貨只回到 3/5)。
# 回應筆數 == 上限就視為被截斷。
RECORD_CAP = 100_000
MIN_SPLIT = timedelta(hours=1)
WORKERS = 8  # 同時發出的請求數 (--workers); API 額度為每窗口 500 次, 瓶頸是伺服器回應時間

# (symbols, schema, start, end, stype_in) -> rows
Requester = Callable[[str, str, str, str, str], list[dict]]

# kind -> (K 線目錄, 合約目錄), 相對於 <data_root>/raw
OUTPUTS = {
    "futures": ("futures/bars_1m", "futures/contracts"),
    "spreads": ("futures/spread_bars_1m", "futures/spread_contracts"),
    "options": ("options/bars_1m", "options/contracts"),
}
FUT_INFO = ["instrument_id", "raw_symbol", "instrument_class", "expiration"]
OPT_INFO = FUT_INFO + ["strike_price", "underlying", "asset"]


def load_products(path: Path = HERE / "products.yaml") -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def wants_options(cfg: dict, root: str) -> bool:
    """商品的 fetch_options 優先, 否則用 defaults.fetch_options (未設定視為 true)。"""
    default = (cfg.get("defaults") or {}).get("fetch_options", True)
    return bool(cfg["products"][root].get("fetch_options", default))


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def months_between(start: date, end: date) -> list[date]:
    """[start, end) 內每個月的 1 號; start / end 必須是月初。"""
    if start.day != 1 or end.day != 1:
        raise ValueError("--start / --end 必須是月初 (YYYY-MM-01)")
    out, d = [], start
    while d < end:
        out.append(d)
        d = _next_month(d)
    return out


def _fmt(dt: datetime) -> str:
    return dt.date().isoformat() if dt.time() == time() else dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_all(req: Requester, symbols: str, schema: str, start: datetime, end: datetime, stype_in: str = "parent") -> list[dict]:
    """抓 [start, end); 回應剛好等於上限 (被代理截斷) 時把區間切半重抓。"""
    rows = req(symbols, schema, _fmt(start), _fmt(end), stype_in)
    if len(rows) < RECORD_CAP:
        return rows
    if end - start <= MIN_SPLIT:
        raise RuntimeError(f"{symbols} {schema} {_fmt(start)}~{_fmt(end)} 切到 {MIN_SPLIT} 仍達 {RECORD_CAP} 筆上限")
    mid = (start + (end - start) / 2).replace(minute=0, second=0, microsecond=0)
    if mid <= start:
        mid = start + MIN_SPLIT
    log.info(f"  {schema} {_fmt(start)}~{_fmt(end)}: 達 {RECORD_CAP} 筆上限, 從 {_fmt(mid)} 切半")
    return get_all(req, symbols, schema, start, mid, stype_in) + get_all(req, symbols, schema, mid, end, stype_in)


def _dt(d: date) -> datetime:
    return datetime.combine(d, time())


def _is_spread_sym() -> pl.Expr:
    # 盤中臨時建立的價差 (UD:...) 不會出現在快照裡, 只能依代碼判定
    return pl.col("symbol").str.contains("-") | pl.col("symbol").str.starts_with("UD:")


def fetch_definitions(req: Requester, parents: list[str], start: date, end: date) -> pl.DataFrame:
    """每週抓一天的定義快照 (所有 parent 合併成一次請求)。

    合併請求出錯時改為逐一請求; 逐一請求仍出錯就往上拋。
    週中才上市又在下次快照前下市的合約會漏掉, 由 backfill_definitions() 補。
    """
    def one_day(d: date) -> list[dict]:
        day, nxt = _dt(d), _dt(d) + timedelta(days=1)
        try:
            got = get_all(req, ",".join(parents), "definition", day, nxt)
        except DatabentoRequestError as e:
            if len(parents) == 1 or e.is_auth:
                raise
            log.warning(f"  definition {d}: 合併請求失敗 ({e.status}), 改為逐一請求")
            got = [r for p in parents for r in get_all(req, p, "definition", day, nxt)]
        log.info(f"  definition {d}: {len(got)} 筆")
        return got

    rows = [r for got in pmap(one_day, _sample_days(start, end)) for r in got]
    return _clean_definitions(rows) if rows else pl.DataFrame()


def fetch_bars(req: Requester, parents: list[str], start: date, end: date) -> list[dict]:
    """1 分 K 按日請求、平行抓取 (伺服器回應慢, 平行才快; 單日也不易碰到筆數上限)。"""
    days = [date.fromordinal(o) for o in range(start.toordinal(), end.toordinal())]
    sym = ",".join(parents)
    chunks = pmap(lambda d: get_all(req, sym, "ohlcv-1m", _dt(d), _dt(d) + timedelta(days=1)), days)
    return [r for c in chunks for r in c]


def pmap(fn: Callable, items: list) -> list:
    """平行執行 fn, 結果依 items 順序; 任一個出錯就往上拋。"""
    if WORKERS <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with _pool(min(WORKERS, len(items))) as ex:
        return [_result(f) for f in [ex.submit(fn, x) for x in items]]


def _result(f: Future):
    """等 future 結果, 但每秒醒來一次: 無限期的 f.result() 會擋住 Ctrl-C 直到請求回來。"""
    while True:
        try:
            return f.result(timeout=1)
        except FutureTimeout:
            continue


@contextmanager
def _pool(n: int):
    """離開時不等在途請求 (Ctrl-C 或任一請求出錯時, 不必卡到其他請求下載完)。"""
    ex = ThreadPoolExecutor(n)
    try:
        yield ex
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def filter_backfill(extra: pl.DataFrame, bars: pl.DataFrame) -> pl.DataFrame:
    """補抓回來的定義只留 (instrument_id, raw_symbol) 確實出現在 K 線中的。

    以 instrument_id 查一整個月, 會把同一個 id 在月內用過的其他身分也抓回來
    (CME 會重新分配到期合約的 id)。
    """
    seen = bars.select("instrument_id", raw_symbol="symbol").unique()
    return extra.join(seen, on=["instrument_id", "raw_symbol"], how="semi")


def backfill_definitions(req: Requester, defs: pl.DataFrame, bars: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """K 線裡出現、但快照裡沒有的單一合約 -> 用 instrument_id 補抓定義。"""
    known = defs.select("instrument_id", "raw_symbol") if not defs.is_empty() else pl.DataFrame(
        schema={"instrument_id": pl.UInt32, "raw_symbol": pl.String}
    )
    missing = (
        bars.join(known, left_on=["instrument_id", "symbol"], right_on=["instrument_id", "raw_symbol"], how="anti")
        .filter(~_is_spread_sym())  # 價差不補
        ["instrument_id"].unique().sort().to_list()
    )
    if not missing:
        log.info("  backfill: 沒有缺漏的合約")
        return defs
    log.info(f"  backfill: {len(missing)} 個合約不在快照裡, 補抓定義")
    batches = [",".join(str(x) for x in missing[i : i + 300]) for i in range(0, len(missing), 300)]
    rows = [r for got in pmap(lambda ids: get_all(req, ids, "definition", _dt(start), _dt(end), "instrument_id"), batches) for r in got]
    if not rows:
        return defs
    extra = filter_backfill(_clean_definitions(rows), bars)
    log.info(f"  backfill: 補到 {extra.height} 個")
    return (
        pl.concat([defs, extra], how="diagonal_relaxed")
        .unique(["instrument_id", "raw_symbol"], keep="last")
        .sort("raw_symbol")
    )


def _attach(bars: pl.DataFrame, defs: pl.DataFrame, info: list[str]) -> pl.DataFrame:
    """以 (instrument_id, 代碼) 對接定義: K 線的 symbol 是當下的正確代碼, 不受 id 重複使用影響。"""
    base = bars.columns
    cols = [c for c in info if c in defs.columns]
    out = bars.join(
        defs.select(cols), left_on=["instrument_id", "symbol"], right_on=["instrument_id", "raw_symbol"], how="left"
    ).with_columns(raw_symbol=pl.col("symbol"))
    for c in info:  # 定義缺欄位時補 null, 讓輸出欄位固定
        if c not in out.columns:
            out = out.with_columns(pl.lit(None).alias(c))
    return out.select(*base, *[c for c in info if c not in base])


def split_kinds(defs: pl.DataFrame, fut_bars: pl.DataFrame, opt_bars: pl.DataFrame) -> dict[str, tuple[pl.DataFrame, pl.DataFrame]]:
    """依 instrument_class 分成 期貨 (F) / 期貨價差 (S) / 選擇權 (C, P), 回傳 kind -> (K 線, 合約)。

    對不到定義的: 代碼像價差 -> 期貨請求裡歸價差、選擇權請求裡丟棄; 其餘保留並警告。
    選擇權組合單 (T)、混合價差 (M) 等一律丟棄。
    """
    cls = pl.col("instrument_class")
    unmatched = cls.is_null()
    out: dict[str, tuple[pl.DataFrame, pl.DataFrame]] = {}

    fb = _attach(fut_bars, defs, FUT_INFO) if not fut_bars.is_empty() else fut_bars
    if not fb.is_empty():
        fut = fb.filter((cls == "F") | (unmatched & ~_is_spread_sym()))
        spr = fb.filter((cls == "S") | (unmatched & _is_spread_sym()))
        _report_dropped("futures", fb, fut.height + spr.height)
        _warn_unmatched("futures", fut)
    else:
        fut = spr = fb
    ob = _attach(opt_bars, defs, OPT_INFO) if not opt_bars.is_empty() else opt_bars
    if not ob.is_empty():
        opt = ob.filter(cls.is_in(["C", "P"]) | (unmatched & ~_is_spread_sym()))
        _report_dropped("options", ob, opt.height)
        _warn_unmatched("options", opt)
    else:
        opt = ob

    def contracts(classes: list[str]) -> pl.DataFrame:
        return defs.filter(pl.col("instrument_class").is_in(classes)) if not defs.is_empty() else defs

    sort = lambda df: df.sort("ts_event", "raw_symbol") if not df.is_empty() else df  # noqa: E731
    out["futures"] = (sort(fut), contracts(["F"]))
    out["spreads"] = (sort(spr), contracts(["S"]))
    out["options"] = (sort(opt), contracts(["C", "P"]))
    return out


def _report_dropped(name: str, bars: pl.DataFrame, kept: int) -> None:
    if bars.height > kept:
        dropped = bars.filter(
            ~pl.col("instrument_class").is_in(["F", "S", "C", "P"]) | pl.col("instrument_class").is_null()
        )
        log.info(f"  [{name}] 丟棄 {bars.height - kept} 根 (組合單等): {dict(dropped['instrument_class'].value_counts().iter_rows())}")


def _warn_unmatched(name: str, bars: pl.DataFrame) -> None:
    um = bars.filter(pl.col("instrument_class").is_null())
    if um.height:
        log.warning(f"  [{name}] 警告: {um.height} 根 K 對不到定義, 已保留. 代碼例: {um['symbol'].unique().head(5).to_list()}")


def check_option_roots(opt_contracts: pl.DataFrame, fut_contracts: pl.DataFrame, root: str) -> pl.DataFrame:
    """由標的期貨決定選擇權合約的商品; 回傳對不到標的或商品不是 root 的合約。"""
    if opt_contracts.is_empty():
        return opt_contracts
    fut = fut_contracts.select(underlying="raw_symbol", underlying_root="asset").unique("underlying")
    tagged = opt_contracts.join(fut, on="underlying", how="left")
    return tagged.filter(pl.col("underlying_root").is_null() | (pl.col("underlying_root") != root))


def _write_part(df: pl.DataFrame, path: Path) -> Path | None:
    """寫 <path>.part 並讀回核對; 空表回傳 None (不產生檔案)。"""
    if df.is_empty():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    part = Path(f"{path}.part")
    df.write_parquet(part)
    back = pl.read_parquet(part)
    if back.height != df.height or back.select("instrument_id", "raw_symbol").n_unique() != df.select("instrument_id", "raw_symbol").n_unique():
        raise RuntimeError(f"讀回核對失敗: {part}")
    return part


def manifest_path(data_root: Path, root: str, month: date) -> Path:
    return data_root / "metadata" / "manifest" / f"root={root}" / f"{month:%Y-%m}.parquet"


def _write_manifest(data_root: Path, root: str, month: date, rows: list[dict]) -> None:
    path = manifest_path(data_root, root, month)
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = {
        "root": pl.String, "month": pl.String, "kind": pl.String, "rows": pl.Int64, "contracts": pl.Int64,
        "fetched_at": pl.Datetime("us", "UTC"), "status": pl.String, "error": pl.String,
    }
    part = Path(f"{path}.part")
    pl.DataFrame(rows, schema=schema).write_parquet(part)
    part.replace(path)


def read_status(data_root: Path, root: str, month: date) -> str | None:
    path = manifest_path(data_root, root, month)
    if not path.exists():
        return None
    return pl.read_parquet(path)["status"][0]


def missing_files(data_root: Path, root: str, month: date) -> list[Path]:
    """manifest 記有資料 (rows > 0) 但 K 線檔不存在的路徑。"""
    man = pl.read_parquet(manifest_path(data_root, root, month))
    out = []
    for kind, rows in man.select("kind", "rows").iter_rows():
        if kind in OUTPUTS and rows:
            p = data_root / "raw" / OUTPUTS[kind][0] / f"root={root}" / f"month={month:%Y-%m}" / "data.parquet"
            if not p.exists():
                out.append(p)
    return out


def _marker(root: str, month: date, fetched_at: datetime, status: str, error: str | None = None) -> list[dict]:
    return [{
        "root": root, "month": f"{month:%Y-%m}", "kind": None, "rows": None, "contracts": None,
        "fetched_at": fetched_at, "status": status, "error": error,
    }]


def fetch_product(
    root: str,
    month: date,
    cfg: dict,
    requester_for: Callable[[Path], Requester],
    data_root: Path,
    cache_root: Path,
    today: date,
    force: bool = False,
) -> str:
    """抓一個 (商品, 月份)。回傳 'skipped' / 'complete' / 'partial' / 'failed'。"""
    tag = f"[{root} {month:%Y-%m}]"
    product = cfg["products"][root]
    want_options = wants_options(cfg, root)
    kinds = ["futures", "spreads"] + (["options"] if want_options else [])
    prev = read_status(data_root, root, month)
    prev_man = pl.read_parquet(manifest_path(data_root, root, month)) if prev else None
    if prev == "complete" and not force:
        lost = missing_files(data_root, root, month)
        lacking = sorted(set(kinds) - set(prev_man["kind"]))
        if not lost and not lacking:
            log.info(f"{tag} manifest 為 complete, 跳過")
            return "skipped"
        if lost:
            log.warning(f"{tag} manifest 為 complete 但資料檔不見了, 重抓: {[str(p) for p in lost]}")
        if lacking:
            log.info(f"{tag} 之前沒抓 {lacking}, 重抓")
    elif prev == "running":
        log.warning(f"{tag} 上次停在 running (被 kill / 關機等硬中斷), 重抓")
    elif prev == "failed":
        log.info(f"{tag} 上次失敗, 重抓")
    end = min(_next_month(month), today)
    if end <= month:
        log.info(f"{tag} 月份尚未開始, 跳過")
        return "skipped"
    status = "complete" if _next_month(month) <= today else "partial"

    cache_dir = cache_root / root / f"{month:%Y-%m}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    req = requester_for(cache_dir)
    fetched_at = datetime.now(timezone.utc)
    fut_parents = [f"{root}.FUT"]
    opt_parents = [f"{s}.OPT" for s in (product.get("options") or {})] if want_options else []
    log.info(f"{tag} 開始: {fut_parents + opt_parents}")
    _write_manifest(data_root, root, month, _marker(root, month, fetched_at, "running"))
    written: list[tuple[Path, Path]] = []
    try:
        # 定義快照與兩種 K 線彼此獨立, 同時進行 (各自內部再按日平行)
        with _pool(3) as ex:
            f_defs = ex.submit(fetch_definitions, req, fut_parents + opt_parents, month, end)
            f_bars = {
                name: ex.submit(fetch_bars, req, parents, month, end) if parents else None
                for name, parents in (("futures", fut_parents), ("options", opt_parents))
            }
            defs = _result(f_defs)
            bars = {}
            for name, f in f_bars.items():
                rows = _result(f) if f else []
                bars[name] = _clean_bars(rows) if rows else pl.DataFrame()
                log.info(f"  ohlcv-1m {name}: {len(rows)} 筆")
        all_bars = pl.concat([b for b in bars.values() if not b.is_empty()]) if any(not b.is_empty() for b in bars.values()) else pl.DataFrame()
        if not all_bars.is_empty():
            defs = backfill_definitions(req, defs, all_bars, month, end)
        parts = split_kinds(defs, bars["futures"], bars["options"])

        bad = check_option_roots(parts["options"][1], parts["futures"][1], root)
        if bad.height:
            log.warning(f"  [options] 警告: {bad.height} 個選擇權合約的標的期貨不屬於 {root}. 例: {bad['raw_symbol'].head(5).to_list()}")

        to_remove: list[Path] = []
        manifest_rows = []
        for kind in kinds:  # 沒請求的種類 (關掉的選擇權) 不寫、不刪
            kbars, kcontracts = parts[kind]
            bars_dir, con_dir = OUTPUTS[kind]
            for df, sub in ((kbars, bars_dir), (kcontracts, con_dir)):
                dest = data_root / "raw" / sub / f"root={root}" / f"month={month:%Y-%m}" / "data.parquet"
                part = _write_part(df, dest)
                if part is None:
                    to_remove.append(dest)  # 重抓後變成沒資料 -> 舊檔要清掉
                else:
                    written.append((part, dest))
            manifest_rows.append({
                "root": root, "month": f"{month:%Y-%m}", "kind": kind, "rows": kbars.height,
                "contracts": kbars["raw_symbol"].n_unique() if kbars.height else 0,
                "fetched_at": fetched_at, "status": status, "error": None,
            })
        if prev_man is not None and "kind" in prev_man.columns:
            # 這次沒請求、但之前抓過且檔案還在的種類 (例如關掉選擇權後 --force): 保留舊紀錄
            keep = prev_man.filter(~pl.col("kind").is_in(kinds) & pl.col("kind").is_not_null() & (pl.col("status") == "complete"))
            manifest_rows += keep.to_dicts()
        for part, dest in written:
            part.replace(dest)
        for dest in to_remove:
            dest.unlink(missing_ok=True)
        _write_manifest(data_root, root, month, manifest_rows)
    except Exception as e:  # noqa: BLE001 — 任何失敗都記進 manifest, 保留快取供重跑
        log.exception(f"{tag} 失敗: {e!r}")
        for part, _ in written:
            part.unlink(missing_ok=True)
        _write_manifest(data_root, root, month, _marker(root, month, fetched_at, "failed", repr(e)[:2000]))
        if isinstance(e, DatabentoRequestError) and e.is_auth:
            raise  # key 錯誤是全域性的, 不再嘗試其他月份
        return "failed"

    shutil.rmtree(cache_dir)
    for r in manifest_rows:
        log.info(f"{tag} {r['kind']}: {r['rows']} 根 K, {r['contracts']} 個合約")
    log.info(f"{tag} {status}")
    return status


def setup_logging(data_root: Path, roots: list[str]) -> Path:
    """日誌同時寫檔與印到畫面; 檔案另接 faulthandler, Python 本身崩潰時也留下 stack。"""
    logs = data_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"fetch_{'-'.join(roots)}_{datetime.now():%Y%m%d-%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    file_h = logging.FileHandler(path, encoding="utf-8")
    screen_h = logging.StreamHandler(sys.stdout)
    for h in (file_h, screen_h):
        h.setFormatter(fmt)
    file_h.setLevel(logging.DEBUG)  # 檔案留每個請求的耗時與筆數
    screen_h.setLevel(logging.INFO)
    root_logger = logging.getLogger("us_fetch")
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers[:] = [file_h, screen_h]
    faulthandler.enable(file=file_h.stream)
    sys.excepthook = lambda t, v, tb: root_logger.critical("未捕捉的例外, 程式結束", exc_info=(t, v, tb))
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True, help="逗號分隔, 例如 NQ,CL,GC")
    ap.add_argument("--start", required=True, help="月初, 例如 2020-03-01")
    ap.add_argument("--end", required=True, help="月初, 不含")
    ap.add_argument("--force", action="store_true", help="manifest 為 complete 也重抓")
    ap.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    ap.add_argument("--workers", type=int, default=8, help="每類請求同時發出的數量")
    args = ap.parse_args()
    global WORKERS
    WORKERS = args.workers

    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        sys.exit("請先設定環境變數 DATABENTO_API_KEY")

    cfg = load_products()
    roots = [p.strip() for p in args.products.split(",") if p.strip()]
    unknown = [r for r in roots if r not in cfg["products"]]
    if unknown:
        sys.exit(f"products.yaml 沒有這些商品: {unknown}")
    months = months_between(date.fromisoformat(args.start), date.fromisoformat(args.end))
    log_path = setup_logging(args.data_root, roots)
    log.info(f"日誌: {log_path}")
    log.info(f"參數: {vars(args)}")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(args.cache_dir).free
    if free < MIN_FREE_BYTES:
        log.error(f"{args.cache_dir} 剩餘空間 {free / 1024**3:.1f} GB, 不足 2 GB; 請清空間或用 --cache-dir 指定別處")
        sys.exit(1)

    dataset = cfg.get("defaults", {}).get("dataset", "GLBX.MDP3")

    def requester_for(cache_dir: Path) -> Requester:
        return lambda symbols, schema, start, end, stype_in: get_range(
            api_key, symbols, schema, start, end, stype_in=stype_in, cache_dir=cache_dir, dataset=dataset
        )

    today = datetime.now(timezone.utc).date()
    results = {}
    try:
        for root in roots:
            for m in months:
                results[(root, f"{m:%Y-%m}")] = fetch_product(
                    root, m, cfg, requester_for, args.data_root, args.cache_dir, today, args.force
                )
    except DatabentoRequestError as e:
        log.error(f"API key 無效或沒有權限 (HTTP {e.status}: {e.body[:200]}); 已停止. "
                  f"請檢查 DATABENTO_API_KEY (目前開頭為 {os.environ['DATABENTO_API_KEY'][:5]}...)")
        sys.exit(2)
    except KeyboardInterrupt:
        # 正在處理的月份 manifest 停在 running, 快取保留; 重跑同指令即接續
        log.warning("使用者中斷 (Ctrl-C); 正在處理的月份留在 running, 重跑即接續")
        logging.shutdown()
        os._exit(130)  # 不等背景執行緒的在途請求
    log.info("結果:")
    for (root, m), s in results.items():
        log.info(f"  {root} {m}: {s}")
    if "failed" in results.values():
        sys.exit(1)


if __name__ == "__main__":
    main()
