"""Databento 歷史資料 API 的請求與欄位清理 (從 fetch_nq_1m.py 搬出)。

時間皆為 UTC, end 不含 (Databento 慣例)。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import requests

BASE_URL = os.environ.get("DATABENTO_BASE_URL", "https://hist.massiveprivateserver.site")
DEFAULT_DATASET = "GLBX.MDP3"

UNDEF_PRICE = 9223372036854775807  # i64::MAX, Databento 的「無價格」
UNDEF_TS = 18446744073709551615  # u64::MAX

log = logging.getLogger("us_fetch.client")

MAX_ATTEMPTS = 8  # 連線/伺服器錯誤的重試次數 (rate limit 的等待不算在內)


class DatabentoRequestError(RuntimeError):
    """不會因重試而恢復的錯誤 (429/5xx/斷線以外的 4xx 等)。"""

    def __init__(self, status: int, body: str, symbols: str, schema: str, start: str, end: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status} {symbols} {schema} {start}~{end}: {body}")

    @property
    def is_auth(self) -> bool:
        """API key 無效 / 無權限: 換月份、換商品也一樣會失敗。"""
        return self.status in (401, 403)


SLOW_SECONDS = 120  # 超過就記一筆, 方便事後找出卡住的請求


def _short(symbols: str) -> str:
    return symbols if len(symbols) <= 60 else f"{symbols[:40]}...({symbols.count(',') + 1} 個)"


def _wait_for_reset(r: requests.Response, fallback: float) -> None:
    """依 Retry-After / x-ratelimit-reset 標頭等到額度重置。"""
    wait = fallback
    if r.headers.get("Retry-After", "").isdigit():
        wait = float(r.headers["Retry-After"])
    elif r.headers.get("x-ratelimit-reset", "").isdigit():
        wait = float(r.headers["x-ratelimit-reset"]) - time.time()
    wait = min(max(wait, 1.0), 3600.0) + 2  # 至少 1 秒、最多 1 小時, 多留 2 秒緩衝
    log.warning(f"  [rate limit] 等待 {wait:.0f} 秒後繼續")
    time.sleep(wait)


def _parse_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                rec.update(rec.pop("hd"))  # 攤平 header (ts_event, instrument_id...)
                rows.append(rec)
    return rows


def get_range(
    api_key: str,
    symbols: str,
    schema: str,
    start: str,
    end: str,
    stype_in: str = "parent",
    cache_dir: Path | None = None,
    dataset: str = DEFAULT_DATASET,
) -> list[dict]:
    """抓一段資料; cache_dir 不為 None 時每個成功的請求存成 jsonl, 重跑時直接讀。

    成功但沒有資料 -> 回傳 []; 不可重試的錯誤 -> DatabentoRequestError。
    """
    cache = None
    if cache_dir is not None:
        safe = symbols.replace(",", "+").replace("/", "_")
        if len(safe) > 100:  # 例如補漏時的一長串 instrument_id
            safe = f"{stype_in}-{hashlib.sha1(symbols.encode()).hexdigest()[:16]}"
        cache = cache_dir / f"{schema}__{safe}__{start}__{end}.jsonl"
        if cache.exists():
            return _parse_jsonl(cache)

    params = {
        "dataset": dataset,
        "symbols": symbols,
        "stype_in": stype_in,
        "schema": schema,
        "start": start,
        "end": end,
        "encoding": "json",
        "map_symbols": "true",  # 每筆 record 帶 "symbol" (原始合約代碼, e.g. NQH0)
    }
    tmp = Path(f"{cache}.part") if cache else None
    attempt = 0
    while attempt < MAX_ATTEMPTS:
        backoff = min(2**attempt * 5, 300)  # 5, 10, 20, ... 最多 5 分鐘
        t0 = time.monotonic()  # WSL2 會校正時鐘, time.time() 可能倒退
        try:
            r = requests.get(
                f"{BASE_URL}/v0/timeseries.get_range",
                auth=(api_key, ""),
                params=params,
                stream=True,
                timeout=(30, 900),  # (連線, 兩次收到資料之間的最長間隔)
            )
            if r.status_code == 429:  # 額度用完 -> 等重置, 不算重試次數
                _wait_for_reset(r, fallback=60)
                continue
            if r.status_code in (200, 206):  # 此代理跨日請求回 206, 內容完整
                if tmp is not None:
                    # 先寫 .part, 下載完整才改名, 中途斷線不會留下殘缺的快取
                    with tmp.open("wb") as f:  # 伺服器沒標 charset, 收到的是 bytes
                        for line in r.iter_lines():
                            if line:
                                f.write(line + b"\n")
                    tmp.replace(cache)
                    rows = _parse_jsonl(cache)
                else:
                    rows = []
                    for line in r.iter_lines(decode_unicode=True):
                        if line:
                            rec = json.loads(line)
                            rec.update(rec.pop("hd"))
                            rows.append(rec)
                log.debug(f"  GET {_short(symbols)} {schema} {start}~{end}: {len(rows)} 筆, {time.monotonic() - t0:.1f}s, "
                          f"額度剩 {r.headers.get('x-ratelimit-remaining')}")
                if time.monotonic() - t0 > SLOW_SECONDS:
                    log.info(f"  慢請求: {_short(symbols)} {schema} {start}~{end} 花了 {time.monotonic() - t0:.0f}s ({len(rows)} 筆)")
                if r.headers.get("x-ratelimit-remaining") == "0":  # 下一次一定會被擋, 先等
                    _wait_for_reset(r, fallback=60)
                return rows
            if r.status_code in (408, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code} {r.text[:200]}")
            # 其他狀態碼: 不重試, 也不當成「沒資料」
            raise DatabentoRequestError(r.status_code, r.text[:1000], symbols, schema, start, end)
        except (requests.RequestException, json.JSONDecodeError) as e:
            # 連線失敗 / 下載到一半斷線 / 回應被截斷
            attempt += 1
            log.warning(f"  {_short(symbols)} {schema} {start}~{end}: {e!r}; {backoff}s 後重試 {attempt}/{MAX_ATTEMPTS}")
            time.sleep(backoff)
    raise RuntimeError(f"多次重試失敗: {symbols} {schema} {start}~{end}")


def _ts(col: str) -> pl.Expr:
    v = pl.col(col).cast(pl.UInt64, strict=False)
    return pl.when(v == UNDEF_TS).then(None).otherwise(v).cast(pl.Int64).pipe(pl.from_epoch, time_unit="ns").dt.replace_time_zone("UTC").alias(col)


def _px(col: str) -> pl.Expr:
    v = pl.col(col).cast(pl.Int64, strict=False)
    return pl.when(v == UNDEF_PRICE).then(None).otherwise(v / 1e9).alias(col)


def _sample_days(start: date, end: date) -> list[date]:
    """抓 definition 的日子: 起始日 + 區間內每個星期一。"""
    days = [start]
    d = start + timedelta(days=(7 - start.weekday()) % 7 or 7)  # 下一個星期一
    while d < end:
        days.append(d)
        d += timedelta(days=7)
    return days


def _clean_definitions(rows: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(rows, infer_schema_length=None)
    keep = [
        "instrument_id", "raw_symbol", "symbol", "asset", "security_type", "instrument_class",
        "expiration", "activation", "strike_price", "underlying", "underlying_id",
        "min_price_increment", "unit_of_measure_qty", "currency", "ts_recv",
    ]
    df = df.select([c for c in keep if c in df.columns])
    df = df.with_columns(
        pl.col("instrument_id").cast(pl.UInt32, strict=False),
        *[_ts(c) for c in ("expiration", "activation", "ts_recv") if c in df.columns],
        *[_px(c) for c in ("strike_price", "min_price_increment") if c in df.columns],
    )
    # 同一合約會出現在多個快照裡 -> 每個合約留最新一筆。
    # CME 會把到期合約的 instrument_id 重新分配給新合約, 所以要用 (id, 代碼) 當 key
    return df.sort("ts_recv").unique(["instrument_id", "raw_symbol"], keep="last").sort("raw_symbol")


def _clean_bars(rows: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(rows, infer_schema_length=None)
    return df.select(
        _ts("ts_event"),
        pl.col("instrument_id").cast(pl.UInt32, strict=False),
        pl.col("symbol"),
        *[_px(c) for c in ("open", "high", "low", "close")],
        pl.col("volume").cast(pl.UInt64, strict=False),
    )
