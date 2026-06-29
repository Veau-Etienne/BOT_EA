from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.donchian import donchian_high, donchian_low
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUFailedBreakoutReversal(BaseStrategy):
    name = "xau_failed_breakout_reversal"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        donchian_period = int(self.config.get("donchian_period", 20))
        atr_period = int(self.config.get("atr_period", 14))
        out["atr"] = atr(out, atr_period)
        out["donchian_high_prev"] = donchian_high(out, donchian_period).shift(1)
        out["donchian_low_prev"] = donchian_low(out, donchian_period).shift(1)
        out["donchian_mid_prev"] = (out["donchian_high_prev"] + out["donchian_low_prev"]) / 2
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("sessions", [])):
            return None
        no_new_after = self.config.get("no_new_trade_after")
        if no_new_after and ts.time() > parse_hhmm(no_new_after):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None
        if pd.isna(row["atr"]) or float(row["atr"]) <= 0:
            return None

        reentry_bars = int(self.config.get("reentry_bars", 3))
        sl_atr = float(self.config.get("sl_atr_multiplier", 1.0))
        tp_r = float(self.config.get("tp_r_multiple", 1.5))
        tp_mode = str(self.config.get("tp_mode", "range_mid"))
        close = float(row["close"])
        atr_value = float(row["atr"])

        for lookback in range(1, reentry_bars + 1):
            j = i - lookback
            if j < 1:
                break
            breakout = data.iloc[j]
            if pd.isna(breakout["donchian_high_prev"]) or pd.isna(breakout["donchian_low_prev"]):
                continue

            channel_high = float(breakout["donchian_high_prev"])
            channel_low = float(breakout["donchian_low_prev"])
            channel_mid = (channel_high + channel_low) / 2

            if float(breakout["high"]) > channel_high and close < channel_high:
                stop = max(float(breakout["high"]), float(row["high"])) + 0.10 * atr_value
                if stop <= close:
                    stop = close + sl_atr * atr_value
                risk = stop - close
                target = channel_mid if tp_mode == "range_mid" and channel_mid < close else close - risk * tp_r
                return StrategySignal(
                    ts,
                    "short",
                    stop,
                    target,
                    {"strategy": self.name, "failed_breakout_time": str(data.index[j]), "atr": atr_value},
                )

            if float(breakout["low"]) < channel_low and close > channel_low:
                stop = min(float(breakout["low"]), float(row["low"])) - 0.10 * atr_value
                if stop >= close:
                    stop = close - sl_atr * atr_value
                risk = close - stop
                target = channel_mid if tp_mode == "range_mid" and channel_mid > close else close + risk * tp_r
                return StrategySignal(
                    ts,
                    "long",
                    stop,
                    target,
                    {"strategy": self.name, "failed_breakout_time": str(data.index[j]), "atr": atr_value},
                )

        return None
