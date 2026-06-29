from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.indicators.donchian import donchian_high, donchian_low
from src.indicators.ema import ema
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUTrendBreakout(BaseStrategy):
    name = "xau_trend_breakout"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        ema_period = int(self.config.get("ema_period", 200))
        donchian_period = int(self.config.get("donchian_period", 20))
        atr_period = int(self.config.get("atr_period", 14))
        out["ema"] = ema(out["close"], ema_period)
        out["atr"] = atr(out, atr_period)
        out["donchian_high_prev"] = donchian_high(out, donchian_period).shift(1)
        out["donchian_low_prev"] = donchian_low(out, donchian_period).shift(1)
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        ts = data.index[i]
        if not in_time_windows(ts, self.config.get("sessions", [])):
            return None
        no_new_after = self.config.get("no_new_trade_after")
        if no_new_after and ts.time() > parse_hhmm(no_new_after):
            return None
        if pd.isna(row["ema"]) or pd.isna(row["atr"]) or pd.isna(row["donchian_high_prev"]) or row["atr"] <= 0:
            return None

        sl_atr = float(self.config.get("sl_atr", 1.5))
        tp_atr = float(self.config.get("tp_atr", 2.5))
        close = float(row["close"])
        signal_meta = {
            "strategy": self.name,
            "atr": float(row["atr"]),
            "trailing_enabled": bool(self.config.get("trailing_enabled", False)),
            "trailing_start_r": float(self.config.get("trailing_start_r", 1.0)),
        }

        if close > float(row["ema"]) and float(row["high"]) > float(row["donchian_high_prev"]):
            stop = close - sl_atr * float(row["atr"])
            target = close + tp_atr * float(row["atr"])
            return StrategySignal(ts, "long", stop, target, signal_meta)

        if close < float(row["ema"]) and float(row["low"]) < float(row["donchian_low_prev"]):
            stop = close + sl_atr * float(row["atr"])
            target = close - tp_atr * float(row["atr"])
            return StrategySignal(ts, "short", stop, target, signal_meta)

        return None
