"""深度回測的面板準備：前向報酬、lag 報酬與成交日的可交易性。

因子在 T 日形成（只能使用 T 日收盤前的資訊），T+1 收盤進場，名目上 T+n+1 收盤出場。
前向報酬 = close_adj[出場日] / close_adj[進場日] - 1。

跨越停牌期間照實計算，不設 NA——見 docs/adr/0001-cross-halt-returns-not-na.md。

可交易性必須在**真正成交的那一天**判定（ADR-0002），而那兩天都不是 T：進場日是
T+1、出場日是 T+n+1（或更早）。面板因此把位移後的旗標一併備妥，評估層只做統計：

- ``entry_can_buy``：進場日（T+1）買得到嗎
- ``{n}day_can_sell``：出場日（含提前出場）賣得掉嗎
- ``{n}day_early_exit``：這筆持有是否因 ``avoid_early`` 而提前出清
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import polars as pl

#: 面板一定要有的欄位。上游見 src/factor/components/align_and_adjust.py。
REQUIRED_COLS: tuple[str, ...] = (
    "symbol",
    "date",
    "close_adj",
    "untradable",
    "can_buy",
    "can_sell",
)

#: 有就帶、沒有也能跑的欄位。avoid_early 由「提前出場」使用。
OPTIONAL_COLS: tuple[str, ...] = ("avoid_early",)


@dataclass(frozen=True)
class DeepBacktestConfig:
    """深度回測的全部設定。面板準備與評估共用同一份。"""

    #: 持有期 n（交易日）。一次深度回測只驗證單一持有期。
    holding_period: int = 1
    #: 面板要備妥的持有期報酬欄，供不同 config 重複使用同一份面板。
    return_periods: tuple[int, ...] = (1, 3, 5, 10, 20, 30)
    #: IC 衰減要看到第幾個 lag。
    max_lag: int = 20
    #: 分組數。
    group_count: int = 5
    #: 去極值（只截斷不置中，因子量級不變）。
    winsorize: bool = True
    winsorize_std: float = 3.0
    #: 打散同值用的噪音，讓 qcut 切得出唯一的分組邊界。沿用 panda_factor 口徑。
    noise_std: float = 1e-10
    #: 亂數種子。None 時行為與 panda_factor 的全域 RNG 一致。
    seed: int | None = None
    #: 因子與面板 join 後的最低覆蓋率，低於此值視為對不上而報錯。
    min_coverage: float = 0.5
    #: 一個交易日至少要有幾檔才納入統計。
    min_names: int = 20
    #: Newey-West 的 lag 長度；None 時依抽樣方式決定（見 nw_lags）。
    newey_west_lags: int | None = None
    #: 手續費率，買賣**皆收**。預設為台股 0.1425% 打 4 折。
    fee_rate: float = 0.001425 * 0.4
    #: 證券交易稅率，**僅賣出**收取。台股普通股 0.3%。
    tax_rate: float = 0.003
    #: 滑點，**單邊**基點；買賣各收一次。20 bps = 0.2%。
    slippage_bps: float = 20.0
    #: 除了必要欄位之外還要留在面板裡的欄位。
    extra_cols: tuple[str, ...] = field(default_factory=tuple)
    price_col: str = "close_adj"

    def __post_init__(self) -> None:
        if self.holding_period < 1:
            raise ValueError(f"holding_period 需為正整數，收到 {self.holding_period}")
        if self.holding_period not in self.return_periods:
            raise ValueError(
                f"holding_period={self.holding_period} 不在 return_periods="
                f"{self.return_periods} 之中，面板不會備妥對應的報酬欄"
            )
        if self.max_lag < 0:
            raise ValueError(f"max_lag 不可為負，收到 {self.max_lag}")
        if self.group_count < 2:
            raise ValueError(f"group_count 至少為 2，收到 {self.group_count}")
        if not 0.0 < self.min_coverage <= 1.0:
            raise ValueError(f"min_coverage 需落在 (0, 1]，收到 {self.min_coverage}")
        for name in ("fee_rate", "tax_rate", "slippage_bps"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不可為負，收到 {getattr(self, name)}")

    @property
    def return_col(self) -> str:
        """本次回測實際使用的報酬欄。"""
        return f"{self.holding_period}day_return"

    @property
    def nw_lags(self) -> int:
        """Newey-West 的 lag 長度。預設 0——序列已經是非重疊的。

        評估層每 ``holding_period`` 個交易日才取一列（ADR-0003），相鄰兩列之間
        沒有共用的持有區間，因此不存在重疊造成的自相關，不需要 HAC 修正。
        ``nw_t``/``nw_p`` 欄位仍然照出，只是在預設值下會與未修正的 ``t``/``p``
        幾乎相同（差別只在標準誤的 ddof）。要看修正後的統計量就明確指定 lag。
        """
        return 0 if self.newey_west_lags is None else self.newey_west_lags

    @property
    def buy_cost_rate(self) -> float:
        """買進一單位權重的成本：手續費 + 滑點。證交稅只在賣出時收。"""
        return self.fee_rate + self.slippage_bps / 10_000.0

    @property
    def sell_cost_rate(self) -> float:
        """賣出一單位權重的成本：手續費 + 證交稅 + 滑點。"""
        return self.fee_rate + self.tax_rate + self.slippage_bps / 10_000.0


def prepare_panel(raw: pl.DataFrame, config: DeepBacktestConfig) -> pl.DataFrame:
    """
    把原始日線展開成深度回測用的面板。

    純函數：同一份輸入產生同一份輸出，且不修改 raw。

    產出的報酬欄：
    - ``{n}day_return`` = close_adj[出場日] / close_adj[T+1] - 1
    - ``returns_lag{i}`` = 第 i 個交易日之後的單日報酬，供 IC 衰減與自相關使用

    產出的可交易性欄（都指向真正成交的那一天，不是 T）：
    - ``entry_can_buy``：T+1 的 ``can_buy``
    - ``{n}day_can_sell``：實際出場日的 ``can_sell``
    - ``{n}day_early_exit``：是否提前出清

    出場日取名目出場日 T+n+1 與持有期間內第一個 ``avoid_early`` 日的較早者。沒有
    ``avoid_early`` 欄位時一律取名目日期。

    位移一律以「有序區塊內的位置」計算並在 symbol 邊界填 null。停牌日在面板中
    是有列的，因此跨停牌的位移自然會落在正確的價格上；真正的日曆缺口也照實跨過，
    不因為中間隔了多個日曆日就視為缺失（ADR-0001）。
    """
    missing = [c for c in REQUIRED_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"原始日線缺少必要欄位 {missing}")

    price = config.price_col
    if price not in raw.columns:
        raise ValueError(f"原始日線缺少價格欄位 {price!r}")

    unknown_extra = [c for c in config.extra_cols if c not in raw.columns]
    if unknown_extra:
        raise ValueError(f"extra_cols 指定了不存在的欄位 {unknown_extra}")

    keep = [
        *REQUIRED_COLS,
        *(c for c in OPTIONAL_COLS if c in raw.columns),
        *(c for c in config.extra_cols if c not in REQUIRED_COLS),
    ]
    if price not in keep:
        keep.append(price)

    selected = raw.select(*dict.fromkeys(keep))

    # 所有進入統計的浮點數一律 Float64：Float32 在市值（mean≈1e6）量級的因子上
    # 讓 Pearson IC 誤差達 5.8e-04，成交額（mean≈1e9）量級直接算出 nan，因為
    # 變異數走 E[x²]-E[x]²，平均值遠大於標準差時發生災難性抵消。
    # 只升 Float32，不動整數旗標——那些不以數值身分進入統計。
    to_f64 = [
        pl.col(name).cast(pl.Float64)
        for name, dtype in selected.schema.items()
        if dtype == pl.Float32 or name == price
    ]

    lf = (
        selected.lazy()
        .with_columns(to_f64)
        # 上游（align_and_adjust）以 Qlib 面板為主索引 left-join DuckDB，DuckDB 沒有
        # 對應列的 pair 會補出價格但留下 null 旗標。沒有來源資料就等於沒有可交易的
        # 證據，因此一律往「不可交易 / 不在宇宙」的方向填——這個方向只會少算部位，
        # 不會憑空多出買不到的交易。
        .with_columns(
            pl.col("untradable").fill_null(1),
            pl.col("can_buy").fill_null(0),
            pl.col("can_sell").fill_null(0),
        )
        .sort(["symbol", "date"])
    )

    has_avoid_early = "avoid_early" in selected.columns
    if has_avoid_early:
        # 沒有減資停牌的證據就是沒有——填 1 會讓每一筆持有都被迫提前出清。
        lf = lf.with_columns(pl.col("avoid_early").fill_null(0))

    leads: Dict[tuple[str, int], pl.Expr] = {}

    def lead(col: str, n: int) -> pl.Expr:
        """有序區塊內往後 n 列的值；跨 symbol 邊界填 null。"""
        key = (col, n)
        if key not in leads:
            leads[key] = (
                pl.when(pl.col("symbol") == pl.col("symbol").shift(-n))
                .then(pl.col(col).shift(-n))
                .otherwise(None)
            )
        return leads[key]

    def at_exit(col: str, n: int) -> pl.Expr:
        """實際出場日的欄位值：名目 T+n+1，遇 avoid_early 則取第一個發生日。

        coalesce 由近而遠取第一個非 null 的分支，因此自然選中最早的 avoid_early 日；
        整段期間都沒有時落到最後的名目出場日。
        """
        nominal = lead(col, n + 1)
        if not has_avoid_early:
            return nominal
        early = [
            pl.when(lead("avoid_early", k) == 1).then(lead(col, k))
            for k in range(1, n + 1)
        ]
        return pl.coalesce(*early, nominal) if early else nominal

    def early_exit_flag(n: int) -> pl.Expr:
        """名目出場日之前（不含）是否踩到 avoid_early。"""
        if not has_avoid_early or n < 1:
            return pl.lit(False)
        return pl.any_horizontal(
            [lead("avoid_early", k) == 1 for k in range(1, n + 1)]
        ).fill_null(False)

    periods = sorted(set(config.return_periods))

    # T+1 進場、名目 T+n+1 出場（遇 avoid_early 提前）
    lf = lf.with_columns(
        [
            (at_exit(price, n) / lead(price, 1) - 1).alias(f"{n}day_return")
            for n in periods
        ]
        # 可交易性判在成交日：買在 T+1、賣在實際出場日（ADR-0002）
        + [lead("can_buy", 1).fill_null(0).alias("entry_can_buy")]
        + [
            at_exit("can_sell", n).fill_null(0).alias(f"{n}day_can_sell")
            for n in periods
        ]
        + [early_exit_flag(n).alias(f"{n}day_early_exit") for n in periods]
    )
    # returns_lag{i}：第 i 個交易日之後的單日報酬，即 T+i+1 進場、T+i+2 出場。
    # 診斷用，不套用提前出場——它衡量的是因子資訊的衰減，不對應可交易策略。
    lf = lf.with_columns(
        [
            (lead(price, i + 2) / lead(price, i + 1) - 1).alias(f"returns_lag{i}")
            for i in range(config.max_lag + 1)
        ]
    )
    return lf.collect()
