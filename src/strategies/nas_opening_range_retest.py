from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import parse_hhmm


@dataclass
class RetestState:
    high: float
    low: float
    ready_after: pd.Timestamp
    broken_up: bool = False
    broken_down: bool = False
    traded_long: bool = False
    traded_short: bool = False


class NASOpeningRangeRetest(BaseStrategy):
    name = "nas_opening_range_retest"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        self._states = self._build_states(out)
        return out

    def _build_states(self, data: pd.DataFrame) -> dict[object, RetestState]:
        states: dict[object, RetestState] = {}
        start = parse_hhmm(self.config.get("session_start", "15:30"))
        bars = max(1, int(self.config.get("opening_range_minutes", 30)) // 15)
        for day, day_df in data.groupby(data.index.date):
            window = day_df[day_df.index.time >= start].head(bars)
            if len(window) == bars:
                states[day] = RetestState(high=float(window["high"].max()), low=float(window["low"].min()), ready_after=window.index[-1])
        return states

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        ts = data.index[i]
        state = getattr(self, "_states", {}).get(ts.date())
        if state is None or ts <= state.ready_after:
            return None
        if ts.time() > parse_hhmm(self.config.get("trade_until", "18:00")):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None
        atr_value = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
        if atr_value <= 0 or atr_value < float(self.config.get("atr_min_filter", 0)):
            return None

        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        tolerance = float(self.config.get("retest_tolerance_atr", 0.25)) * atr_value
        tp_r = float(self.config.get("tp_r_multiple", 1.5))

        if close > state.high:
            state.broken_up = True
        if close < state.low:
            state.broken_down = True

        if state.broken_up and not state.traded_long and low <= state.high + tolerance and close > state.high:
            stop = min(state.low, low - 0.10 * atr_value)
            risk = close - stop
            if risk <= 0:
                return None
            state.traded_long = True
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_value})

        if state.broken_down and not state.traded_short and high >= state.low - tolerance and close < state.low:
            stop = max(state.high, high + 0.10 * atr_value)
            risk = stop - close
            if risk <= 0:
                return None
            state.traded_short = True
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_value})

        return None
