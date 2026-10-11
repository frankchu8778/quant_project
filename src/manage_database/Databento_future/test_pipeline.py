"""美國期貨原始資料管線的測試 (不連網)。

    ~/miniconda3/envs/quant_research/bin/python -m pytest src/manage_database/Databento_future/test_pipeline.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import databento_client  # noqa: E402
import init_duckdb  # noqa: E402
from databento_client import DatabentoRequestError, _px, _sample_days  # noqa: E402
from fetch import (  # noqa: E402
    check_option_roots,
    fetch_product,
    filter_backfill,
    load_products,
    manifest_path,
    months_between,
)

E9 = 1_000_000_000


def ns(ts: str) -> str:
    """ISO UTC 時間 -> Databento JSON 的 ns 字串。"""
    return str(int(datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()) * E9)


def defn(iid, raw, asset, cls, underlying="", strike=None, ts_recv="2020-04-01T00:00:00"):
    return {
        "ts_event": ns(ts_recv), "instrument_id": iid, "raw_symbol": raw, "asset": asset,
        "instrument_class": cls, "expiration": ns("2020-06-19T13:30:00"), "underlying": underlying,
        "strike_price": str(int(strike * E9)) if strike is not None else str(databento_client.UNDEF_PRICE),
        "ts_recv": ns(ts_recv),
    }


def bar(iid, sym, ts, close=100.0):
    px = str(int(close * E9))
    return {"ts_event": ns(ts), "instrument_id": iid, "symbol": sym,
            "open": px, "high": px, "low": px, "close": px, "volume": "1"}


# ---------- 純函式 ----------

def test_sample_days_start_plus_mondays():
    assert _sample_days(date(2020, 4, 1), date(2020, 5, 1)) == [
        date(2020, 4, 1), date(2020, 4, 6), date(2020, 4, 13), date(2020, 4, 20), date(2020, 4, 27)
    ]
    # 起始日本身是星期一: 不重複
    assert _sample_days(date(2020, 6, 1), date(2020, 6, 9)) == [date(2020, 6, 1), date(2020, 6, 8)]


def test_months_between():
    assert months_between(date(2020, 3, 1), date(2020, 5, 1)) == [date(2020, 3, 1), date(2020, 4, 1)]
    assert months_between(date(2020, 12, 1), date(2021, 2, 1)) == [date(2020, 12, 1), date(2021, 1, 1)]
    with pytest.raises(ValueError):
        months_between(date(2020, 3, 2), date(2020, 5, 1))


def test_px_keeps_negative_price():
    df = pl.DataFrame({"close": [str(-37_630_000_000), str(databento_client.UNDEF_PRICE)]})
    assert df.select(_px("close"))["close"].to_list() == [-37.63, None]


def test_filter_backfill_drops_other_identity_of_reused_id():
    # 實例 (v2): id 345301 在 4/10 前是瑞郎選擇權, 4/29 起才是 QNEM0 C9710; 以 id 查整月兩個都會回來
    extra = pl.DataFrame({
        "instrument_id": pl.Series([345301, 345301, 548060], dtype=pl.UInt32),
        "raw_symbol": ["2SFJ0 P1100", "QNEM0 C9710", "NQM0 C9710"],
    })
    bars = pl.DataFrame({
        "instrument_id": pl.Series([345301, 548060], dtype=pl.UInt32),
        "symbol": ["QNEM0 C9710", "NQM0 C9710"],
    })
    assert sorted(filter_backfill(extra, bars)["raw_symbol"].to_list()) == ["NQM0 C9710", "QNEM0 C9710"]


def test_option_root_comes_from_underlying_future():
    fut = pl.DataFrame({"raw_symbol": ["CLK0", "CLM0"], "asset": ["CL", "CL"]})
    opt = pl.DataFrame({"raw_symbol": ["LOK0 C2500", "LOM0 P2000", "XXK0 C1"], "underlying": ["CLK0", "CLM0", "6SM0"]})
    assert check_option_roots(opt, fut, "CL")["raw_symbol"].to_list() == ["XXK0 C1"]
    assert check_option_roots(opt, fut, "GC").height == 3


def test_products_yaml_monthly_options_only():
    # 選擇權只當期貨的補充資料: 每個商品最多一個月選系列
    cfg = load_products()
    assert all(len(p.get("options") or {}) <= 1 for p in cfg["products"].values())
    assert {r: list(cfg["products"][r]["options"]) for r in ("NQ", "CL", "GC")} == {"NQ": ["NQ"], "CL": ["LO"], "GC": ["OG"]}


def test_get_all_splits_when_response_hits_cap(monkeypatch):
    import fetch

    monkeypatch.setattr(fetch, "RECORD_CAP", 30)
    calls = []

    def req(symbols, schema, start, end, stype_in):
        calls.append((start, end))
        s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
        n = int((e - s).total_seconds() // 3600)  # 每小時 1 筆, 最多回 30 筆 (截斷)
        return [{"ts": s + timedelta(hours=i)} for i in range(min(n, 30))]

    rows = fetch.get_all(req, "CL.FUT", "ohlcv-1m", datetime(2020, 4, 1), datetime(2020, 4, 4))
    assert [r["ts"] for r in rows] == [datetime(2020, 4, 1) + timedelta(hours=i) for i in range(72)]  # 不缺不重
    assert calls[0] == ("2020-04-01", "2020-04-04")  # 午夜邊界維持日期格式 (與舊快取檔名相容)
    assert ("2020-04-02T12:00:00", "2020-04-04") in calls

    monkeypatch.setattr(fetch, "RECORD_CAP", 0)  # 怎麼切都滿 -> 報錯而不是默默截斷
    with pytest.raises(RuntimeError, match="上限"):
        fetch.get_all(lambda *a: [], "CL.FUT", "ohlcv-1m", datetime(2020, 4, 1), datetime(2020, 4, 1, 4))


# ---------- get_range 的錯誤處理 ----------

class FakeResponse:
    def __init__(self, status, text="", lines=()):
        self.status_code, self.text, self.headers, self._lines = status, text, {}, lines

    def iter_lines(self, decode_unicode=False):
        return iter(self._lines)


def test_get_range_raises_on_non_retryable_4xx(monkeypatch):
    monkeypatch.setattr(databento_client.requests, "get", lambda *a, **k: FakeResponse(401, "bad key"))
    with pytest.raises(DatabentoRequestError) as e:
        databento_client.get_range("k", "NQ.FUT", "ohlcv-1m", "2020-04-01", "2020-05-01")
    assert e.value.status == 401 and "bad key" in e.value.body


def test_get_range_empty_success_returns_empty(monkeypatch):
    monkeypatch.setattr(databento_client.requests, "get", lambda *a, **k: FakeResponse(200))
    assert databento_client.get_range("k", "NQ.FUT", "ohlcv-1m", "2020-04-01", "2020-05-01") == []


# ---------- fetch_product 端到端 (假的 requester) ----------

CFG = {"products": {"CL": {"name": "WTI", "options": {"LO": "月選"}}}}

DEFS = [
    defn(1, "CLK0", "CL", "F"),
    defn(2, "CLM0", "CL", "F"),
    defn(3, "CLK0-CLM0", "CL", "S"),
    defn(10, "LOK0 C2500", "LO", "C", "CLK0", 25.0),
    defn(11, "LOK0 P-500", "LO", "P", "CLK0", -5.0),  # 負履約價
    defn(12, "UD:1V: VT 0420", "LO", "T"),  # 選擇權組合單
]
FUT_BARS = [
    bar(1, "CLK0", "2020-04-20T18:30:00", -37.63),  # 負價
    bar(2, "CLM0", "2020-04-20T18:30:00", 20.43),
    bar(3, "CLK0-CLM0", "2020-04-20T18:30:00", -58.06),
    bar(4, "UD:1V: SP 0420", "2020-04-20T18:31:00", 1.0),  # 盤中臨時價差, 沒有定義
]
OPT_BARS = [
    bar(10, "LOK0 C2500", "2020-04-20T18:30:00", 0.01),
    bar(11, "LOK0 P-500", "2020-04-20T18:30:00", 3.0),
    bar(12, "UD:1V: VT 0420", "2020-04-20T18:30:00", 0.5),
    bar(13, "LOK0 C3000", "2020-04-29T18:30:00", 0.02),  # 4/27 快照之後才掛牌 -> 靠補漏
]
BACKFILL = [
    defn(13, "OZSK0 C1", "OZS", "C", "ZSK0", 1.0, ts_recv="2020-04-02T00:00:00"),  # id 13 的舊身分
    defn(13, "LOK0 C3000", "LO", "C", "CLK0", 30.0, ts_recv="2020-04-29T00:00:00"),
]


class FakeRequester:
    def __init__(self, cache_dir: Path, fail_on: str | None = None):
        self.cache_dir, self.fail_on, self.calls = cache_dir, fail_on, []

    def __call__(self, symbols, schema, start, end, stype_in):
        self.calls.append((symbols, schema, start, end, stype_in))
        (self.cache_dir / f"{len(self.calls)}.jsonl").write_text("x")  # 模擬快取檔
        if self.fail_on and self.fail_on == schema:
            raise DatabentoRequestError(422, "boom", symbols, schema, start, end)
        if schema == "definition" and stype_in == "instrument_id":
            return BACKFILL
        if schema == "definition":
            return DEFS if start == "2020-04-01" else []
        lo, hi = ns(datetime.fromisoformat(start).isoformat()), ns(datetime.fromisoformat(end).isoformat())
        return [b for b in (FUT_BARS if symbols == "CL.FUT" else OPT_BARS) if int(lo) <= int(b["ts_event"]) < int(hi)]


@pytest.fixture
def run(tmp_path):
    data_root, cache_root = tmp_path / "us", tmp_path / "cache"
    made = []

    def _run(fail_on=None, force=False, today=date(2020, 6, 1)):
        def requester_for(cache_dir):
            made.append(FakeRequester(cache_dir, fail_on))
            return made[-1]
        return fetch_product("CL", date(2020, 4, 1), CFG, requester_for, data_root, cache_root, today, force)

    return _run, data_root, cache_root, made


def _read(data_root: Path, sub: str) -> pl.DataFrame:
    return pl.read_parquet(data_root / "raw" / sub / "root=CL" / "month=2020-04" / "data.parquet")


def test_fetch_product_splits_kinds_and_cleans_up(run):
    _run, data_root, cache_root, made = run
    assert _run() == "complete"

    fut = _read(data_root, "futures/bars_1m")
    assert fut["raw_symbol"].to_list() == ["CLK0", "CLM0"]
    assert fut.filter(pl.col("raw_symbol") == "CLK0")["close"].item() == -37.63

    spr = _read(data_root, "futures/spread_bars_1m")
    assert sorted(spr["raw_symbol"].to_list()) == ["CLK0-CLM0", "UD:1V: SP 0420"]

    opt = _read(data_root, "options/bars_1m")
    assert sorted(opt["raw_symbol"].to_list()) == ["LOK0 C2500", "LOK0 C3000", "LOK0 P-500"]  # 組合單已丟
    assert opt.filter(pl.col("raw_symbol") == "LOK0 C3000")["underlying"].item() == "CLK0"  # 補漏對到

    con = _read(data_root, "options/contracts")
    assert sorted(con["raw_symbol"].to_list()) == ["LOK0 C2500", "LOK0 C3000", "LOK0 P-500"]  # 沒有 OZSK0
    assert con.filter(pl.col("raw_symbol") == "LOK0 P-500")["strike_price"].item() == -5.0
    assert _read(data_root, "futures/spread_contracts")["raw_symbol"].to_list() == ["CLK0-CLM0"]

    man = pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))
    assert dict(zip(man["kind"], man["rows"])) == {"futures": 2, "spreads": 2, "options": 3}
    assert set(man["status"]) == {"complete"}
    assert not (cache_root / "CL" / "2020-04").exists()

    # 重跑: 不發任何請求
    assert _run() == "skipped"
    assert len(made) == 1  # 沒有新建 requester


def test_fetch_product_failure_keeps_cache_and_marks_failed(run):
    _run, data_root, cache_root, made = run
    assert _run(fail_on="ohlcv-1m") == "failed"
    man = pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))
    assert man["status"].to_list() == ["failed"] and "boom" in man["error"].item()
    assert any((cache_root / "CL" / "2020-04").iterdir())
    assert not (data_root / "raw").exists()

    # 失敗的月份重跑時會重新處理
    assert _run() == "complete"


def test_products_yaml_keys_are_strings():
    cfg = load_products()
    assert all(isinstance(r, str) for r in cfg["products"])  # 6E / 6J 不能被 YAML 讀成數字
    assert {"ES", "SIL", "ZC", "6E", "6J"} <= set(cfg["products"])


def test_options_switch(tmp_path):
    data_root, cache_root = tmp_path / "us", tmp_path / "cache"
    made = []

    def go(fetch_opts, force=False):
        cfg = {"defaults": {"fetch_options": fetch_opts}, "products": CFG["products"]}
        def requester_for(cache_dir):
            made.append(FakeRequester(cache_dir))
            return made[-1]
        return fetch_product("CL", date(2020, 4, 1), cfg, requester_for, data_root, cache_root, date(2020, 6, 1), force)

    opt_file = data_root / "raw" / "options" / "bars_1m" / "root=CL" / "month=2020-04" / "data.parquet"
    kinds = lambda: sorted(pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))["kind"])  # noqa: E731

    # 關閉: 不請求選擇權, 不產生檔案, manifest 不記選擇權
    assert go(False) == "complete"
    assert all("LO" not in c[0] for c in made[-1].calls)
    assert not opt_file.exists() and kinds() == ["futures", "spreads"]

    # 打開: 缺選擇權紀錄的月份會重抓
    assert go(True) == "complete" and opt_file.exists() and kinds() == ["futures", "options", "spreads"]
    assert go(True) == "skipped"
    assert go(False) == "skipped"  # 關閉時, 已有選擇權的月份照樣算完成

    # 關閉 + --force: 只重抓期貨, 舊的選擇權檔案與紀錄保留
    assert go(False, force=True) == "complete"
    assert opt_file.exists() and kinds() == ["futures", "options", "spreads"]


def test_invalid_key_stops_instead_of_failing_every_month(tmp_path):
    data_root, cache_root = tmp_path / "us", tmp_path / "cache"
    calls = []

    def requester_for(cache_dir):
        def req(symbols, schema, start, end, stype_in):
            calls.append((symbols, schema))
            raise DatabentoRequestError(401, '{"detail":"Invalid client API key"}', symbols, schema, start, end)
        return req

    with pytest.raises(DatabentoRequestError):
        fetch_product("CL", date(2020, 4, 1), CFG, requester_for, data_root, cache_root, date(2020, 6, 1))
    assert pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))["status"][0] == "failed"
    assert {s for s, schema in calls if schema == "definition"} == {"CL.FUT,LO.OPT"}  # 401 後不改逐一請求


def test_failure_logs_traceback(run, caplog):
    _run, *_ = run
    with caplog.at_level("ERROR", logger="us_fetch"):
        assert _run(fail_on="ohlcv-1m") == "failed"
    rec = [r for r in caplog.records if "失敗" in r.getMessage()]
    assert rec and rec[0].exc_info is not None  # 有完整 traceback


def test_running_marker_during_fetch_and_resume_after_hard_crash(tmp_path):
    data_root, cache_root = tmp_path / "us", tmp_path / "cache"
    seen = []

    class Crash(BaseException):  # 模擬 kill: 不是 Exception, 程式的錯誤處理接不到
        pass

    def requester_for(cache_dir):
        def req(*a):
            seen.append(pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))["status"][0])
            raise Crash
        return req

    with pytest.raises(Crash):
        fetch_product("CL", date(2020, 4, 1), CFG, requester_for, data_root, cache_root, date(2020, 6, 1))
    assert seen[0] == "running"
    assert pl.read_parquet(manifest_path(data_root, "CL", date(2020, 4, 1)))["status"][0] == "running"

    # 重跑: running 不算完成, 會重新處理
    ok = lambda cache_dir: FakeRequester(cache_dir)  # noqa: E731
    assert fetch_product("CL", date(2020, 4, 1), CFG, ok, data_root, cache_root, date(2020, 6, 1)) == "complete"


def test_complete_but_file_missing_is_refetched(run):
    _run, data_root, _, made = run
    assert _run() == "complete"
    (data_root / "raw" / "options" / "bars_1m" / "root=CL" / "month=2020-04" / "data.parquet").unlink()
    assert _run() == "complete" and len(made) == 2  # 重抓了, 不是 skipped


def test_unfinished_month_is_partial(run):
    _run, data_root, _, made = run
    assert _run(today=date(2020, 4, 15)) == "partial"
    ohlcv = [c for c in made[-1].calls if c[1] == "ohlcv-1m"]
    assert max(c[3] for c in ohlcv) == "2020-04-15" and len(ohlcv) == 2 * 14  # 按日請求, 只到今天
    assert _run(today=date(2020, 5, 2)) == "complete"  # partial 不會被跳過


# ---------- DuckDB ----------

def test_duckdb_views_and_trade_date(tmp_path):
    data_root = tmp_path / "us"
    times = [
        "2020-03-01T23:00:00",  # 週日 17:00 CST -> 週一 3/2
        "2020-03-06T21:59:00",  # 週五 15:59 CST -> 週五 3/6
        "2020-03-08T22:00:00",  # 夏令時間首日, 週日 17:00 CDT -> 週一 3/9
        "2020-03-08T21:59:00",  # 同日 16:59 CDT (維護時段前) -> 週日 3/8 (實際不會有成交)
    ]
    bars = pl.DataFrame({
        "ts_event": [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in times],
        "instrument_id": pl.Series([1] * 4, dtype=pl.UInt32), "raw_symbol": ["NQH0"] * 4,
    })
    d = data_root / "raw" / "futures" / "bars_1m" / "root=NQ" / "month=2020-03"
    d.mkdir(parents=True)
    bars.write_parquet(d / "data.parquet")
    for month, recv in (("2020-03", 1), ("2020-04", 2)):
        c = data_root / "raw" / "futures" / "contracts" / "root=NQ" / f"month={month}"
        c.mkdir(parents=True)
        pl.DataFrame({"instrument_id": pl.Series([1], dtype=pl.UInt32), "raw_symbol": ["NQH0"], "ts_recv": [recv]}).write_parquet(c / "data.parquet")

    made = init_duckdb.build(data_root)
    assert "fut_bars" in made and "opt_bars" not in made
    con = duckdb.connect(str(data_root / "metadata" / "us.duckdb"), read_only=True)
    got = [r[0] for r in con.execute("SELECT trade_date FROM fut_bars ORDER BY ts_event").fetchall()]
    assert [str(g) for g in got] == ["2020-03-02", "2020-03-06", "2020-03-08", "2020-03-09"]
    assert con.execute("SELECT DISTINCT root FROM fut_bars").fetchall() == [("NQ",)]
    assert con.execute("SELECT count(*), max(ts_recv) FROM fut_contracts").fetchone() == (1, 2)
