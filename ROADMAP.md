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

### V1.6

- Sanity check data/config.
- Resampling M30/H1.
- Scanner full sample non tradable sur M15/M30/H1.
- Identification d'un seul candidat : `US100_H1 / nas_trend_pullback`.

## En Cours

### V1.7 - US100 H1 Trend Pullback Review

- Backtest strict du candidat.
- Monte Carlo.
- Walk-forward.
- Analyse de concentration mensuelle.
- Sensibilité légère des paramètres.
- Statut : À RETRAVAILLER, non validable, non tradable.

## Prochaines Étapes

### V1.8 - Régimes US100 H1

- Comprendre les régimes qui portent `nas_trend_pullback`.
- Tester des filtres de jour, heure, ATR et spread sans optimisation massive.
- Valider uniquement si le profit cesse d'être concentré sur quelques mois.

### V1.9 - EURUSD

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
