from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import parse_hhmm


@dataclass(frozen=True)
class OpeningRange:
    high: float
    low: float
    ready_after: pd.Timestamp
    atr_at_ready: float


class NASOpeningBreakout(BaseStrategy):
    name = "nas_opening_breakout"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        self._ranges = self._build_ranges(out)
        return out

    def _build_ranges(self, data: pd.DataFrame) -> dict[object, OpeningRange]:
        ranges: dict[object, OpeningRange] = {}
        start = parse_hhmm(self.config.get("session_start", self.config.get("range_start", "15:30")))
        if "opening_range_minutes" in self.config:
            bars = max(1, int(self.config.get("opening_range_minutes", 30)) // 15)
        else:
            bars = int(self.config.get("range_bars", 2))
        for day, day_df in data.groupby(data.index.date):
            window = day_df[day_df.index.time >= start].head(bars)
            if len(window) == bars:
                atr_value = float(window["atr"].iloc[-1]) if "atr" in window and pd.notna(window["atr"].iloc[-1]) else 0.0
                ranges[day] = OpeningRange(
                    high=float(window["high"].max()),
                    low=float(window["low"].min()),
                    ready_after=window.index[-1],
                    atr_at_ready=atr_value,
                )
        return ranges

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        ts = data.index[i]
        range_info = getattr(self, "_ranges", {}).get(ts.date())
        if range_info is None or ts <= range_info.ready_after:
            return None
        if ts.time() > parse_hhmm(self.config.get("trade_until", self.config.get("no_new_trade_after", "18:00"))):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None

        atr_value = float(row["atr"]) if pd.notna(row["atr"]) else 0.0
        min_atr = float(self.config.get("min_atr_filter", self.config.get("min_atr", 0)))
        if atr_value <= 0 or atr_value < min_atr:
            return None

        close = float(row["close"])
        range_size = range_info.high - range_info.low
        if range_size <= 0:
            return None
        range_atr_ratio = range_size / atr_value if atr_value > 0 else 0.0
        min_ratio = float(self.config.get("min_range_atr_ratio", 0.0))
        max_ratio = float(self.config.get("max_range_atr_ratio", 999.0))
        if range_atr_ratio < min_ratio or range_atr_ratio > max_ratio:
            return None

        tp_r = float(self.config.get("tp_r_multiple", self.config.get("tp_r", 2.0)))
        break_even_at_r = self.config.get("break_even_at_r")
        trailing_enabled = bool(self.config.get("trailing_enabled", False) or break_even_at_r is not None)
        trailing_start_r = float(break_even_at_r if break_even_at_r is not None else self.config.get("trailing_start_r", 1.0))

        metadata = {
            "strategy": self.name,
            "range_size": range_size,
            "range_atr_ratio": range_atr_ratio,
            "atr": atr_value,
            "trailing_enabled": trailing_enabled,
            "trailing_start_r": trailing_start_r,
        }

        if close > range_info.high:
            stop = range_info.low
            if close - stop < 0.25 * atr_value:
                stop = close - max(range_size, atr_value)
            risk = close - stop
            if risk <= 0:
                return None
            target = close + range_size * tp_r
            if self.config.get("tp_uses_r", True):
                target = close + risk * tp_r
            return StrategySignal(ts, "long", stop, target, metadata)
        if close < range_info.low:
            stop = range_info.high
            if stop - close < 0.25 * atr_value:
                stop = close + max(range_size, atr_value)
            risk = stop - close
            if risk <= 0:
                return None
            target = close - range_size * tp_r
            if self.config.get("tp_uses_r", True):
                target = close - risk * tp_r
            return StrategySignal(ts, "short", stop, target, metadata)
        return None
