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

### V1.7 - US100 H1 Trend Pullback Review

- Backtest strict du candidat.
- Monte Carlo.
- Walk-forward.
- Analyse de concentration mensuelle.
- Sensibilité légère des paramètres.
- Statut : À RETRAVAILLER, non validable, non tradable.

### V1.8 - Régimes US100 H1

- Filter Lab sur `US100_H1 / nas_trend_pullback`.
- 35 filtres simples ou combinaisons limitées testés.
- 0 filtre prometteur.
- Le candidat reste À RETRAVAILLER, non validable, non tradable.

### V1.9 - US100 H1 Exclude Monday Validation

- Stratégie explicite `nas_trend_pullback_exclude_monday`.
- Backtest strict, Monte Carlo, walk-forward, analyse candidat, stress tests et rolling validation.
- Statut : À RETRAVAILLER.
- Pas de validation avancée : walk-forward fragile et concentration meilleur mois encore légèrement trop élevée.

### V2.0 - MT5 Parity US100 H1

- Configuration candidate dédiée.
- Export des signaux Python pour comparaison.
- EA MQL5 vérificateur sans trading réel par défaut.
- Comparateur Python/MT5.
- Inspection des coûts et backtest coûts x1.5.
- Tests anti-lookahead.

### V2.1 - Run MT5 Parity Workflow

- Pytest installé et tests anti-lookahead OK.
- MT5/Wine localisé.
- EA vérificateur copié dans `MQL5/Experts`.
- Compilation automatique non validée car aucun `.ex5` n'a été généré.
- CSV MT5 absent, parité bloquée avec verdict `PARITY_BLOCKED_MT5_CSV_MISSING`.

## En Cours

### V2.1 - Génération Manuelle CSV MT5

- Compiler manuellement `US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5` dans MetaEditor.
- Ouvrir `US100.cash` en H1 dans MT5.
- Attacher l'EA avec `EnableTrading=false`.
- Générer `MQL5/Files/us100_h1_mt5_signals.csv`.
- Relancer `scripts/run_mt5_parity_check.py`.
- Si `PARITY_OK` : prochaine étape = forward test observation only, sans trading live.
- Si `PARITY_WARNING` ou `PARITY_FAIL` : prochaine étape = corriger timezone/EMA/ATR/timestamp/SLTP, sans optimiser la stratégie.

## Prochaines Étapes

### V1.11 - EURUSD

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
