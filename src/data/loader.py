from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.cleaner import CleaningReport, clean_ohlcv
from src.data.mt5_export_parser import read_mt5_csv


def load_mt5_ohlcv(
    path: str | Path,
    timezone: str = "Europe/Paris",
    timeframe: str = "M15",
) -> tuple[pd.DataFrame, CleaningReport]:
    raw = read_mt5_csv(path)
    return clean_ohlcv(raw, timezone=timezone, timeframe=timeframe)


class HistoricalDataLoader:
    def load(self, path: str | Path, timezone: str = "Europe/Paris", timeframe: str = "M15") -> tuple[pd.DataFrame, CleaningReport]:
        return load_mt5_ohlcv(path, timezone=timezone, timeframe=timeframe)
