from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.ema import ema
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class NASTrendPullback(BaseStrategy):
    name = "nas_trend_pullback"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["ema_fast"] = ema(out["close"], int(self.config.get("ema_fast", 20)))
        out["ema_mid"] = ema(out["close"], int(self.config.get("ema_mid", 50)))
        out["ema_slow"] = ema(out["close"], int(self.config.get("ema_slow", 200)))
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        out["ema_mid_slope"] = out["ema_mid"] - out["ema_mid"].shift(int(self.config.get("slope_lookback", 4)))
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i < 2:
            return None
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("sessions", [["15:45", "18:00"]])):
            return None
        if ts.time() < parse_hhmm(self.config.get("avoid_until", "15:45")):
            return None
        if ts.time() > parse_hhmm(self.config.get("trade_until", "18:00")):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None
        if pd.isna(row["ema_slow"]) or pd.isna(row["ema_mid_slope"]) or pd.isna(row["atr"]) or float(row["atr"]) <= 0:
            return None
        atr_value = float(row["atr"])
        if atr_value < float(self.config.get("atr_min_filter", 0)):
            return None

        close = float(row["close"])
        open_ = float(row["open"])
        tp_r = float(self.config.get("tp_r_multiple", 1.5))
        sl_atr = float(self.config.get("sl_atr_multiplier", 1.5))
        swing_lookback = int(self.config.get("swing_lookback", 5))
        recent = data.iloc[max(0, i - swing_lookback) : i + 1]
        pullback_ema = "ema_fast" if int(self.config.get("pullback_ema", 20)) <= 20 else "ema_mid"

        long_ok = close > float(row["ema_slow"]) and float(row["ema_mid_slope"]) > 0
        short_ok = close < float(row["ema_slow"]) and float(row["ema_mid_slope"]) < 0
        pullback_long = float(prev["low"]) <= float(prev[pullback_ema])
        pullback_short = float(prev["high"]) >= float(prev[pullback_ema])
        resume_long = close > open_ and close > float(prev["high"])
        resume_short = close < open_ and close < float(prev["low"])

        if long_ok and pullback_long and resume_long:
            stop = float(recent["low"].min())
            if stop >= close or close - stop < 0.25 * atr_value:
                stop = close - sl_atr * atr_value
            risk = close - stop
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_value})

        if short_ok and pullback_short and resume_short:
            stop = float(recent["high"].max())
            if stop <= close or stop - close < 0.25 * atr_value:
                stop = close + sl_atr * atr_value
            risk = stop - close
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_value})

        return None
