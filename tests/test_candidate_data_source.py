from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_us100_candidate_documents_mt5_h1_as_official_source() -> None:
    path = ROOT / "config/candidates/us100_h1_trend_pullback_exclude_monday.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    candidate = data["candidate"]

    assert candidate["official_data_source"] == "MT5 Strategy Tester H1 export"
    assert candidate["official_data_file_local"] == "data/resampled/US100_H1_FROM_MT5.csv"
    assert candidate["rejected_for_candidate_validation"] == "data/resampled/US100_H1.csv"
    assert "BAR_PARITY_FAIL" in candidate["data_source_reason"]
    assert "PARITY_OK" in candidate["signal_parity_status"]

