#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.locate_mt5_wine import locate_mt5_paths


MANUAL_STEPS = """Manual MT5 parity steps:
1. Open MetaEditor.
2. Open US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5.
3. Compile.
4. Fix any compilation error.
5. In MT5, open US100.cash in H1.
6. Attach the EA to the chart.
7. Verify EnableTrading=false.
8. Let it generate us100_h1_mt5_signals.csv in MQL5/Files.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy the US100 H1 verifier EA into the MT5 MQL5/Experts folder.")
    parser.add_argument("--ea", required=True, help="Path to the verifier EA .mq5 file.")
    return parser.parse_args()


def _wine_binary() -> str | None:
    for candidate in ["wine64", "wine"]:
        found = shutil.which(candidate)
        if found:
            return found
    mac_candidates = [
        Path("/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine64"),
        Path("/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine"),
        Path("/Applications/Wine Devel.app/Contents/Resources/wine/bin/wine64"),
        Path("/Applications/Wine Devel.app/Contents/Resources/wine/bin/wine"),
    ]
    for path in mac_candidates:
        if path.exists():
            return str(path)
    return None


def _try_compile(metaeditor: Path, ea_dest: Path) -> tuple[str, str]:
    wine = _wine_binary()
    if not wine:
        return "AUTO_COMPILE_NOT_AVAILABLE", "Wine executable not found in PATH or common macOS Wine app paths."

    log_path = ea_dest.with_suffix(".compile.log")
    ex5_path = ea_dest.with_suffix(".ex5")
    winepath = shutil.which("winepath")
    compile_target = str(ea_dest)
    compile_log = str(log_path)
    if winepath:
        try:
            compile_target = subprocess.check_output([winepath, "-w", str(ea_dest)], text=True, timeout=10).strip()
            compile_log = subprocess.check_output([winepath, "-w", str(log_path)], text=True, timeout=10).strip()
        except Exception:
            compile_target = str(ea_dest)
            compile_log = str(log_path)
    command = [wine, str(metaeditor), f"/compile:{compile_target}", f"/log:{compile_log}"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return "AUTO_COMPILE_KO", f"Compilation command failed to run: {exc}"

    detail = "\n".join(
        item
        for item in [
            f"command: {' '.join(command)}",
            f"returncode: {completed.returncode}",
            completed.stdout.strip(),
            completed.stderr.strip(),
            f"log: {log_path}",
            f"ex5: {ex5_path}",
        ]
        if item
    )
    if completed.returncode == 0 and ex5_path.exists():
        return "AUTO_COMPILE_OK", detail
    if completed.returncode == 0 and not ex5_path.exists():
        return "AUTO_COMPILE_KO", detail + "\nMetaEditor returned 0 but the expected .ex5 file was not created."
    return "AUTO_COMPILE_KO", detail


def main() -> None:
    args = parse_args()
    ea_source = (ROOT / args.ea).resolve() if not Path(args.ea).is_absolute() else Path(args.ea)
    if not ea_source.exists():
        raise FileNotFoundError(f"EA source not found: {ea_source}")

    paths = locate_mt5_paths()
    print(f"MT5 locate verdict: {paths.verdict}")
    print(f"terminal path: {paths.terminal if paths.terminal else 'NOT_FOUND'}")
    print(f"metaeditor path: {paths.metaeditor if paths.metaeditor else 'NOT_FOUND'}")
    print(f"MQL5/Experts path: {paths.experts if paths.experts else 'NOT_FOUND'}")
    print(f"MQL5/Files path: {paths.files if paths.files else 'NOT_FOUND'}")

    if paths.experts is None:
        print("EA copy status: EA_COPY_KO")
        print("MQL5/Experts path not found. No AutoTrading action was attempted.")
        print(MANUAL_STEPS)
        return

    destination = paths.experts / ea_source.name
    shutil.copy2(ea_source, destination)
    exists = destination.exists()
    print(f"EA destination: {destination}")
    print(f"EA copy status: {'EA_COPY_OK' if exists else 'EA_COPY_KO'}")
    print("AutoTrading status: NOT_TOUCHED")
    print("Trading status: NO_ORDER_SENT")

    if not exists:
        print(MANUAL_STEPS)
        return

    if paths.metaeditor is None:
        print("EA compile status: AUTO_COMPILE_NOT_AVAILABLE")
        print("metaeditor64.exe not found.")
        print(MANUAL_STEPS)
        return

    status, detail = _try_compile(paths.metaeditor, destination)
    print(f"EA compile status: {status}")
    print(detail)
    if status != "AUTO_COMPILE_OK":
        print(MANUAL_STEPS)


if __name__ == "__main__":
    main()
