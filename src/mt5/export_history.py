from __future__ import annotations


def mt5_csv_export_steps(symbol: str, timeframe: str = "M15") -> list[str]:
    return [
        "Open MetaTrader 5 under Wine.",
        "Open View > Symbols or press Ctrl+U.",
        f"Select the broker symbol matching {symbol}. Names may be XAUUSD, US100.cash, NAS100.cash, or similar.",
        f"Open the Bars tab and choose {timeframe}.",
        "Click Request/Download if MT5 has not loaded enough history.",
        "Click Export and save the CSV into data/raw/.",
        "Run the Python backtest against that CSV.",
    ]
