"""最小可執行檢查：zhong_jin_vol_price。"""

from __future__ import annotations

import math

import numpy as np
import polars as pl

from src.alphas import zhong_jin_vol_price as zj


def _make_df(n: int = 30, symbols: tuple[str, ...] = ("A", "B")) -> pl.DataFrame:
    rows = []
    rng = np.random.default_rng(0)
    for sym in symbols:
        close = 100.0
        for i in range(n):
            ret = float(rng.normal(0, 0.01))
            open_ = close * (1 + float(rng.normal(0, 0.002)))
            close = close * (1 + ret)
            high = max(open_, close) * (1 + abs(float(rng.normal(0, 0.005))))
            low = min(open_, close) * (1 - abs(float(rng.normal(0, 0.005))))
            rows.append(
                {
                    "symbol": sym,
                    "date": i,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "amount": float(rng.uniform(1e5, 1e6)),
                    "turnover": float(rng.uniform(0.1, 2.0)),
                    "return_day": ret,
                    "limit_status": 0,
                }
            )
    return pl.DataFrame(rows)


def test_missing_columns_raises() -> None:
    df = pl.DataFrame({"symbol": ["A"], "date": [1], "close": [1.0]})
    try:
        zj.generate_vol_std(df, 22)
    except ValueError as e:
        assert "return_day" in str(e)
    else:
        raise AssertionError("應因缺欄報錯")


def test_period_suffix_naming() -> None:
    df = _make_df(30)
    out22 = zj.generate_vol_std(df, 22)
    out5 = zj.generate_vol_std(df, 5)
    assert "vol_std_1M" in out22.columns
    assert "vol_std_5d" in out5.columns
    assert out5.filter(pl.col("symbol") == "A")["vol_std_5d"][:4].null_count() == 4
    assert out5.filter(pl.col("symbol") == "A")["vol_std_5d"][4] is not None


def test_sample_std_matches_numpy() -> None:
    df = _make_df(10, symbols=("A",))
    out = zj.generate_vol_std(df, 5)
    rets = df["return_day"].to_numpy()
    expected = float(np.std(rets[0:5], ddof=1))
    got = out["vol_std_5d"][4]
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_safe_div_and_symbol_isolation() -> None:
    # A: 前 5 日低=0 → high/low 應為 null；B 正常
    rows = []
    for i in range(8):
        rows.append(
            {
                "symbol": "A",
                "date": i,
                "high": 10.0,
                "low": 0.0 if i < 5 else 8.0,
                "open": 9.0,
                "close": 9.5,
                "return_day": 0.01,
                "amount": 1e5,
                "turnover": 1.0,
                "limit_status": 0,
            }
        )
        rows.append(
            {
                "symbol": "B",
                "date": i,
                "high": 10.0,
                "low": 8.0,
                "open": 9.0,
                "close": 9.5,
                "return_day": 0.02 * (i + 1),
                "amount": 1e5,
                "turnover": 1.0,
                "limit_status": 0,
            }
        )
    df = pl.DataFrame(rows)
    out = zj.generate_vol_highlow_avg(df, 3)
    a = out.filter(pl.col("symbol") == "A").sort("date")
    b = out.filter(pl.col("symbol") == "B").sort("date")
    # A 視窗含 low=0 → 對應列為 null
    assert a["vol_highlow_avg_3d"][2] is None
    # B 不應受 A 影響，且有有效值
    assert b["vol_highlow_avg_3d"][2] is not None
    assert math.isclose(b["vol_highlow_avg_3d"][2], 10.0 / 8.0, rel_tol=1e-9)


def test_upshadow_formula() -> None:
    df = pl.DataFrame(
        {
            "symbol": ["A"] * 3,
            "date": [0, 1, 2],
            "open": [10.0, 10.0, 10.0],
            "high": [12.0, 12.0, 12.0],
            "low": [9.0, 9.0, 9.0],
            "close": [11.0, 11.0, 11.0],
            "return_day": [0.0, 0.0, 0.0],
            "amount": [1.0, 1.0, 1.0],
            "turnover": [1.0, 1.0, 1.0],
            "limit_status": [0, 0, 0],
        }
    )
    # (12 - max(10,11)) / 12 = 1/12
    out = zj.generate_vol_upshadow_avg(df, 3)
    assert math.isclose(out["vol_upshadow_avg_3d"][2], 1.0 / 12.0, rel_tol=1e-9)


def test_corr_and_mmt_smoke() -> None:
    df = _make_df(40)
    out = zj.generate_corr_ret_turn(df, 10)
    assert "corr_ret_turn_10d" in out.columns
    assert out.filter(pl.col("symbol") == "A")["corr_ret_turn_10d"][9] is not None
    out2 = zj.generate_mmt_normal_M(df, days=5)
    assert "mmt_normal_M" in out2.columns


def test_public_api_coverage() -> None:
    for name in zj.PERIOD_FACTORS:
        assert hasattr(zj, f"generate_{name}"), name
    for name in zj.FIXED_FACTORS:
        assert hasattr(zj, f"generate_{name}"), name
    # 略過的業績公告不應出現
    for name in ("mmt_report_overnight", "mmt_report_jump", "mmt_report_period"):
        assert not hasattr(zj, f"generate_{name}")


if __name__ == "__main__":
    test_missing_columns_raises()
    test_period_suffix_naming()
    test_sample_std_matches_numpy()
    test_safe_div_and_symbol_isolation()
    test_upshadow_formula()
    test_corr_and_mmt_smoke()
    test_public_api_coverage()
    print("ok")
