#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPECTED_ROOTS = [
    Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5",
    Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5",
    Path.home() / ".wine",
]


@dataclass(frozen=True)
class MT5Paths:
    terminal: Path | None
    metaeditor: Path | None
    experts: Path | None
    files: Path | None
    searched_roots: list[Path]

    @property
    def verdict(self) -> str:
        if self.terminal and self.experts and self.files:
            return "MT5_PATHS_OK"
        if self.terminal or self.metaeditor or self.experts or self.files:
            return "MT5_PATHS_PARTIAL"
        return "MT5_PATHS_NOT_FOUND"


def _walk_limited(root: Path) -> list[Path]:
    if not root.exists():
        return []
    matches: list[Path] = []
    try:
        for path in root.rglob("*"):
            name = path.name.lower()
            if name in {"terminal64.exe", "metaeditor64.exe"}:
                matches.append(path)
            elif path.is_dir() and path.name == "Experts" and path.parent.name == "MQL5":
                matches.append(path)
            elif path.is_dir() and path.name == "Files" and path.parent.name == "MQL5":
                matches.append(path)
    except (OSError, PermissionError):
        return matches
    return matches


def locate_mt5_paths(extra_roots: list[Path] | None = None) -> MT5Paths:
    roots = []
    for root in [*EXPECTED_ROOTS, *(extra_roots or [])]:
        if root not in roots:
            roots.append(root)

    terminal: Path | None = None
    metaeditor: Path | None = None
    experts: Path | None = None
    files: Path | None = None

    for root in roots:
        for path in _walk_limited(root):
            name = path.name.lower()
            if name == "terminal64.exe" and terminal is None:
                terminal = path
            elif name == "metaeditor64.exe" and metaeditor is None:
                metaeditor = path
            elif path.is_dir() and path.name == "Experts" and experts is None:
                experts = path
            elif path.is_dir() and path.name == "Files" and files is None:
                files = path

    return MT5Paths(terminal=terminal, metaeditor=metaeditor, experts=experts, files=files, searched_roots=roots)


def _format(path: Path | None) -> str:
    return str(path) if path else "NOT_FOUND"


def main() -> None:
    paths = locate_mt5_paths()
    print(f"terminal path: {_format(paths.terminal)}")
    print(f"metaeditor path: {_format(paths.metaeditor)}")
    print(f"MQL5/Experts path: {_format(paths.experts)}")
    print(f"MQL5/Files path: {_format(paths.files)}")
    print("searched roots:")
    for root in paths.searched_roots:
        print(f"  - {root}")
    print(f"verdict: {paths.verdict}")


if __name__ == "__main__":
    main()
