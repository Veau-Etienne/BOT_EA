from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.ema import ema
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUm30HTFTrendPullback(BaseStrategy):
    """XAU M30 — HTF trend filter (EMA50 vs EMA200) + pullback to EMA20.

    Hypothesis: XAUUSD M30 is noisy on M15 but the EMA50/200 dual filter
    on M30 helps identify the dominant trend. Pullbacks to EMA20 followed
    by a resumption bar offer an entry with defined risk.
    """

    name = "xau_m30_htf_trend_pullback"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        ema_fast = int(self.config.get("ema_fast", 20))
        ema_mid = int(self.config.get("ema_mid", 50))
        ema_slow = int(self.config.get("ema_slow", 200))
        atr_period = int(self.config.get("atr_period", 14))
        out["ema_fast"] = ema(out["close"], ema_fast)
        out["ema_mid"] = ema(out["close"], ema_mid)
        out["ema_slow"] = ema(out["close"], ema_slow)
        out["atr"] = atr(out, atr_period)
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        if i < 2:
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

        if any(pd.isna(row[col]) for col in ["ema_fast", "ema_mid", "ema_slow", "atr"]):
            return None
        atr_val = float(row["atr"])
        if atr_val <= 0:
            return None
        atr_min = float(self.config.get("atr_min_filter", 0))
        if atr_val < atr_min:
            return None

        close = float(row["close"])
        open_ = float(row["open"])
        ema_fast_val = float(row["ema_fast"])
        ema_mid_val = float(row["ema_mid"])
        ema_slow_val = float(row["ema_slow"])
        prev_ema_fast = float(prev["ema_fast"])

        # Trend filter: EMA50 vs EMA200
        long_trend = ema_mid_val > ema_slow_val
        short_trend = ema_mid_val < ema_slow_val

        # Pullback: previous bar's extreme touched or crossed EMA fast
        pullback_long = float(prev["low"]) <= prev_ema_fast
        pullback_short = float(prev["high"]) >= prev_ema_fast

        # Resume: current bar closes in trend direction, above/below EMA fast
        resume_long = close > open_ and close > float(prev["high"]) and close > ema_fast_val
        resume_short = close < open_ and close < float(prev["low"]) and close < ema_fast_val

        sl_atr = float(self.config.get("sl_atr_multiplier", 1.5))
        tp_r = float(self.config.get("tp_r_multiple", 1.5))
        swing_lookback = int(self.config.get("swing_lookback", 5))
        recent = data.iloc[max(0, i - swing_lookback) : i + 1]

        if long_trend and pullback_long and resume_long:
            stop = float(recent["low"].min())
            if stop >= close or close - stop < 0.25 * atr_val:
                stop = close - sl_atr * atr_val
            risk = close - stop
            if risk <= 0:
                return None
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_val})

        if short_trend and pullback_short and resume_short:
            stop = float(recent["high"].max())
            if stop <= close or stop - close < 0.25 * atr_val:
                stop = close + sl_atr * atr_val
            risk = stop - close
            if risk <= 0:
                return None
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_val})

        return None
