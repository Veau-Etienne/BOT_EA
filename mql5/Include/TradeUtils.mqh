#ifndef __TRADE_UTILS_MQH__
#define __TRADE_UTILS_MQH__

double NormalizeVolumeForSymbol(const string symbol, double volume)
{
   double minVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      return 0.0;

   volume = MathMax(minVolume, MathMin(maxVolume, volume));
   return MathFloor(volume / step) * step;
}

double CalculateRiskLots(const string symbol, double riskMoney, double entryPrice, double stopLoss)
{
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0 || riskMoney <= 0.0)
      return 0.0;

   double stopDistance = MathAbs(entryPrice - stopLoss);
   double ticks = stopDistance / tickSize;
   double lossPerLot = ticks * tickValue;
   if(lossPerLot <= 0.0)
      return 0.0;

   return NormalizeVolumeForSymbol(symbol, riskMoney / lossPerLot);
}

bool HasOpenPositionForSymbol(const string symbol, long magic)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == magic)
         return true;
   }
   return false;
}

#endif
