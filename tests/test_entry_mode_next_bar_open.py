from __future__ import annotations

import pandas as pd

from src.backtest.engine import BacktestConfig, BacktestEngine
from src.backtest.execution import AssetSpec
from src.strategies.base import BaseStrategy, StrategySignal


class OneSignalStrategy(BaseStrategy):
    name = "one_signal"

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i == 1:
            ts = data.index[i]
            return StrategySignal(ts, "long", stop_loss=95.0, take_profit=130.0, metadata={"strategy": self.name})
        return None


def test_next_bar_open_uses_next_bar_timestamp_and_keeps_signal_timestamp() -> None:
    data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 110.0, 111.0],
            "high": [101.0, 102.0, 112.0, 112.0],
            "low": [99.0, 100.0, 108.0, 100.0],
            "close": [100.5, 101.5, 111.0, 101.0],
            "spread": [0.0, 0.0, 0.0, 0.0],
        },
        index=pd.date_range("2026-01-01 15:00", periods=4, freq="h", tz="Europe/Paris"),
    )
    cfg = BacktestConfig(entry_mode="next_bar_open", slippage_points=0.0, commission_per_lot_round_turn=0.0, no_overnight=False)
    result = BacktestEngine(cfg, AssetSpec("TEST", point=1.0, contract_size=1.0)).run(data, OneSignalStrategy({}))

    trade = result.trades.iloc[0]
    assert pd.Timestamp(trade["signal_timestamp"]) == data.index[1]
    assert pd.Timestamp(trade["entry_time"]) == data.index[2]
    assert trade["entry_mode"] == "next_bar_open"
    assert float(trade["entry_price"]) == 110.0

