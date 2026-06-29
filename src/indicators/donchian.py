from __future__ import annotations

import pandas as pd


def donchian_high(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["high"].rolling(period, min_periods=period).max()


def donchian_low(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["low"].rolling(period, min_periods=period).min()


def donchian_channel(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "donchian_high": donchian_high(df, period),
            "donchian_low": donchian_low(df, period),
        },
        index=df.index,
    )
