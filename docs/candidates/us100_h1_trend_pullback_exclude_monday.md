# US100 H1 Trend Pullback Exclude Monday

## Statut

- Actif : US100 / NAS100, symbole broker attendu `US100.cash`.
- Timeframe : H1.
- Stratégie Python : `nas_trend_pullback_exclude_monday`.
- Statut : candidat de recherche.
- Verdict courant : À RETRAVAILLER.
- Trading live : interdit.

## Source De Données Officielle

- Source officielle V2.3 : export H1 MT5 Strategy Tester.
- Fichier local de travail : `data/resampled/US100_H1_FROM_MT5.csv`.
- Source rejetée pour la validation de ce candidat : `data/resampled/US100_H1.csv`.

Le H1 resamplé depuis M15 est rejeté pour la validation stricte de ce candidat parce que la V2.2 a confirmé `BAR_PARITY_FAIL` entre ce fichier et les bougies H1 réellement utilisées par MT5 Strategy Tester. Les signaux Python/MT5 passent en `PARITY_OK` uniquement quand Python utilise les bougies H1 exportées depuis MT5.

Cette décision ne valide pas la stratégie. Elle fixe seulement la source de vérité pour les tests US100 H1 suivants. Le candidat reste recherche uniquement, non tradable, sans live.

## Convention D'Entrée V2.3

- Signal : calculé sur une bougie H1 clôturée.
- Timestamp signal : timestamp de la bougie de signal.
- Mode historique : `bar_close`, entrée théorique au close de la bougie signal.
- Mode réaliste de validation : `next_bar_open`, entrée à l'open de la bougie suivante avec spread/slippage.
- Le trade doit conserver séparément `signal_timestamp` et `entry_time`.

## Métriques V1.9

| Mesure | Valeur |
| --- | ---: |
| Trades | 200 |
| Profit net | 3 310.95 |
| Profit factor | 1.343 |
| Winrate | 52.00% |
| Expectancy | 16.55 |
| Max drawdown | 0.89% |
| Max losing streak | 8 |
| Meilleur mois | 1 192.54 |
| Pire mois | -473.51 |
| Concentration meilleur mois | 36.02% |
| Concentration top 3 mois | 73.88% |
| Monte Carlo DD médian | 1.30% |
| Monte Carlo DD 95% | 2.06% |
| Monte Carlo pire DD | 3.15% |

## Walk-Forward V1.9

| Fold | PF test | Verdict |
| ---: | ---: | --- |
| 1 | 1.645 | OK |
| 2 | 1.050 | fragile |
| 3 | 1.062 | fragile |

Le candidat ne passe pas le walk-forward majoritairement OK. Les folds 2 et 3 montrent une forte dégradation train/test.

## Stress Tests V1.9

| Stress | Résultat |
| --- | --- |
| Sans meilleur mois | PF 1.231, OK |
| Sans top 3 mois | PF 1.096, OK faible |
| Sans top 5 trades | PF 1.157, OK faible |
| Sans top 10 trades | PF 0.976, échec |
| Coûts x1.5 | PF 1.161, OK faible |
| Coûts x2 | PF 0.665, échec |
| Slippage x2 | PF 1.338, OK |
| Risque 0.5% | PF 1.339, DD 1.78%, OK |

## Résultats V2.3

| Test | Trades | Net | PF | Expectancy | DD max | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| MT5 H1 `bar_close` | 200 | 3 382.77 | 1.350 | 16.91 | 0.89% | VALIDABLE moteur |
| MT5 H1 `next_bar_open` | 200 | 3 236.37 | 1.335 | 16.18 | 0.90% | VALIDABLE moteur |
| MT5 H1 `next_bar_open` coûts x1.5 | 200 | 1 673.94 | 1.163 | 8.37 | 0.99% | À RETRAVAILLER |

Monte Carlo coûts x1.5 : DD médian 1.61%, DD 95% 2.51%, pire DD 3.53%, ruine 5/8/10/15% à 0%.

Trade parity coûts x1.5 : 200 trades Python, 200 trades MT5 replay, 200 communs, 0 mismatch direction/entrée/sortie/raison avec tolérance d'exécution 35 points et 2 USD PnL.

Verdict V2.3 : CANDIDAT FRAGILE. Le signal survit au mode `next_bar_open`, mais le stress coûts x1.5 ramène le PF sous 1.20 et concentre trop le profit sur un seul mois.

## Forces

- Profit factor strict supérieur à 1.20.
- Expectancy positive sur 200 trades.
- Drawdown historique et Monte Carlo faibles.
- Règle `exclude_monday` simple et défendable, sans combinaison de filtres excessive.
- Rolling validation majoritairement positive : 19 fenêtres positives sur 20.

## Faiblesses

- Meilleur mois à 36.02% du profit, au-dessus de la limite stricte de 35%.
- Top 3 mois à 73.88% du profit.
- Walk-forward fragile sur 2 folds sur 3.
- Dépendance aux coûts : coûts x2 détruisent le signal.
- Le retrait des 10 meilleurs trades rend le PF inférieur à 1.
- 2025 faible et 2026 partiel négatif dans l'analyse V1.9.

## Raisons De Non-Live

- La parité signaux/trades Python/MT5 est exploitable uniquement avec la source H1 MT5 officielle.
- La résistance aux coûts réels broker reste insuffisante : coûts x1.5 donnent PF 1.163.
- Les règles de validation avancée ne sont pas toutes passées.
- Le candidat reste un objet de recherche, pas une stratégie validée.

## Validations Suivantes

1. Exporter les signaux Python avec `scripts/export_strategy_signals.py`.
2. Lancer l'EA vérificateur MT5 en mode `EnableTrading=false` et exporter `us100_h1_mt5_signals.csv`.
3. Comparer les signaux Python et MT5 avec `scripts/compare_mt5_python_signals.py`.
4. Inspecter les coûts réels avec `scripts/inspect_trade_costs.py`.
5. Relancer le backtest avec `--cost-multiplier 1.5`.
6. Relancer Monte Carlo sur les trades du backtest coûts x1.5.
7. Maintenir le verdict À RETRAVAILLER tant que la parité MT5 ou la robustesse coûts n'est pas démontrée.
