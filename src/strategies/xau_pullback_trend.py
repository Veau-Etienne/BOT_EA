from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.ema import ema
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUPullbackTrend(BaseStrategy):
    name = "xau_pullback_trend"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        ema_fast = int(self.config.get("ema_fast", 20))
        ema_slow = int(self.config.get("ema_slow", 200))
        atr_period = int(self.config.get("atr_period", 14))
        out["ema_fast"] = ema(out["close"], ema_fast)
        out["ema_slow"] = ema(out["close"], ema_slow)
        out["atr"] = atr(out, atr_period)
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i < 2:
            return None
        row = data.iloc[i]
        prev = data.iloc[i - 1]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("sessions", [])):
            return None
        no_new_after = self.config.get("no_new_trade_after")
        if no_new_after and ts.time() > parse_hhmm(no_new_after):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None
        if pd.isna(row["ema_fast"]) or pd.isna(row["ema_slow"]) or pd.isna(row["atr"]) or float(row["atr"]) <= 0:
            return None
        if float(row["atr"]) < float(self.config.get("atr_min_filter", 0)):
            return None

        close = float(row["close"])
        open_ = float(row["open"])
        atr_value = float(row["atr"])
        tp_r = float(self.config.get("tp_r_multiple", 2.0))
        sl_atr = float(self.config.get("sl_atr_multiplier", 1.5))
        swing_lookback = int(self.config.get("swing_lookback", 5))
        start = max(0, i - swing_lookback)
        recent = data.iloc[start : i + 1]

        long_trend = close > float(row["ema_slow"])
        short_trend = close < float(row["ema_slow"])
        pullback_long = float(prev["low"]) <= float(prev["ema_fast"])
        pullback_short = float(prev["high"]) >= float(prev["ema_fast"])
        resume_long = close > open_ and close > float(prev["high"]) and close > float(row["ema_fast"])
        resume_short = close < open_ and close < float(prev["low"]) and close < float(row["ema_fast"])

        if long_trend and pullback_long and resume_long:
            stop = float(recent["low"].min())
            if stop >= close or close - stop < 0.25 * atr_value:
                stop = close - sl_atr * atr_value
            risk = close - stop
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_value})

        if short_trend and pullback_short and resume_short:
            stop = float(recent["high"].max())
            if stop <= close or stop - close < 0.25 * atr_value:
                stop = close + sl_atr * atr_value
            risk = stop - close
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_value})

        return None
