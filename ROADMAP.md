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
- Compilation automatique OK via le Wine embarqué dans l'app MetaTrader 5.
- Strategy Tester MT5 exécuté sur `US100.cash` H1, sans trading réel.
- CSV MT5 généré dans le dossier agent Strategy Tester.
- Parité Python/MT5 exécutée : `PARITY_FAIL`, 311 signaux Python contre 367 signaux MT5, 57 extras MT5, 1 manquant MT5, 0 mismatch direction.

### V2.2 - Correction Parité Python/MT5

- DataDump EA ajouté pour exporter bougies H1 et indicateurs MT5.
- Bar parity exécutée : `BAR_PARITY_FAIL` entre `data/resampled/US100_H1.csv` et les bougies H1 MT5.
- Cause principale des 57 extras MT5 identifiée : l'EA vérificateur utilisait l'EMA fast courante pour tester le pullback de la bougie précédente.
- Correction appliquée : pullback MQL5 sur `prev.low/high` vs EMA fast précédente, comme Python.
- Signal parity après correction avec bougies MT5 importées : `PARITY_OK`, 311 signaux communs, 0 extra, 0 manquant.
- Signal parity après correction avec bougies Python resamplées : reste `PARITY_FAIL` résiduel par source de données, 1 extra MT5 et 1 manquant MT5.

### V2.3 - Décision Source H1 Officielle

- Source officielle décidée pour ce candidat : `data/resampled/US100_H1_FROM_MT5.csv`.
- Entry mode réaliste ajouté : `next_bar_open`.
- Backtest `bar_close` vs `next_bar_open` exécuté sur MT5 H1.
- Stress coûts x1.5 exécuté en `next_bar_open`.
- TradeReplay EA ajouté et compilé, simulation uniquement.
- Trade parity coûts x1.5 : `TRADE_PARITY_OK` avec tolérance d'exécution 35 points / 2 USD PnL.
- Statut : candidat fragile, non validé, non tradable.

### V2.4 — XAUUSD M15/M30 Strategy Exploration

- 4 nouvelles familles de stratégies XAU créées : liquidity sweep, HTF trend pullback, compression retest, session momentum.
- Matrice d'exploration multi-stratégies lancée (entry_mode next_bar_open, coûts x1.0 et x1.5).
- Résultats : 3 stratégies rejetées (PF < 1.05), 1 à retravailler (`xau_m30_session_momentum_continuation`, PF 1.118).
- US100 H1 reste le meilleur candidat (PF 1.335, CANDIDAT SÉRIEUX base costs).
- Aucune stratégie XAU validée, aucune stratégie live.

## En Cours

### V2.5 — XAU M30 Session Momentum Deep Analysis (si priorité)

- Walk-forward `xau_m30_session_momentum_continuation`.
- Analyse concentration mensuelle et stress tests.
- Corrélation avec US100 H1 pour évaluer la diversification potentielle.
- Ne pas optimiser les paramètres sans d'abord valider la robustesse temporelle.
- Décision : promouvoir ou rejeter.

### Observation Forward US100 H1

- Si le candidat reste prioritaire : observation forward/demo sans ordre réel.
- Source MT5 H1 officielle uniquement.
- Aucun live tant qu'aucune stratégie n'est validée.

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
