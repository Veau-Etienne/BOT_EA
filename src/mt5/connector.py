from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class MT5ConnectionCheck:
    wine_available: bool
    env_terminal_path: str | None
    detected_paths: list[str]
    usable_terminal_path: str | None
    notes: list[str]


def _candidate_paths() -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".wine/drive_c/Program Files/MetaTrader 5/terminal64.exe",
        home / ".wine/drive_c/Program Files/MetaTrader 5/terminal.exe",
        home / ".wine/drive_c/Program Files (x86)/MetaTrader 5/terminal64.exe",
        home / ".wine/drive_c/Program Files (x86)/MetaTrader 5/terminal.exe",
    ]
    candidates.extend(home.glob(".wine*/drive_c/Program Files*/**/terminal64.exe"))
    candidates.extend(home.glob(".wine*/drive_c/Program Files*/**/terminal.exe"))
    return list(dict.fromkeys(candidates))


def check_mt5_connection(env_file: str | Path = ".env") -> MT5ConnectionCheck:
    load_dotenv(env_file)
    wine_available = shutil.which("wine") is not None
    env_path = os.getenv("MT5_TERMINAL_PATH") or None
    detected: list[Path] = []
    if env_path:
        detected.append(Path(env_path).expanduser())
    detected.extend(_candidate_paths())

    existing = [path for path in detected if path.exists()]
    usable = str(existing[0]) if existing else None
    notes = []
    if not wine_available:
        notes.append("Wine is not available in PATH. Install Wine or launch MT5 manually.")
    if env_path and not Path(env_path).expanduser().exists():
        notes.append("MT5_TERMINAL_PATH is set but the file was not found.")
    if not usable:
        notes.append("No MT5 terminal executable detected. Set MT5_TERMINAL_PATH in .env.")
    else:
        notes.append("MT5 terminal executable found. Direct Python control through Wine may still be fragile; CSV export is the robust path.")

    return MT5ConnectionCheck(
        wine_available=wine_available,
        env_terminal_path=env_path,
        detected_paths=[str(path) for path in existing],
        usable_terminal_path=usable,
        notes=notes,
    )
