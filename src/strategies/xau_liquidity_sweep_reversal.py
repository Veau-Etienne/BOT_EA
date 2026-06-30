from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAULiquiditySweepReversal(BaseStrategy):
    """XAU M15 — Liquidity sweep of range extremes then re-entry into range.

    Hypothesis: XAUUSD frequently hunts intraday highs/lows and then
    re-integrates the range. We trade the re-entry bar after the sweep,
    not the breakout itself.
    """

    name = "xau_liquidity_sweep_reversal"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        atr_period = int(self.config.get("atr_period", 14))
        # range_lookback bars define the reference range.
        # shift(2): excludes bar i-1 so the range is established before the sweep bar.
        range_lookback = int(self.config.get("range_lookback", 20))
        out["atr"] = atr(out, atr_period)
        out["range_high"] = out["high"].rolling(range_lookback, min_periods=range_lookback).max().shift(2)
        out["range_low"] = out["low"].rolling(range_lookback, min_periods=range_lookback).min().shift(2)
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i < 3:
            return None
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        ts = data.index[i]

        sessions = self.config.get("sessions", [["08:00", "11:30"], ["14:30", "18:00"]])
        if not in_time_windows(ts, sessions):
            return None
        no_new_after = self.config.get("no_new_trade_after")
        if no_new_after and ts.time() > parse_hhmm(no_new_after):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")):
            if float(row["spread"]) > float(max_spread):
                return None

        if pd.isna(row["atr"]) or pd.isna(row["range_high"]) or pd.isna(row["range_low"]):
            return None
        atr_val = float(row["atr"])
        if atr_val <= 0:
            return None

        atr_min = float(self.config.get("atr_min_filter", 0))
        if atr_val < atr_min:
            return None

        range_high = float(row["range_high"])
        range_low = float(row["range_low"])
        range_size = range_high - range_low
        if range_size <= 0:
            return None
        range_mid = (range_high + range_low) / 2.0

        close = float(row["close"])
        prev_high = float(prev["high"])
        prev_low = float(prev["low"])
        sl_atr_buffer = float(self.config.get("sl_atr_buffer", 0.5))
        tp_mode = self.config.get("tp_mode", "range_mid")
        tp_r = float(self.config.get("tp_r_multiple", 1.5))

        # Short: previous bar swept above range_high, current bar closes below range_high
        if prev_high > range_high and close < range_high:
            stop = prev_high + sl_atr_buffer * atr_val
            risk = stop - close
            if risk <= 0 or risk < 0.1 * atr_val:
                return None
            if tp_mode == "range_mid" and range_mid < close:
                target = range_mid
            else:
                target = close - risk * tp_r
            if target >= close:
                return None
            return StrategySignal(ts, "short", stop, target, {"strategy": self.name, "atr": atr_val})

        # Long: previous bar swept below range_low, current bar closes above range_low
        if prev_low < range_low and close > range_low:
            stop = prev_low - sl_atr_buffer * atr_val
            risk = close - stop
            if risk <= 0 or risk < 0.1 * atr_val:
                return None
            if tp_mode == "range_mid" and range_mid > close:
                target = range_mid
            else:
                target = close + risk * tp_r
            if target <= close:
                return None
            return StrategySignal(ts, "long", stop, target, {"strategy": self.name, "atr": atr_val})

        return None
