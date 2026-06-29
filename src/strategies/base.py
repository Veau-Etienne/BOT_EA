from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class StrategySignal:
    timestamp: pd.Timestamp
    direction: Direction
    stop_loss: float
    take_profit: float
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStrategy:
    name = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        return data.copy()

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        raise NotImplementedError

    @property
    def risk_per_trade_pct(self) -> float:
        return float(self.config.get("risk_per_trade_pct", 0.25))

    @property
    def max_trades_per_day(self) -> int | None:
        value = self.config.get("max_trades_per_day")
        return int(value) if value is not None else None
