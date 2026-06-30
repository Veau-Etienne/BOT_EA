"""Strategy implementations."""

from src.strategies.base import BaseStrategy
from src.strategies.eur_london_breakout import EURLondonBreakout
from src.strategies.eur_london_mean_reversion import EURLondonMeanReversion
from src.strategies.nas_opening_breakout import NASOpeningBreakout
from src.strategies.nas_opening_range_retest import NASOpeningRangeRetest
from src.strategies.nas_post_open_mean_reversion import NASPostOpenMeanReversion
from src.strategies.nas_trend_pullback import NASTrendPullback
from src.strategies.nas_trend_pullback_exclude_monday import NASTrendPullbackExcludeMonday
from src.strategies.xau_failed_breakout_reversal import XAUFailedBreakoutReversal
from src.strategies.xau_liquidity_sweep_reversal import XAULiquiditySweepReversal
from src.strategies.xau_m30_htf_trend_pullback import XAUm30HTFTrendPullback
from src.strategies.xau_m30_session_momentum_continuation import XAUm30SessionMomentumContinuation
from src.strategies.xau_pullback_trend import XAUPullbackTrend
from src.strategies.xau_trend_breakout import XAUTrendBreakout
from src.strategies.xau_volatility_compression_retest import XAUVolatilityCompressionRetest


STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    XAUTrendBreakout.name: XAUTrendBreakout,
    XAUFailedBreakoutReversal.name: XAUFailedBreakoutReversal,
    XAUPullbackTrend.name: XAUPullbackTrend,
    XAULiquiditySweepReversal.name: XAULiquiditySweepReversal,
    XAUm30HTFTrendPullback.name: XAUm30HTFTrendPullback,
    XAUVolatilityCompressionRetest.name: XAUVolatilityCompressionRetest,
    XAUm30SessionMomentumContinuation.name: XAUm30SessionMomentumContinuation,
    NASOpeningBreakout.name: NASOpeningBreakout,
    NASPostOpenMeanReversion.name: NASPostOpenMeanReversion,
    NASTrendPullback.name: NASTrendPullback,
    NASTrendPullbackExcludeMonday.name: NASTrendPullbackExcludeMonday,
    NASOpeningRangeRetest.name: NASOpeningRangeRetest,
    EURLondonBreakout.name: EURLondonBreakout,
    EURLondonMeanReversion.name: EURLondonMeanReversion,
}
