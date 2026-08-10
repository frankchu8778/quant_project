"""因子資料準備與共用元件。"""

from __future__ import annotations

from typing import Any

__all__ = ["load_aligned_adjusted_daily"]


def __getattr__(name: str) -> Any:
    if name == "load_aligned_adjusted_daily":
        from src.factor.components.align_and_adjust import load_aligned_adjusted_daily

        return load_aligned_adjusted_daily
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
