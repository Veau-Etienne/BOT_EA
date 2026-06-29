from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators.atr import atr
from src.strategies.base import BaseStrategy, StrategySignal
from src.utils.time import parse_hhmm


@dataclass(frozen=True)
class InitialMove:
    high: float
    low: float
    open: float
    ready_after: pd.Timestamp
    atr: float


class NASPostOpenMeanReversion(BaseStrategy):
    name = "nas_post_open_mean_reversion"

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        out = data.copy()
        out["atr"] = atr(out, int(self.config.get("atr_period", 14)))
        self._moves = self._build_initial_moves(out)
        return out

    def _build_initial_moves(self, data: pd.DataFrame) -> dict[object, InitialMove]:
        moves: dict[object, InitialMove] = {}
        start = parse_hhmm(self.config.get("session_start", "15:30"))
        bars = max(1, int(self.config.get("initial_window_minutes", 45)) // 15)
        for day, day_df in data.groupby(data.index.date):
            window = day_df[day_df.index.time >= start].head(bars)
            if len(window) == bars:
                atr_value = float(window["atr"].iloc[-1]) if pd.notna(window["atr"].iloc[-1]) else 0.0
                moves[day] = InitialMove(
                    high=float(window["high"].max()),
                    low=float(window["low"].min()),
                    open=float(window["open"].iloc[0]),
                    ready_after=window.index[-1],
                    atr=atr_value,
                )
        return moves

    def generate_signal(self, i: int, data: pd.DataFrame) -> StrategySignal | None:
        row = data.iloc[i]
        prev = data.iloc[i - 1] if i > 0 else row
        ts = data.index[i]
        move = getattr(self, "_moves", {}).get(ts.date())
        if move is None or ts <= move.ready_after:
            return None
        if ts.time() > parse_hhmm(self.config.get("trade_until", "18:00")):
            return None
        max_spread = self.config.get("max_spread")
        if max_spread is not None and "spread" in data.columns and pd.notna(row.get("spread")) and float(row["spread"]) > float(max_spread):
            return None

        atr_value = float(row["atr"]) if pd.notna(row["atr"]) else move.atr
        if atr_value <= 0 or atr_value < float(self.config.get("atr_min_filter", 0)):
            return None

        initial_range = move.high - move.low
        initial_extension = max(abs(move.high - move.open), abs(move.open - move.low))
        if initial_extension < float(self.config.get("min_initial_move_atr", 1.0)) * atr_value:
            return None
        if initial_range < float(self.config.get("min_range_atr_ratio", 0.5)) * atr_value:
            return None

        close = float(row["close"])
        open_ = float(row["open"])
        tp_r = float(self.config.get("tp_r_multiple", 1.0))
        target_mode = self.config.get("tp_mode", "range_mid")
        mid = (move.high + move.low) / 2

        if move.high - move.open >= abs(move.open - move.low):
            rejection = close < float(prev["high"]) and close < open_
            if rejection and close < move.high:
                stop = max(move.high, float(row["high"])) + 0.10 * atr_value
                risk = stop - close
                if risk <= 0:
                    return None
                target = mid if target_mode == "range_mid" and mid < close else close - risk * tp_r
                return StrategySignal(ts, "short", stop, target, {"strategy": self.name, "atr": atr_value, "initial_range": initial_range})

        if abs(move.open - move.low) > move.high - move.open:
            rejection = close > float(prev["low"]) and close > open_
            if rejection and close > move.low:
                stop = min(move.low, float(row["low"])) - 0.10 * atr_value
                risk = close - stop
                if risk <= 0:
                    return None
                target = mid if target_mode == "range_mid" and mid > close else close + risk * tp_r
                return StrategySignal(ts, "long", stop, target, {"strategy": self.name, "atr": atr_value, "initial_range": initial_range})

        return None
