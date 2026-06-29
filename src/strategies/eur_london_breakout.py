from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows


@dataclass(frozen=True)
class AsiaRange:
    high: float
    low: float


class EURLondonBreakout(BaseStrategy):
    name = "eur_london_breakout"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        self._ranges = self._build_ranges(out)
        return out

    def _build_ranges(self, data: pd.DataFrame) -> dict[object, AsiaRange]:
        ranges: dict[object, AsiaRange] = {}
        asia_windows = self.config.get("asia_range", [["00:00", "07:00"]])
        for day, day_df in data.groupby(data.index.date):
            mask = [in_time_windows(ts, asia_windows) for ts in day_df.index]
            asia = day_df.loc[mask]
            if len(asia):
                ranges[day] = AsiaRange(high=float(asia["high"].max()), low=float(asia["low"].min()))
        return ranges

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("london_session", [["08:00", "11:30"]])):
            return None
        range_info = getattr(self, "_ranges", {}).get(ts.date())
        if range_info is None:
            return None
        if pd.isna(row["atr"]) or float(row["atr"]) < float(self.config.get("min_atr", 0)):
            return None

        close = float(row["close"])
        risk = max(range_info.high - range_info.low, float(row["atr"]))
        tp_r = float(self.config.get("tp_r", 1.8))

        if close > range_info.high:
            stop = range_info.low
            target = close + risk * tp_r
            return StrategySignal(ts, "long", stop, target, {"strategy": self.name, "asia_range": risk})
        if close < range_info.low:
            stop = range_info.high
            target = close - risk * tp_r
            return StrategySignal(ts, "short", stop, target, {"strategy": self.name, "asia_range": risk})
        return None
