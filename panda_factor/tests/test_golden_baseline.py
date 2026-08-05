"""Golden-master 回歸測試 —— pandas → polars 重構的正確性基準。

專案原本零測試覆蓋，此檔是 Phase 1-3 唯一的比對依據。

用法：
    python -m pytest tests/ -v                    # 比對現況與 baseline
    python -m pytest tests/ --update-baseline     # 重新產生 baseline（行為變更時才用）

⚠️ `--update-baseline` 會覆寫基準。除非你**確認**行為變更是刻意的，否則不要用它
   來讓失敗的測試變綠 —— 那等於把回歸安全網關掉。
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from conftest import BASELINE_DIR, PANEL_FINGERPRINT_PATH, seeded
from _reference_pipeline import run_pandas_chain

# 數值比對容差。實測（見 test_noise_is_numerically_negligible）未設種子時
# ic/ir 漂移量級為 1e-10，故 1e-8 已有兩個數量級的餘裕。
ATOL = 1e-8
RTOL = 1e-8

# df_cuted 重構會重新產生的欄位
DF_CUTED_TRACKED_COLS = (
    ["test_factor", "test_factor_group"]
    + [f"returns_lag{i}" for i in range(0, 21)]
)

NUMERIC_ARTIFACTS = ["df_benchmark", "df_pnl", "df_ic"]
STRING_ARTIFACTS = ["df_info", "df_info2"]

# df_cuted 完整存檔約 12.5MB，不適合進版控，且內容是冗餘的 —— 它的每個受追蹤欄位
# 都會流進 df_ic / df_pnl（winsorize 後的因子值 → ic；分組指派 → pnl；
# returns_lag1..20 → ic_lag/rank_ic_lag）。因此改存逐欄統計指紋：
# 體積小，且比 df_ic 的整體偏移更能直接指出「是哪一欄變了」。
FINGERPRINT_NAME = "df_cuted_fingerprint"


def _numeric_path(name: str):
    return BASELINE_DIR / f"{name}.parquet"


def _string_path(name: str):
    return BASELINE_DIR / f"{name}.csv"


def _fingerprint(df: pd.DataFrame) -> pd.DataFrame:
    """逐欄統計指紋，用於在不存整份資料的前提下偵測 df_cuted 變動。"""
    rows = []
    for col in DF_CUTED_TRACKED_COLS:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        rows.append(
            {
                "column": col,
                "count": float(len(s)),
                "nan_count": float(s.isna().sum()),
                "mean": float(s.mean()),
                "std": float(s.std()),
                "min": float(s.min()),
                "max": float(s.max()),
                "sum": float(s.sum()),
            }
        )
    return pd.DataFrame(rows).set_index("column")


@pytest.fixture(scope="session")
def chain(panel):
    """以固定種子跑一次完整 pandas 鏈，供整個 session 共用。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            return run_pandas_chain(panel)


@pytest.fixture(scope="session", autouse=True)
def _maybe_write_baseline(chain, update_baseline):
    """帶 --update-baseline 時重新產生基準檔。"""
    if not update_baseline:
        return
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    for name in NUMERIC_ARTIFACTS:
        chain[name].to_parquet(_numeric_path(name))
    for name in STRING_ARTIFACTS:
        chain[name].to_csv(_string_path(name))
    _fingerprint(chain["df_cuted"]).to_parquet(_numeric_path(FINGERPRINT_NAME))
    print(f"\n[baseline] 已寫入 {BASELINE_DIR}")


def test_baseline_artifacts_exist():
    """baseline 必須已產生，否則後續比對無意義。"""
    missing = [
        p.name
        for p in [_numeric_path(n) for n in NUMERIC_ARTIFACTS]
        + [_numeric_path(FINGERPRINT_NAME)]
        + [_string_path(n) for n in STRING_ARTIFACTS]
        if not p.exists()
    ]
    assert not missing, (
        f"缺少 baseline: {missing}。請先執行 "
        f"`python -m pytest tests/ --update-baseline`"
    )


def test_fixture_is_stable(panel):
    """面板 fixture 由種子即時生成，此處驗證其跨環境／跨版本一致。

    面板不進版控，前提是 np.random.default_rng(PCG64) 的位元流穩定（NEP 19）。
    這個測試把該前提變成主動檢查 —— 若 NumPy 哪天真的改了串流，會在這裡明確報錯，
    而不是讓所有 baseline 悄悄偏移、被誤判成重構出錯。
    """
    from generate_fixture import panel_fingerprint

    expected = pd.read_csv(PANEL_FINGERPRINT_PATH, index_col=0)
    actual = panel_fingerprint(panel)

    pd.testing.assert_frame_equal(
        actual, expected, rtol=1e-12, atol=1e-12, check_dtype=False,
        obj="panel fixture fingerprint",
    )


def test_df_cuted_fingerprint_matches_baseline(chain):
    """df_cuted 的逐欄統計指紋需與 baseline 相符。

    任一欄（winsorize 後的因子、分組指派、returns_lag*）改變都會在此顯示是哪一欄，
    比從 df_ic 的整體偏移回推來得直接。
    """
    expected = pd.read_parquet(_numeric_path(FINGERPRINT_NAME))
    actual = _fingerprint(chain["df_cuted"])

    assert list(actual.index) == list(expected.index), (
        f"df_cuted 受追蹤欄位改變\n"
        f"  新增: {set(actual.index) - set(expected.index)}\n"
        f"  缺少: {set(expected.index) - set(actual.index)}"
    )
    pd.testing.assert_frame_equal(
        actual, expected, rtol=RTOL, atol=ATOL, check_dtype=False,
        obj="df_cuted fingerprint",
    )


@pytest.mark.parametrize("name", NUMERIC_ARTIFACTS)
def test_numeric_artifact_matches_baseline(chain, name):
    """數值產物需與 baseline 相符（df_benchmark / df_pnl / df_ic）。"""
    expected = pd.read_parquet(_numeric_path(name))
    actual = chain[name]

    assert list(actual.columns) == list(expected.columns), (
        f"{name} 欄位組成改變\n"
        f"  新增: {set(actual.columns) - set(expected.columns)}\n"
        f"  缺少: {set(expected.columns) - set(actual.columns)}"
    )
    assert len(actual) == len(expected), (
        f"{name} 列數改變: {len(expected)} -> {len(actual)}"
    )

    pd.testing.assert_frame_equal(
        actual.reset_index(drop=True),
        expected.reset_index(drop=True),
        rtol=RTOL,
        atol=ATOL,
        check_dtype=False,
        check_categorical=False,
        obj=name,
    )


@pytest.mark.parametrize("name", STRING_ARTIFACTS)
def test_string_artifact_matches_baseline(chain, name):
    """df_info / df_info2 是格式化後的字串表（含 '%'），逐格比對。"""
    # dtype=str 不可省：否則 '0.0030' 會被推斷為 float 而在讀回時失去尾隨零，
    # 造成與實際輸出不符的假警報。
    expected = pd.read_csv(
        _string_path(name), index_col=0, keep_default_na=False, dtype=str
    )
    actual = chain[name].astype(str).fillna("")

    assert list(actual.index) == list(expected.index), f"{name} index 改變"
    assert list(actual.columns) == list(expected.columns), f"{name} 欄位改變"

    diffs = [
        f"  [{r}, {c}]: {expected.at[r, c]!r} -> {actual.at[r, c]!r}"
        for r in expected.index
        for c in expected.columns
        if actual.at[r, c] != expected.at[r, c]
    ]
    assert not diffs, f"{name} 有 {len(diffs)} 格不符:\n" + "\n".join(diffs)


def test_reproducible_under_seed(panel):
    """固定種子時整條鏈必須逐位元重現。

    ext_out_3std(factor_func.py:487) 與 grouping_factor(factor_func.py:826) 內部
    呼叫 np.random.normal 但未設種子，靠 seeded() 固定全域 RNG 才得以重現。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with seeded():
            a = run_pandas_chain(panel)
        with seeded():
            b = run_pandas_chain(panel)

    for key in ["df_cuted", "df_benchmark", "df_pnl", "df_ic"]:
        assert a[key].equals(b[key]), f"{key} 在相同種子下未能重現"
    assert a["df_info2"].equals(b["df_info2"])


def test_noise_is_numerically_negligible(panel):
    """記錄一項對重構重要的事實：內部噪音對結果的影響可忽略。

    ext_out_3std / grouping_factor 加入 1e-10 量級噪音以避免 qcut 分箱邊界重複。
    實測顯示，即使完全不設種子：
      - 分組指派、df_pnl、rank_ic 完全一致
      - 僅原始 float ic / ir 漂移約 1e-10

    意義：polars 版**不需要**複製噪音的抽樣序列，只需在 1e-8 容差內符合語意即可。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = run_pandas_chain(panel)  # 刻意不設種子
        b = run_pandas_chain(panel)

    grp = "test_factor_group"
    assert (a["df_cuted"][grp].values == b["df_cuted"][grp].values).all(), (
        "噪音改變了分組指派 —— 容差假設需重新評估"
    )
    assert np.nanmax(np.abs(a["df_ic"]["rank_ic"] - b["df_ic"]["rank_ic"])) == 0.0

    drift = np.nanmax(np.abs(a["df_ic"]["ic"] - b["df_ic"]["ic"]))
    assert drift < ATOL, f"ic 漂移 {drift:.3e} 已超出容差 {ATOL:.0e}"
