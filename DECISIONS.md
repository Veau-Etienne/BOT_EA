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

## V1.8 — US100_H1 nas_trend_pullback regime filter lab

- Date : 2026-06-29.
- Candidat brut : 246 trades, PF 1.129, expectancy 6.64, max DD 1.18%, concentration meilleur mois 53.63%, top 3 mois 130.75%.
- Filtres testés : 35 filtres simples ou combinaisons limitées, avec segments A/B/C et holdout 2025-03-01 -> 2026-02-25.
- Filtres prometteurs : 0.
- Filtres à retravailler : 6, incluant `exclude_thursday`, `baseline`, `keep_15_18`, `keep_16_19`, `keep_15_20`, `ema_slope_ok`.
- Meilleur score robustesse : `exclude_monday_adx_gt_20`, 178 trades, PF 1.363, expectancy 16.79, max DD 0.83%, holdout OK, segments OK, mais rejeté car concentration meilleur mois 39.32% et top 3 mois 77.37%.
- Filtre le plus proche des règles : `exclude_monday`, 200 trades, PF 1.343, expectancy 16.35, max DD 0.87%, holdout OK, segments OK, mais rejeté car concentration meilleur mois 35.93%, au-dessus de la limite 35%.
- Holdout : plusieurs filtres gardent un holdout positif, mais cela ne suffit pas à compenser la concentration temporelle.
- Segments : les meilleurs filtres ont des segments A/B/C positifs, mais la performance reste trop dépendante de quelques mois.
- Verdict : À RETRAVAILLER, pas de validation avancée.
- Décision : ne pas relancer Monte Carlo/walk-forward filtré, car aucun filtre ne passe les règles prometteuses.
- Prochaine action : analyser un split out-of-sample plus strict ou reformuler le signal ; ne pas lancer d'EA et ne pas promouvoir le candidat en stratégie validable.

## V1.9 — US100_H1 nas_trend_pullback_exclude_monday validation pack

- Date : 2026-06-29.
- Raison du test : `exclude_monday` est le meilleur filtre simple, justifiable et non ultra-spécifique issu du Filter Lab.
- Stratégie créée : `nas_trend_pullback_exclude_monday`, même logique que `nas_trend_pullback`, avec blocage des entrées le lundi.
- Backtest strict : 200 trades, profit net 3 310.95, PF 1.343, expectancy 16.55, winrate 52.00%, max DD 0.89%, max losing streak 8.
- Concentration : meilleur mois 36.02%, top 3 mois 73.88%, stabilité mensuelle 52.78%.
- Monte Carlo : DD médian 1.30%, DD 95% 2.06%, pire DD 3.15%, ruine 5/8/10/15% à 0%, risque recommandé 0.50%.
- Walk-forward : 3 folds, 1 OK et 2 fragiles ; PF test 1.645, 1.050, 1.062 ; forte dégradation train/test sur folds 2 et 3.
- Analyse candidat : 2023 et 2024 solides, 2025 faible mais positif, 2026 négatif sur échantillon partiel ; 16h positif, 17h légèrement négatif.
- Stress tests : sans meilleur mois PF 1.231, sans top 3 mois PF 1.096, sans top 5 trades PF 1.157 ; sans top 10 trades PF 0.976 et expectancy négative ; coûts x1.5 PF 1.161 ; coûts x2 PF 0.665.
- Rolling validation : 20 fenêtres, 19 positives ; une fenêtre 6 mois négative sur 2025-08 -> 2026-01.
- Verdict : À RETRAVAILLER.
- Raison : les métriques strictes et rolling sont bonnes, mais la stratégie ne passe pas la validation avancée car le walk-forward n'est pas majoritairement OK et le meilleur mois reste au-dessus de la limite stricte de 35%.
- Prochaine action : ne pas lancer d'EA ; conserver comme candidat de recherche prioritaire, puis tester un vrai out-of-sample futur ou une simulation paper/demo sans exécution réelle avant toute promotion.

## Décision Courante

Le candidat `US100_H1 / nas_trend_pullback_exclude_monday` reste à retravailler. Aucune stratégie n'est validée.
