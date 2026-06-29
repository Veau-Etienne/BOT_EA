from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Portfolio:
    initial_capital: float
    equity: float
    peak_equity: float

    @classmethod
    def create(cls, initial_capital: float) -> "Portfolio":
        return cls(initial_capital=initial_capital, equity=initial_capital, peak_equity=initial_capital)

    def apply_pnl(self, pnl: float) -> None:
        self.equity += pnl
        self.peak_equity = max(self.peak_equity, self.equity)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity * 100
