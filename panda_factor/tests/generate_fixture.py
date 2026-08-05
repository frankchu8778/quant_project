"""確定性合成因子面板的建構器。

`build_panel()` 由 conftest 的 panel fixture 在測試時即時呼叫，面板本身不進版控
（見 conftest.PANEL_FINGERPRINT_PATH 的說明）。

直接執行本檔會（重新）產生面板指紋檔，供 test_fixture_is_stable 驗證跨環境一致性：

    python tests/generate_fixture.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from conftest import FIXTURE_DIR, PANEL_FINGERPRINT_PATH

N_SYMBOLS = 200
N_DAYS = 300  # 前向報酬最多用到 T+31，實際可用交易日約 270
FIXTURE_SEED = 4242

# 對齊 single_factor_eval.DEFAULT_RETURN_WINDOWS
# (名稱, 賣出日相對偏移, 進場日偏移)：1day_return = close[T+2]/close[T+1] - 1
RETURN_WINDOWS = (
    ("1day_return", 2, 1),
    ("3day_return", 4, 1),
    ("5day_return", 6, 1),
    ("10day_return", 11, 1),
    ("20day_return", 21, 1),
    ("30day_return", 31, 1),
)


def build_panel() -> pd.DataFrame:
    rng = np.random.default_rng(FIXTURE_SEED)

    dates = pd.bdate_range("2023-01-02", periods=N_DAYS)
    symbols = [f"{i:06d}.SZ" for i in range(N_SYMBOLS)]

    # 每檔一條隨機漫步價格序列
    daily_ret = rng.normal(0.0, 0.02, size=(N_DAYS, N_SYMBOLS))
    close = 100.0 * np.cumprod(1.0 + daily_ret, axis=0)

    df = pd.DataFrame(
        {
            "date": np.repeat(dates.values, N_SYMBOLS),
            "symbol": np.tile(symbols, N_DAYS),
            "close_adj": close.reshape(-1),
        }
    )
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # 前向報酬
    grp = df.groupby("symbol")["close_adj"]
    for name, end_lead, start_lead in RETURN_WINDOWS:
        df[name] = grp.shift(-end_lead) / grp.shift(-start_lead) - 1.0

    # 因子：對次日報酬有微弱預測力（訊號 + 大量噪音）。
    # 係數刻意壓到讓 Rank_IC 落在 0.03~0.05 的真實區間 —— 訊號過強會使分組極度穩定，
    # 反而掩蓋弱因子才會觸發的分箱邊界與 IC 正負號翻轉等邊界情況。
    signal = df["1day_return"].to_numpy()
    noise = rng.normal(0.0, 1.0, size=len(df))
    with np.errstate(invalid="ignore"):
        df["test_factor"] = np.where(np.isfinite(signal), signal * 1.5, 0.0) + noise

    # 注入少量缺值與極值，以涵蓋 inf/NaN 清理路徑（process_inf=True）
    n = len(df)
    nan_idx = rng.choice(n, size=int(n * 0.005), replace=False)
    df.loc[nan_idx, "test_factor"] = np.nan
    inf_idx = rng.choice(n, size=200, replace=False)
    df.loc[inf_idx[:100], "test_factor"] = np.inf
    df.loc[inf_idx[100:], "test_factor"] = -np.inf

    # 少量不可交易標記
    df["untradable"] = 0
    untradable_idx = rng.choice(n, size=int(n * 0.01), replace=False)
    df.loc[untradable_idx, "untradable"] = 1

    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)


def panel_fingerprint(df: pd.DataFrame) -> pd.DataFrame:
    """面板的逐欄統計指紋，用於驗證 default_rng 位元流的跨版本穩定性。

    統計量刻意只在**有限值**上計算：test_factor 欄含刻意注入的 ±inf，若直接 sum
    會得到 NaN、min/max 得到 ±inf，指紋就退化成只檢查列數 —— 而 assert_frame_equal
    視 NaN 與 NaN 相等，該欄的任何數值變動都會靜默通過。inf 的個數另外單獨記錄。
    """
    rows = []
    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        is_object = df[col].dtype == object
        finite = s[np.isfinite(s)] if not is_object else s.dropna()
        rows.append(
            {
                "column": col,
                "count": float(len(s)),
                "nan_count": float(df[col].isna().sum()),
                "nunique": float(df[col].nunique(dropna=True)),
                "pos_inf": float(np.isposinf(s).sum()) if not is_object else 0.0,
                "neg_inf": float(np.isneginf(s).sum()) if not is_object else 0.0,
                "finite_sum": float(finite.sum()) if len(finite) else 0.0,
                "finite_min": float(finite.min()) if len(finite) else 0.0,
                "finite_max": float(finite.max()) if len(finite) else 0.0,
            }
        )
    return pd.DataFrame(rows).set_index("column")


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    df = build_panel()
    panel_fingerprint(df).to_csv(PANEL_FINGERPRINT_PATH)
    print(f"已寫入 {PANEL_FINGERPRINT_PATH}")
    print(f"  形狀      : {df.shape}")
    print(f"  日期範圍  : {df['date'].min().date()} ~ {df['date'].max().date()}")
    print(f"  標的數    : {df['symbol'].nunique()}")
    print(f"  因子 NaN  : {df['test_factor'].isna().sum()}")
    print(f"  因子 inf  : {np.isinf(df['test_factor']).sum()}")
    print(f"  不可交易  : {int(df['untradable'].sum())}")


if __name__ == "__main__":
    main()
