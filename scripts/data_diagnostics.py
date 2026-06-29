#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.diagnostics import diagnose_csv, diagnostics_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Produce a data quality report for an MT5 CSV export.")
    parser.add_argument("--data", required=True, help="CSV file exported from MT5.")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--output", help="Optional markdown output path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = diagnose_csv(args.data, timezone=args.timezone, timeframe=args.timeframe)
    except Exception as exc:
        raise SystemExit(f"Data diagnostics failed: {exc}") from exc

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    markdown = diagnostics_markdown(report)
    print(markdown)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
