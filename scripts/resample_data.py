#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.loader import load_mt5_ohlcv
from src.data.resampler import resample_ohlcv, write_ohlcv_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resample a cleaned MT5 OHLCV CSV to higher timeframes.")
    parser.add_argument("--data", required=True, help="Input MT5 CSV, usually M15.")
    parser.add_argument("--timeframes", required=True, help="Comma-separated targets, for example M30,H1.")
    parser.add_argument("--output-dir", default=str(ROOT / "data/resampled"))
    parser.add_argument("--input-timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    return parser.parse_args()


def _symbol_from_path(path: Path) -> str:
    stem = path.stem.upper()
    match = re.fullmatch(r"(.+)_(M\d+|H\d+|D\d+)", stem)
    return match.group(1) if match else stem


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    symbol = _symbol_from_path(data_path)
    data, cleaning = load_mt5_ohlcv(data_path, timezone=args.timezone, timeframe=args.input_timeframe)
    print(f"Loaded {cleaning.rows_out} rows: {cleaning.first_timestamp} -> {cleaning.last_timestamp}")

    for timeframe in [item.strip().upper() for item in args.timeframes.split(",") if item.strip()]:
        resampled = resample_ohlcv(data, timeframe)
        output = output_dir / f"{symbol}_{timeframe}.csv"
        write_ohlcv_csv(resampled, output)
        print(f"{timeframe}: {len(resampled)} rows written to {output}")


if __name__ == "__main__":
    main()
