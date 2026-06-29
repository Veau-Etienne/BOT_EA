# Roadmap

## Réalisé

### V1

- Moteur Python de backtest.
- Parser CSV MT5.
- Stratégies initiales.
- EAs MQL5.
- Risk Guard.

### V1.1

- Diagnostics de données.
- Rapports enrichis.
- Monte Carlo.
- Walk-forward.
- Garde-fous anti-overfitting.

### V1.2

- Analyse des trades.
- Stratégie inverse théorique.
- `xau_failed_breakout_reversal`.
- `xau_pullback_trend`.

### V1.3

- Exit Lab.
- Diagnostic full sample.
- Analyse des trades ayant atteint +1R puis fini perdants.

### V1.5

- Strategy Scanner.
- Nouvelles stratégies NAS100.
- Scan global XAUUSD/US100.
- Conclusion : toutes les hypothèses M15 testées sont rejetées.

## En Cours

### V1.6 - Sanity Check + Timeframe Scanner

- Vérifier les coûts, point sizes, spreads, sessions et timezones.
- Ajouter un sanity check data/config.
- Ajouter le resampling M30/H1.
- Scanner M15/M30/H1 en diagnostic full sample non tradable.
- Identifier si le problème vient des hypothèses ou d'une configuration de backtest.

## Prochaines Étapes

### V1.7 - EURUSD

- Importer et diagnostiquer EURUSD M15.
- Tester `eur_london_breakout`.
- Tester `eur_london_mean_reversion`.
- Rejeter ou classer les hypothèses selon les mêmes règles.

### V2 - Régimes De Marché

- Détection de tendance/range/volatilité.
- Filtres horaires et saisonnalité.
- Tests par régime plutôt que par stratégie unique.

### V3 - EA Après Validation

- Aucun EA live avant stratégie validée.
- Transposition MQL5 uniquement après backtest robuste, Monte Carlo, walk-forward et test demo.
- Risk Guard obligatoire.
