from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


COLUMN_ALIASES = {
    "time": "time",
    "timestamp": "time",
    "datetime": "time",
    "date_time": "time",
    "timegmt": "time",
    "gmt": "time",
    "date": "date",
    "day": "date",
    "open": "open",
    "o": "open",
    "high": "high",
    "h": "high",
    "low": "low",
    "l": "low",
    "close": "close",
    "c": "close",
    "tickvol": "tick_volume",
    "tick_volume": "tick_volume",
    "tick volume": "tick_volume",
    "tickvolume": "tick_volume",
    "tick_volume_": "tick_volume",
    "vol": "volume",
    "volume": "volume",
    "realvol": "volume",
    "real_volume": "volume",
    "real_volume": "volume",
    "spread": "spread",
    "spread_points": "spread",
    "spread_pts": "spread",
    "spread_in_points": "spread",
}


def _clean_column_name(name: object) -> str:
    clean = str(name).strip().lower().replace("\ufeff", "")
    clean = clean.replace("<", "").replace(">", "")
    clean = re.sub(r"[^a-z0-9]+", "_", clean)
    return clean.strip("_")


def read_mt5_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        for sep in ("\t", ";", ","):
            try:
                df = pd.read_csv(path, sep=sep, encoding=encoding)
                if len(df.columns) > 1:
                    return normalize_columns(df)
                errors.append(f"encoding={encoding}, sep={sep!r}: only one column detected")
            except Exception as exc:  # pragma: no cover - kept for diagnostics
                errors.append(f"encoding={encoding}, sep={sep!r}: {exc}")

        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=encoding)
            if len(df.columns) > 1:
                return normalize_columns(df)
            errors.append(f"encoding={encoding}, sep=auto: only one column detected")
        except Exception as exc:
            errors.append(f"encoding={encoding}, sep=auto: {exc}")

    details = "\n  - ".join(errors[-8:])
    raise ValueError(f"Could not read CSV {path}. Tried common MT5 separators/encodings. Last errors:\n  - {details}")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for col in df.columns:
        clean = _clean_column_name(col)
        renamed[col] = COLUMN_ALIASES.get(clean, clean)
    out = df.rename(columns=renamed).copy()
    if out.columns.duplicated().any():
        merged = pd.DataFrame(index=out.index)
        for column in dict.fromkeys(out.columns):
            same_name = out.loc[:, out.columns == column]
            if same_name.shape[1] == 1:
                merged[column] = same_name.iloc[:, 0]
            else:
                merged[column] = same_name.bfill(axis=1).iloc[:, 0]
        out = merged

    if "date" in out.columns and "time" in out.columns:
        time_values = out["time"].astype(str).str.strip()
        if time_values.str.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?").fillna(False).all():
            out["time"] = out["date"].astype(str).str.strip() + " " + time_values
        out = out.drop(columns=["date"])

    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(out.columns)
    if missing:
        original_columns = [str(col) for col in df.columns]
        normalized_columns = list(out.columns)
        raise ValueError(
            f"Missing required OHLC columns after normalization: {sorted(missing)}. "
            f"Original columns: {original_columns}. Normalized columns: {normalized_columns}."
        )

    if "tick_volume" not in out.columns and "volume" in out.columns:
        out["tick_volume"] = out["volume"]
    if "volume" not in out.columns and "tick_volume" in out.columns:
        out["volume"] = out["tick_volume"]

    return out
