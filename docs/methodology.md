# Méthodologie

## Principe

Le projet cherche un edge réel sur données MT5/FTMO. Une hypothèse doit survivre aux coûts, au spread, au slippage, aux règles de risque, au walk-forward, au Monte Carlo et à un out-of-sample. Sinon elle est rejetée.

## Processus

1. Exporter des données réelles depuis MT5.
2. Diagnostiquer les données avant tout backtest.
3. Lancer un backtest brut, sans optimisation.
4. Lire les métriques principales : profit factor, expectancy, drawdown, trades, stabilité mensuelle.
5. Rejeter rapidement les hypothèses faibles.
6. Optimiser légèrement uniquement les candidats.
7. Tester les candidats par Monte Carlo.
8. Tester les candidats en walk-forward.
9. Garder un vrai out-of-sample non touché par l'optimisation.
10. Ne passer à l'EA qu'après validation.

## Règles

- Ne jamais supprimer les coûts pour améliorer artificiellement un résultat.
- Ne jamais augmenter le risque pour compenser une expectancy négative.
- Ne jamais valider une stratégie avec trop peu de trades.
- Ne jamais choisir un paramètre isolé parce qu'il est le meilleur en backtest.
- Ne jamais lancer d'EA live avant validation.
- Accepter le rejet comme un résultat scientifique utile.

## Modes Non Tradables

Le diagnostic full sample peut ignorer l'arrêt max drawdown pour comprendre la structure d'un signal. Ce mode ne peut jamais produire une stratégie validable et ne doit jamais être utilisé comme preuve tradable.
