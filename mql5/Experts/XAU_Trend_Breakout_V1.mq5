#property strict
#property version "1.00"
#property description "XAUUSD M15 trend breakout prototype with hard SL/TP and internal risk checks."

#include <Trade/Trade.mqh>
#include <RiskManager.mqh>
#include <TradeUtils.mqh>

input long InpMagic = 2026062901;
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input double InpInitialBalance = 100000.0;
input double InpRiskPerTradePct = 0.25;
input double InpMaxDailyLossPct = 1.0;
input double InpMaxTotalLossPct = 5.0;
input int InpMaxTradesPerDay = 3;
input int InpMaxSpreadPoints = 50;
input int InpEMAPeriod = 200;
input int InpDonchianPeriod = 20;
input int InpATRPeriod = 14;
input double InpSLATR = 1.5;
input double InpTPATR = 2.5;
input int InpDeviationPoints = 20;
input string InpBlockVariableName = "FTMO_RISK_BLOCK";

CTrade Trade;
CFTMORiskManager Risk;
int EmaHandle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
datetime LastBarTime = 0;

bool InSession()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   int minutes = t.hour * 60 + t.min;
   bool morning = minutes >= 8 * 60 && minutes <= 11 * 60 + 30;
   bool afternoon = minutes >= 14 * 60 + 30 && minutes <= 18 * 60;
   return morning || afternoon;
}

bool IsNewBar()
{
   datetime times[1];
   if(CopyTime(_Symbol, InpTimeframe, 0, 1, times) != 1)
      return false;
   if(times[0] == LastBarTime)
      return false;
   LastBarTime = times[0];
   return true;
}

bool GetIndicatorValue(int handle, double &value)
{
   double buffer[1];
   if(CopyBuffer(handle, 0, 1, 1, buffer) != 1)
      return false;
   value = buffer[0];
   return value != EMPTY_VALUE;
}

bool GetDonchian(double &highest, double &lowest)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, InpTimeframe, 2, InpDonchianPeriod, rates);
   if(copied < InpDonchianPeriod)
      return false;

   highest = rates[0].high;
   lowest = rates[0].low;
   for(int i = 1; i < copied; i++)
   {
      highest = MathMax(highest, rates[i].high);
      lowest = MathMin(lowest, rates[i].low);
   }
   return true;
}

int OnInit()
{
   Trade.SetExpertMagicNumber(InpMagic);
   Trade.SetDeviationInPoints(InpDeviationPoints);
   Risk.Setup(InpInitialBalance, InpBlockVariableName);

   EmaHandle = iMA(_Symbol, InpTimeframe, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
   AtrHandle = iATR(_Symbol, InpTimeframe, InpATRPeriod);
   if(EmaHandle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE)
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(EmaHandle != INVALID_HANDLE)
      IndicatorRelease(EmaHandle);
   if(AtrHandle != INVALID_HANDLE)
      IndicatorRelease(AtrHandle);
}

void OnTick()
{
   if(!IsNewBar())
      return;
   if(!InSession())
      return;
   if(Risk.TerminalBlockActive())
      return;

   string reason = "";
   if(!Risk.Allowed(_Symbol, InpMaxDailyLossPct, InpMaxTotalLossPct, InpMaxTradesPerDay, InpMaxSpreadPoints, reason))
      return;
   if(HasOpenPositionForSymbol(_Symbol, InpMagic))
      return;

   MqlRates signalBar[1];
   ArraySetAsSeries(signalBar, true);
   if(CopyRates(_Symbol, InpTimeframe, 1, 1, signalBar) != 1)
      return;

   double ema = 0.0;
   double atr = 0.0;
   double donchianHigh = 0.0;
   double donchianLow = 0.0;
   if(!GetIndicatorValue(EmaHandle, ema) || !GetIndicatorValue(AtrHandle, atr) || !GetDonchian(donchianHigh, donchianLow))
      return;
   if(atr <= 0.0)
      return;

   double close = signalBar[0].close;
   double high = signalBar[0].high;
   double low = signalBar[0].low;
   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPerTradePct / 100.0;

   if(close > ema && high > donchianHigh)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double sl = entry - InpSLATR * atr;
      double tp = entry + InpTPATR * atr;
      double lots = CalculateRiskLots(_Symbol, riskMoney, entry, sl);
      if(lots > 0.0 && sl > 0.0)
         Trade.Buy(lots, _Symbol, entry, sl, tp, "XAU Trend Breakout V1");
   }
   else if(close < ema && low < donchianLow)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double sl = entry + InpSLATR * atr;
      double tp = entry - InpTPATR * atr;
      double lots = CalculateRiskLots(_Symbol, riskMoney, entry, sl);
      if(lots > 0.0 && sl > 0.0)
         Trade.Sell(lots, _Symbol, entry, sl, tp, "XAU Trend Breakout V1");
   }
}
