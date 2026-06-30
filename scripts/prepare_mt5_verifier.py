#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
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
    mac_candidates = [
        Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"),
        Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine"),
        Path("/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine64"),
        Path("/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine"),
        Path("/Applications/Wine Devel.app/Contents/Resources/wine/bin/wine64"),
        Path("/Applications/Wine Devel.app/Contents/Resources/wine/bin/wine"),
    ]
    for path in mac_candidates:
        if path.exists():
            return str(path)
    for candidate in ["wine64", "wine"]:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _read_log_text(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    for encoding in ["utf-16", "utf-8", "latin-1"]:
        try:
            return log_path.read_text(encoding=encoding, errors="replace")
        except UnicodeError:
            continue
    return ""


def _mt5_root_from_path(path: Path) -> Path | None:
    parts = path.parts
    try:
        mql5_index = parts.index("MQL5")
    except ValueError:
        return None
    return Path(*parts[:mql5_index])


def _wineprefix_from_mt5_root(mt5_root: Path | None) -> Path | None:
    if mt5_root is None:
        return None
    parts = mt5_root.parts
    try:
        drive_c_index = parts.index("drive_c")
    except ValueError:
        return None
    return Path(*parts[:drive_c_index])


def _windows_mt5_path(path: Path) -> str | None:
    parts = path.parts
    try:
        mql5_index = parts.index("MQL5")
    except ValueError:
        return None
    relative = "\\".join(parts[mql5_index:])
    return f"C:\\MT5\\{relative}"


def _try_compile(metaeditor: Path, ea_dest: Path) -> tuple[str, str]:
    wine = _wine_binary()
    if not wine:
        return "AUTO_COMPILE_NOT_AVAILABLE", "Wine executable not found in PATH or common macOS Wine app paths."

    stem_tag = "".join(ch for ch in ea_dest.stem.lower() if ch.isalnum() or ch == "_")
    log_path = ea_dest.parent.parent / "Files" / f"compile_{stem_tag}.log"
    ex5_path = ea_dest.with_suffix(".ex5")
    winepath = shutil.which("winepath")
    mt5_root = _mt5_root_from_path(ea_dest)
    wineprefix = _wineprefix_from_mt5_root(mt5_root)
    if wineprefix and mt5_root:
        alias = wineprefix / "drive_c" / "MT5"
        try:
            if alias.exists() or alias.is_symlink():
                alias.unlink()
            alias.symlink_to(mt5_root)
        except OSError:
            pass
    compile_target = _windows_mt5_path(ea_dest) or str(ea_dest)
    compile_log = _windows_mt5_path(log_path) or str(log_path)
    if "\\" not in compile_target and winepath:
        try:
            compile_target = subprocess.check_output([winepath, "-w", str(ea_dest)], text=True, timeout=10).strip()
            compile_log = subprocess.check_output([winepath, "-w", str(log_path)], text=True, timeout=10).strip()
        except Exception:
            compile_target = str(ea_dest)
            compile_log = str(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in [log_path, ex5_path]:
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    command = [wine, str(metaeditor), f"/compile:{compile_target}", f"/log:{compile_log}"]
    try:
        env = None
        if wineprefix:
            env = {**os.environ, "WINEPREFIX": str(wineprefix)}
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60, env=env)
    except Exception as exc:  # noqa: BLE001
        return "AUTO_COMPILE_KO", f"Compilation command failed to run: {exc}"

    log_text = _read_log_text(log_path)
    log_has_no_errors = "0 errors" in log_text.lower()
    log_tail = "\n".join(log_text.splitlines()[-8:])
    detail = "\n".join(
        item
        for item in [
            f"command: {' '.join(command)}",
            f"returncode: {completed.returncode}",
            completed.stdout.strip(),
            completed.stderr.strip(),
            f"log: {log_path}",
            f"ex5: {ex5_path}",
            f"log_tail:\n{log_tail}" if log_tail else "",
        ]
        if item
    )
    if ex5_path.exists() and (completed.returncode == 0 or log_has_no_errors):
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
