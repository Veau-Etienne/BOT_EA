#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.mt5.connector import check_mt5_connection


def main() -> None:
    result = check_mt5_connection(ROOT / ".env")
    print(f"Wine available: {result.wine_available}")
    print(f"MT5_TERMINAL_PATH: {result.env_terminal_path or '(not set)'}")
    print(f"Usable terminal: {result.usable_terminal_path or '(not found)'}")
    print("Detected paths:")
    for path in result.detected_paths:
        print(f"  - {path}")
    print("Notes:")
    for note in result.notes:
        print(f"  - {note}")


if __name__ == "__main__":
    main()
