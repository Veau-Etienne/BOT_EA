# Decisions Scientifiques

Toutes les décisions ci-dessous suivent les métriques, pas l'intuition. Une stratégie rejetée ne doit pas être optimisée pour forcer un résultat.

| Date | Actif | Timeframe | Stratégie | Trades | Profit factor | Expectancy | Max DD | Décision | Raison | Prochaine action |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2026-06-29 | XAUUSD | M15 | xau_trend_breakout | 73 | 0.469 | -60.49 | 4.96% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser, changer d'hypothèse/timeframe |
| 2026-06-29 | XAUUSD | M15 | xau_failed_breakout_reversal | 75 | 0.577 | -65.42 | 4.99% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |
| 2026-06-29 | XAUUSD | M15 | xau_pullback_trend | 123 | 0.755 | -36.57 | 4.92% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |
| 2026-06-29 | US100 | M15 | nas_opening_breakout | 125 | 0.641 | -40.08 | 4.75% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |
| 2026-06-29 | US100 | M15 | nas_post_open_mean_reversion | 127 | 0.619 | -38.40 | 4.93% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |
| 2026-06-29 | US100 | M15 | nas_trend_pullback | 131 | 0.570 | -39.20 | 4.96% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |
| 2026-06-29 | US100 | M15 | nas_opening_range_retest | 118 | 0.628 | -42.93 | 4.91% | REJETÉE | PF < 1, expectancy négative, arrêt max drawdown | Ne pas optimiser |

## V1.7 — US100_H1 nas_trend_pullback candidate review

- Date : 2026-06-29.
- Actif : US100/NAS100.
- Timeframe : H1.
- Stratégie : `nas_trend_pullback`.
- Données : `data/resampled/US100_H1.csv`, période 2023-02-27 -> 2026-02-25, 17 692 bougies.
- Diagnostic data : 0 doublon, 0 valeur manquante, 2 zero-range candles, 29 bougies extrêmes, spread moyen 131.98 points, gaps principalement week-ends/jours fériés.
- Backtest strict : 246 trades, profit net 1 633.80, PF 1.129, expectancy 6.64, max DD 1.18%, max losing streak 10.
- Monte Carlo : DD médian 1.84%, DD 95% 2.77%, probabilité de ruine 0% aux seuils 5/8/10/15%, risque recommandé 0.50%.
- Walk-forward : 3 folds, 2 OK, 1 rejeté ; le fold 2 a PF test 0.841 et expectancy test -8.11.
- Analyse candidat : concentration meilleur mois 53.63%, top 3 mois 130.75%, stagnation maximale 68 trades, performance très dépendante de certaines périodes.
- Sensibilité : 16 variations légères positives, mais verdict `fragile_concentrated`; la concentration reste le défaut principal.
- Verdict : À RETRAVAILLER, non validable, non tradable.
- Raison : edge potentiel faible mais réel en strict, cependant PF < 1.20, profit concentré, walk-forward mitigé et défaut de stabilité temporelle.
- Prochaine action : ne pas lancer d'EA ; isoler les régimes qui portent le signal, surtout filtres temporels/jours/ATR, puis retester hors échantillon sans optimisation massive.

## Décision Courante

Le candidat `US100_H1 / nas_trend_pullback` reste à retravailler. Aucune stratégie n'est validée.
