from __future__ import annotations

import pandas as pd

from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.execution import AssetSpec
from src.strategies.base import BaseStrategy, StrategySignal


class WinningStrategy(BaseStrategy):
    name = "winning"

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i == 0:
            ts = data.index[i]
            return StrategySignal(ts, "long", stop_loss=95.0, take_profit=110.0, metadata={"strategy": self.name})
        return None


def _run(spread: float, slippage: float, commission: float) -> float:
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [111.0, 111.0],
            "low": [99.0, 99.0],
            "close": [100.0, 100.0],
            "spread": [spread, spread],
        },
        index=pd.date_range("2026-01-01 15:00", periods=2, freq="h", tz="Europe/Paris"),
    )
    cfg = BacktestConfig(spread_points=spread, slippage_points=slippage, commission_per_lot_round_turn=commission, no_overnight=False)
    result = BacktestEngine(cfg, AssetSpec("TEST", point=1.0, contract_size=1.0)).run(data, WinningStrategy({}))
    return float(result.trades.iloc[0]["net_pnl"])


def test_higher_costs_reduce_net_pnl() -> None:
    base = _run(spread=1.0, slippage=0.0, commission=1.0)
    stressed = _run(spread=1.5, slippage=0.0, commission=1.5)

    assert stressed < base

