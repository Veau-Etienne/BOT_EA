# US100 H1 Trend Pullback Exclude Monday

## Statut

- Actif : US100 / NAS100, symbole broker attendu `US100.cash`.
- Timeframe : H1.
- Stratégie Python : `nas_trend_pullback_exclude_monday`.
- Statut : candidat de recherche.
- Verdict courant : À RETRAVAILLER.
- Trading live : interdit.

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

- La parité Python/MT5 n'est pas encore prouvée.
- La résistance aux coûts réels broker doit être vérifiée.
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
