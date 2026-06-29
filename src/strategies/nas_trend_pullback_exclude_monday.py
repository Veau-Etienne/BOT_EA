from __future__ import annotations

import pandas as pd

from src.strategies.base import StrategySignal
from src.strategies.nas_trend_pullback import NASTrendPullback


class NASTrendPullbackExcludeMonday(NASTrendPullback):
    name = "nas_trend_pullback_exclude_monday"

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        ts = data.index[i]
        if ts.weekday() == 0:
            return None
        signal = super().generate_signal(i, data)
        if signal is not None:
            signal.metadata["strategy"] = self.name
        return signal
