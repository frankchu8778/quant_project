"""pytest 共用設定與 fixture。

本測試套件的目的是為 pandas → polars 重構建立回歸安全網。
專案原本零測試覆蓋，這裡的 golden-master 是唯一的正確性基準。
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TESTS_DIR / "fixtures"
BASELINE_DIR = TESTS_DIR / "baseline"

# 讓測試永遠針對「本 repo 內」的 panda_factor，而非 editable install 記錄的絕對路徑。
# setuptools 的 editable finder 是 sys.meta_path.append()，排在 PathFinder 之後，
# 因此把本地套件目錄插到 sys.path 最前面即可勝出。
# 沒有這段時，在 git worktree 或第二份 checkout 中跑 pytest 會靜默地測到另一份原始碼。
_PKG_PARENT = TESTS_DIR.parent / "panda_factor"
if (_PKG_PARENT / "panda_factor" / "__init__.py").exists():
    sys.path.insert(0, str(_PKG_PARENT))

# 面板 fixture 為即時生成而非存檔：np.random.default_rng(PCG64) 的位元流在 NumPy
# 版本間有明文相容保證（NEP 19），因此由固定種子重算是確定性的，可省下 4.5MB 版控體積。
# 該保證本身由 test_fixture_is_stable 主動驗證，不是默默假設。
PANEL_FINGERPRINT_PATH = FIXTURE_DIR / "panel_fingerprint.csv"

# 固定種子。ext_out_3std 與 grouping_factor 內部呼叫 np.random.normal 但未設種子，
# 必須由外部固定全域 RNG，golden-master 才可重現。詳見 seeded()。
GOLDEN_SEED = 20260805


def pytest_addoption(parser):
    parser.addoption(
        "--update-baseline",
        action="store_true",
        default=False,
        help="重新產生 golden-master baseline artifacts（會覆寫 tests/baseline/）",
    )


@pytest.fixture(scope="session")
def update_baseline(request) -> bool:
    return bool(request.config.getoption("--update-baseline"))


@contextlib.contextmanager
def seeded(seed: int = GOLDEN_SEED):
    """暫時固定 numpy 全域 RNG，離開時還原原有狀態。

    ext_out_3std(factor_func.py:487) 與 grouping_factor(factor_func.py:826) 都以
    np.random.normal 加入 1e-10 量級的噪音以避免 qcut 分箱邊界重複，兩者皆未設種子。
    它們用的是 numpy 全域 RNG，因此在此固定全域種子即可讓整條鏈可重現。
    """
    state = np.random.get_state()
    try:
        np.random.seed(seed)
        yield
    finally:
        np.random.set_state(state)


@pytest.fixture
def seed():
    """把 seeded() 以 fixture 形式提供給測試。"""
    return seeded


@pytest.fixture(scope="session")
def panel() -> pd.DataFrame:
    """合成的日頻因子面板（由固定種子確定性生成）。

    欄位：date, symbol, close_adj, untradable, test_factor,
          1day/3day/5day/10day/20day/30day_return
    刻意「不」包含 returns_lag*，以便讓 cal_pct_lag 也被測試涵蓋。
    """
    from generate_fixture import build_panel

    return build_panel()
