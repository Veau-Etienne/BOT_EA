from __future__ import annotations

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import in_time_windows, parse_hhmm


class XAUVolatilityCompressionRetest(BaseStrategy):
    """XAU M15 — Volatility compression breakout followed by retest.

    Hypothesis: Pure breakouts on XAU M15 fail frequently, but when
    a tight compression zone breaks and the broken level is successfully
    retested, the edge improves substantially.

    Signal logic (no lookahead):
    - Detect compression in bars [i-compression_bars-1 to i-2]
      (ATR below threshold of its rolling mean).
    - Breakout on bar i-1: close above/below compression range.
    - Retest on bar i: bar touches the broken level but closes on the
      breakout side → entry signal.
    """

    name = "xau_volatility_compression_retest"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        atr_period = int(self.config.get("atr_period", 14))
        atr_ma_period = int(self.config.get("atr_ma_period", 50))
        out["atr"] = atr(out, atr_period)
        out["atr_mean"] = out["atr"].rolling(atr_ma_period, min_periods=atr_ma_period // 2).mean()
        return out

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        compression_bars = int(self.config.get("compression_bars", 8))
        if i < compression_bars + 3:
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

        if pd.isna(row["atr"]) or float(row["atr"]) <= 0:
            return None
        atr_val = float(row["atr"])

        # Compression window: bars strictly before the breakout bar (i-1)
        comp_start = max(0, i - compression_bars - 1)
        comp_end = i - 1  # exclusive → bars [comp_start, comp_end-1] i.e. to i-2
        comp_window = data.iloc[comp_start:comp_end]
        if len(comp_window) < compression_bars // 2:
            return None

        # ATR-based compression check
        threshold = float(self.config.get("compression_threshold", 0.75))
        atr_vals = comp_window["atr"].dropna()
        atr_means = comp_window["atr_mean"].dropna()
        common_idx = atr_vals.index.intersection(atr_means.index)
        if len(common_idx) < 2:
            return None
        valid_means = atr_means.loc[common_idx]
        valid_atrs = atr_vals.loc[common_idx]
        positive_means = valid_means[valid_means > 0]
        if positive_means.empty:
            return None
        ratios = valid_atrs.loc[positive_means.index] / positive_means
        # At least half of the window must be compressed
        if (ratios < threshold).mean() < 0.5:
            return None

        # Compression range high/low
        comp_high = float(comp_window["high"].max())
        comp_low = float(comp_window["low"].min())
        if comp_high <= comp_low:
            return None

        close = float(row["close"])
        prev_close = float(prev["close"])
        tp_r = float(self.config.get("tp_r_multiple", 1.5))
        sl_buffer = float(self.config.get("sl_atr_buffer", 0.25))

        # Long setup: breakout up on bar i-1, retest on bar i
        if prev_close > comp_high and float(row["low"]) <= comp_high and close > comp_high:
            stop = min(float(row["low"]), comp_high) - sl_buffer * atr_val
            risk = close - stop
            if risk <= 0 or risk < 0.1 * atr_val:
                return None
            return StrategySignal(ts, "long", stop, close + risk * tp_r, {"strategy": self.name, "atr": atr_val})

        # Short setup: breakout down on bar i-1, retest on bar i
        if prev_close < comp_low and float(row["high"]) >= comp_low and close < comp_low:
            stop = max(float(row["high"]), comp_low) + sl_buffer * atr_val
            risk = stop - close
            if risk <= 0 or risk < 0.1 * atr_val:
                return None
            return StrategySignal(ts, "short", stop, close - risk * tp_r, {"strategy": self.name, "atr": atr_val})

        return None
