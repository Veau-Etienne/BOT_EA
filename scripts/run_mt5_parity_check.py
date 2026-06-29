#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.locate_mt5_wine import locate_mt5_paths


MT5_SIGNAL_FILE = "us100_h1_mt5_signals.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find MT5 verifier CSV and run Python/MT5 signal parity comparison.")
    parser.add_argument("--python-signals", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _manual_steps(expected: Path | None) -> str:
    expected_line = str(expected) if expected else "MQL5/Files/us100_h1_mt5_signals.csv"
    return "\n".join(
        [
            "CSV MT5 introuvable.",
            f"Chemin attendu: {expected_line}",
            "Étapes manuelles:",
            "1. Ouvrir MetaEditor.",
            "2. Compiler US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5.",
            "3. Dans MT5, ouvrir US100.cash en H1.",
            "4. Attacher l'EA au graphique.",
            "5. Vérifier EnableTrading=false.",
            "6. Vérifier qu'AutoTrading n'est pas nécessaire pour l'export.",
            "7. Laisser générer us100_h1_mt5_signals.csv dans MQL5/Files.",
            "8. Relancer ce script.",
        ]
    )


def _write_blocked_report(output: Path, expected: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Python / MT5 Signal Parity\n\n"
        "- Verdict : PARITY_BLOCKED_MT5_CSV_MISSING\n"
        f"- CSV attendu : {expected if expected else 'MQL5/Files/us100_h1_mt5_signals.csv'}\n\n"
        "La comparaison n'a pas été lancée car le CSV MT5 est absent.\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    paths = locate_mt5_paths()
    expected = paths.files / MT5_SIGNAL_FILE if paths.files else None
    candidates = []
    if expected:
        candidates.append(expected)
    for root in paths.searched_roots:
        if root.exists():
            try:
                candidates.extend(root.rglob(MT5_SIGNAL_FILE))
            except (OSError, PermissionError):
                continue

    mt5_csv = next((path for path in candidates if path.exists()), None)
    output = Path(args.output)
    if mt5_csv is None:
        message = _manual_steps(expected)
        _write_blocked_report(output, expected)
        print(message)
        print(f"Report: {output}")
        raise SystemExit(1)

    command = [
        sys.executable,
        str(ROOT / "scripts/compare_mt5_python_signals.py"),
        "--python-signals",
        args.python_signals,
        "--mt5-signals",
        str(mt5_csv),
        "--output",
        str(output),
    ]
    print(f"MT5 CSV found: {mt5_csv}")
    completed = subprocess.run(command, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
