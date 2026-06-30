from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.ema import ema
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUm30SessionMomentumContinuation(BaseStrategy):
    """XAU M30 — Directional signal in London/US session with momentum confirmation.

    Hypothesis: Gold exhibits directional momentum during specific session
    windows. Two consecutive bullish/bearish bars above/below EMA50 signal
    continuation momentum worth fading into at the next open.

    A time stop closes any remaining position after N bars to avoid
    overnight exposure.
    """

    name = "xau_m30_session_momentum_continuation"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        ema_period = int(self.config.get("ema_period", 50))
        atr_period = int(self.config.get("atr_period", 14))
        out["ema50"] = ema(out["close"], ema_period)
        out["atr"] = atr(out, atr_period)
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

        if pd.isna(row["ema50"]) or pd.isna(row["atr"]) or float(row["atr"]) <= 0:
            return None
        atr_val = float(row["atr"])
        atr_min = float(self.config.get("atr_min_filter", 0))
        if atr_val < atr_min:
            return None

        close = float(row["close"])
        open_ = float(row["open"])
        prev_close = float(prev["close"])
        prev_open = float(prev["open"])
        ema50_val = float(row["ema50"])

        # Two consecutive closes in the same direction
        bar_bullish = close > open_
        bar_prev_bullish = prev_close > prev_open
        bar_bearish = close < open_
        bar_prev_bearish = prev_close < prev_open

        sl_atr = float(self.config.get("sl_atr_multiplier", 1.5))
        tp_r = float(self.config.get("tp_r_multiple", 1.5))
        swing_lookback = int(self.config.get("swing_lookback", 3))
        recent = data.iloc[max(0, i - swing_lookback) : i + 1]

        # Long: two bullish bars, close above EMA50
        if bar_bullish and bar_prev_bullish and close > ema50_val:
            stop = close - sl_atr * atr_val
            swing_stop = float(recent["low"].min())
            if swing_stop < stop and close - swing_stop >= 0.25 * atr_val:
                stop = swing_stop
            risk = close - stop
            if risk <= 0:
                return None
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_val})

        # Short: two bearish bars, close below EMA50
        if bar_bearish and bar_prev_bearish and close < ema50_val:
            stop = close + sl_atr * atr_val
            swing_stop = float(recent["high"].max())
            if swing_stop > stop and swing_stop - close >= 0.25 * atr_val:
                stop = swing_stop
            risk = stop - close
            if risk <= 0:
                return None
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_val})

        return None
