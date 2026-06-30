#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Python backtester-compatible H1 CSV from MT5 Strategy Tester bar dump.")
    parser.add_argument("--mt5-bars", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.mt5_bars)
    if not source.exists():
        raise FileNotFoundError(f"CSV MT5 introuvable: {source}")

    data = pd.read_csv(source)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Colonnes manquantes dans le dump MT5: {missing}")

    out = pd.DataFrame()
    out["time"] = pd.to_datetime(data["timestamp"], errors="raise").dt.strftime("%Y-%m-%d %H:%M:%S")
    for column in ["open", "high", "low", "close"]:
        out[column] = pd.to_numeric(data[column], errors="raise")
    if "tick_volume" in data.columns:
        out["tick_volume"] = pd.to_numeric(data["tick_volume"], errors="coerce")
        out["volume"] = out["tick_volume"]
    if "spread" in data.columns:
        out["spread"] = pd.to_numeric(data["spread"], errors="coerce")

    out = out.drop_duplicates("time", keep="last").sort_values("time")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)

    print(f"Rows imported: {len(out)}")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
