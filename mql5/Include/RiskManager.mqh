#ifndef __FTMO_RISK_MANAGER_MQH__
#define __FTMO_RISK_MANAGER_MQH__

class CFTMORiskManager
{
private:
   double m_initialBalance;
   double m_dayStartEquity;
   int m_dayOfYear;
   string m_blockVariableName;

   datetime DayStart(datetime now)
   {
      MqlDateTime t;
      TimeToStruct(now, t);
      t.hour = 0;
      t.min = 0;
      t.sec = 0;
      return StructToTime(t);
   }

   int DayOfYear(datetime now)
   {
      MqlDateTime t;
      TimeToStruct(now, t);
      return t.day_of_year;
   }

public:
   void Setup(double initialBalance, string blockVariableName = "FTMO_RISK_BLOCK")
   {
      m_initialBalance = initialBalance;
      m_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      m_dayOfYear = DayOfYear(TimeCurrent());
      m_blockVariableName = blockVariableName;
   }

   void ResetDayIfNeeded()
   {
      int current = DayOfYear(TimeCurrent());
      if(current != m_dayOfYear)
      {
         m_dayOfYear = current;
         m_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      }
   }

   double DailyDrawdownPct()
   {
      ResetDayIfNeeded();
      if(m_dayStartEquity <= 0.0)
         return 0.0;
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      return MathMax(0.0, (m_dayStartEquity - equity) / m_dayStartEquity * 100.0);
   }

   double TotalDrawdownPct()
   {
      if(m_initialBalance <= 0.0)
         return 0.0;
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      return MathMax(0.0, (m_initialBalance - equity) / m_initialBalance * 100.0);
   }

   int TradesToday()
   {
      datetime start = DayStart(TimeCurrent());
      if(!HistorySelect(start, TimeCurrent()))
         return 0;

      int count = 0;
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0)
            continue;
         if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN)
            count++;
      }
      return count;
   }

   bool SpreadAllowed(const string symbol, int maxSpreadPoints)
   {
      long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
      return spread <= maxSpreadPoints;
   }

   bool Allowed(const string symbol, double maxDailyLossPct, double maxTotalLossPct, int maxTradesPerDay, int maxSpreadPoints, string &reason)
   {
      ResetDayIfNeeded();
      if(DailyDrawdownPct() >= maxDailyLossPct)
      {
         reason = "daily loss limit";
         return false;
      }
      if(TotalDrawdownPct() >= maxTotalLossPct)
      {
         reason = "total drawdown limit";
         return false;
      }
      if(TradesToday() >= maxTradesPerDay)
      {
         reason = "max trades today";
         return false;
      }
      if(!SpreadAllowed(symbol, maxSpreadPoints))
      {
         reason = "spread too high";
         return false;
      }
      reason = "allowed";
      return true;
   }

   void PublishBlock(bool blocked)
   {
      GlobalVariableSet(m_blockVariableName, blocked ? 1.0 : 0.0);
   }

   bool TerminalBlockActive()
   {
      if(!GlobalVariableCheck(m_blockVariableName))
         return false;
      return GlobalVariableGet(m_blockVariableName) >= 1.0;
   }
};

#endif
