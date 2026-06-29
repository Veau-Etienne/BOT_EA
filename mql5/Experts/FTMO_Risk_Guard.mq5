#property strict
#property version "1.00"
#property description "Internal FTMO risk guard. Attach to a chart and keep it running."

#include <RiskManager.mqh>

input double InpInitialBalance = 100000.0;
input double InpMaxDailyLossPct = 1.0;
input double InpMaxTotalLossPct = 5.0;
input int InpMaxTradesPerDay = 3;
input int InpMaxSpreadPoints = 50;
input string InpBlockVariableName = "FTMO_RISK_BLOCK";

CFTMORiskManager Risk;

int OnInit()
{
   Risk.Setup(InpInitialBalance, InpBlockVariableName);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
}

void OnTick()
{
   string reason = "";
   bool allowed = Risk.Allowed(_Symbol, InpMaxDailyLossPct, InpMaxTotalLossPct, InpMaxTradesPerDay, InpMaxSpreadPoints, reason);
   Risk.PublishBlock(!allowed);

   string state = allowed ? "AUTORISE" : "BLOQUE";
   Comment(
      "FTMO Risk Guard\n",
      "State: ", state, "\n",
      "Reason: ", reason, "\n",
      "Equity: ", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2), "\n",
      "Balance: ", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2), "\n",
      "Daily DD: ", DoubleToString(Risk.DailyDrawdownPct(), 2), "%\n",
      "Total DD: ", DoubleToString(Risk.TotalDrawdownPct(), 2), "%\n",
      "Trades today: ", IntegerToString(Risk.TradesToday()), "\n",
      "Spread points: ", IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD))
   );
}
