from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows


@dataclass(frozen=True)
class LondonRange:
    high: float
    low: float


class EURLondonMeanReversion(BaseStrategy):
    name = "eur_london_mean_reversion"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        self._ranges = self._build_ranges(out)
        return out

    def _build_ranges(self, data: pd.DataFrame) -> dict[object, LondonRange]:
        ranges: dict[object, LondonRange] = {}
        asia_windows = self.config.get("asia_range", [["00:00", "07:00"]])
        for day, day_df in data.groupby(data.index.date):
            mask = [in_time_windows(ts, asia_windows) for ts in day_df.index]
            asia = day_df.loc[mask]
            if len(asia):
                ranges[day] = LondonRange(high=float(asia["high"].max()), low=float(asia["low"].min()))
        return ranges

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i < 1:
            return None
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("london_session", [["08:00", "11:30"]])):
            return None
        range_info = getattr(self, "_ranges", {}).get(ts.date())
        if range_info is None:
            return None
        atr_value = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
        if atr_value <= 0 or atr_value < float(self.config.get("atr_min_filter", 0)):
            return None

        close = float(row["close"])
        tp_r = float(self.config.get("tp_r_multiple", 1.0))
        mid = (range_info.high + range_info.low) / 2

        failed_up = float(prev["high"]) > range_info.high and close < range_info.high
        if failed_up:
            stop = max(float(prev["high"]), float(row["high"])) + 0.10 * atr_value
            risk = stop - close
            target = mid if self.config.get("tp_mode", "range_mid") == "range_mid" and mid < close else close - risk * tp_r
            return StrategySignal(ts, "short", stop, target, {"strategy": self.name, "atr": atr_value})

        failed_down = float(prev["low"]) < range_info.low and close > range_info.low
        if failed_down:
            stop = min(float(prev["low"]), float(row["low"])) - 0.10 * atr_value
            risk = close - stop
            target = mid if self.config.get("tp_mode", "range_mid") == "range_mid" and mid > close else close + risk * tp_r
            return StrategySignal(ts, "long", stop, target, {"strategy": self.name, "atr": atr_value})

        return None
