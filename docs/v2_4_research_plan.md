# Plan de Recherche V2.4 — XAUUSD M15/M30 Strategy Exploration

## Pourquoi explorons-nous XAUUSD M15/M30 ?

Le candidat actuel `US100_H1 / nas_trend_pullback_exclude_monday` est fragile :
- Profit Factor sous coûts x1.5 : 1.163 (sous le seuil VALIDABLE de 1.20).
- Concentration de profit à 65.22% sur un seul mois sous coûts x1.5.
- Walk-forward fragile (2/3 folds dégradés).
- Marge de sécurité faible : coûts x2 détruisent la stratégie (PF 0.665).

L'objectif n'est pas de trouver une stratégie parfaite unique, mais de construire un portefeuille d'edges peu corrélés. XAUUSD M15/M30 est une hypothèse distincte de US100 H1, avec une microstructure différente.

Raisons concrètes :
- XAUUSD présente des dynamiques de liquidité intraday bien documentées (sweeps).
- Le M30 offre un compromis bruit/signal potentiellement meilleur que le M15.
- Les patterns de compression/expansion de volatilité sont exploitables sur XAU.
- La corrélation XAU/US100 est faible sur les tendances intraday → diversification.

## Pourquoi les anciennes stratégies XAU sont rejetées

Les stratégies V1.x sur XAUUSD M15 ont été rejetées (PF < 1, expectancy négative) :

| Stratégie | Trades | PF | Décision |
|---|---|---|---|
| xau_trend_breakout | 73 | 0.469 | REJETÉE |
| xau_failed_breakout_reversal | 75 | 0.577 | REJETÉE |
| xau_pullback_trend | 123 | 0.755 | REJETÉE |

Ces stratégies ne sont pas optimisées davantage car :
- Les rejeter sur PF < 1 est la règle absolue.
- Optimiser une stratégie rejetée génère de l'overfitting.
- L'hypothèse fondamentale (breakout simple, trend simple) est probablement inadaptée à XAU M15.

Les nouvelles stratégies V2.4 sont des hypothèses fondamentalement différentes :
- Liquidity sweep (inversion après chasse des stops).
- Compression breakout + retest (validation après faux breakout).
- HTF dual EMA trend (filtre de tendance supérieur plus strict).
- Session momentum (dynamique directionnelle horaire).

## Nouvelles familles testées

### Famille A — XAU M15 Liquidity Sweep Reversal
Fichier : `src/strategies/xau_liquidity_sweep_reversal.py`

Hypothèse : XAUUSD chasse souvent les extrêmes intraday puis réintègre le range.
On trade la réintégration après le sweep, pas le breakout.

Signal :
- Range de référence = max/min des N dernières bougies (shift 2 pour éviter lookahead).
- Si la bougie précédente a cassé le high du range puis la bougie courante clôture en dessous → short.
- Inverse pour un sweep du low → long.
- SL : au-delà de la mèche du sweep + buffer ATR.
- TP : midpoint du range ou 1.5R.

### Famille B — XAU M30 HTF Trend Pullback
Fichier : `src/strategies/xau_m30_htf_trend_pullback.py`

Hypothèse : XAU M30 peut être exploitable avec un double filtre EMA50/EMA200.
Les pullbacks vers l'EMA20 suivis d'une reprise dans la direction de la tendance.

Signal :
- Tendance : EMA50 > EMA200 pour longs, inverse pour shorts.
- Pullback : low de la bougie précédente touche l'EMA20.
- Reprise : bougie courante haussière au-dessus de la précédente et au-dessus EMA20.
- SL : swing récent ou ATR fallback.
- TP : 1.5R.

### Famille C — XAU M15 Volatility Compression Retest
Fichier : `src/strategies/xau_volatility_compression_retest.py`

Hypothèse : Les breakouts directs XAU M15 échouent, mais breakout après compression
puis retest peuvent avoir un meilleur edge.

Signal :
- Compression : ATR/ATR_mean < seuil sur la fenêtre de référence.
- Breakout : bougie i-1 clôture au-dessus/en dessous du range de compression.
- Retest : bougie i touche le niveau cassé puis clôture de l'autre côté → signal.
- SL : bas de la bougie de retest - buffer ATR.
- TP : 1.5R.

### Famille D — XAU M30 Session Momentum Continuation
Fichier : `src/strategies/xau_m30_session_momentum_continuation.py`

Hypothèse : Le momentum directionnel sur XAU M30 pendant les sessions London/US
peut offrir un signal exploitable quand confirmé par deux bougies consécutives.

Signal :
- Deux bougies haussières consécutives + close au-dessus EMA50 → long.
- Deux bougies baissières consécutives + close en dessous EMA50 → short.
- SL : ATR ou swing récent.
- TP : 1.5R.

## Règles anti-overfitting V2.4

1. **Backtest brut obligatoire** avant toute optimisation.
2. **Aucune optimisation massive** : les paramètres par défaut sont testés en premier.
3. **entry_mode next_bar_open** obligatoire pour toute validation sérieuse.
4. **Coût x1.5 obligatoire** pour tout candidat.
5. **Minimum 100 trades** souhaité (sauf stratégie volontairement rare et justifiée).
6. **Pas de stratégie optimisée** si le PF brut < 1.0.
7. **Ne pas relancer les stratégies XAU V1.x rejetées** sans changement d'hypothèse fondamental.
8. **Diagnostic data** obligatoire pour toute nouvelle source de données.

## Critères de promotion d'une stratégie

| Étape | Critère |
|---|---|
| Scan brut | PF > 1.05, expectancy positive, DD < 8% |
| Candidat | PF > 1.20, trades >= 100, concentration < 50% |
| Validation avancée | Monte Carlo, walk-forward, stress tests, analyse concentration |
| Parité MT5 | Uniquement après validation avancée positive |

Seuils explicites :
- PF < 1.0 → REJETÉE, ne pas optimiser.
- PF 1.05 à 1.20 → À RETRAVAILLER.
- PF > 1.20 avec coûts x1.5 encore > 1.05, DD contrôlé, stabilité temporelle → CANDIDAT SÉRIEUX.
- Pas de live ni FTMO sans avoir passé tous les jalons ci-dessus.

## Pourquoi aucune stratégie ne doit être lancée live

- Aucune stratégie n'est actuellement validée (statut V2.3).
- Le candidat US100 H1 est fragile et non tradable.
- Le scan V2.4 est exploratoire : un bon résultat brut est une hypothèse à tester, pas une validation.
- La parité MT5, le Monte Carlo et le walk-forward sont requis avant toute exécution.
- FTMO et tout compte réel sont hors scope tant qu'aucune stratégie n'est validée.

## Objectif de portefeuille

L'objectif final est de trouver plusieurs edges peu corrélés :
- US100 H1 momentum (candidat fragile actuel).
- XAU M15/M30 (exploration V2.4).
- Éventuellement EURUSD si les données existent.

Une corrélation basse entre stratégies candidates permet de réduire le drawdown cumulé
sans sacrifier le rendement attendu. Cette analyse est intégrée dans le rapport d'exploration.
