# Règles De Validation

## VALIDABLE

Une stratégie ne peut être `VALIDABLE` que si elle respecte tous les critères suivants :

- profit factor > `1.20` ;
- expectancy positive ;
- nombre de trades suffisant, par défaut au moins `100` ;
- max drawdown < `8%` ;
- Monte Carlo 95% drawdown < `10%` ;
- walk-forward acceptable ;
- profit non concentré sur un seul mois ;
- pas d'arrêt prématuré par max drawdown ;
- logique exploitable sans modifier les coûts réels.

## À RETRAVAILLER

Une stratégie peut être `À RETRAVAILLER` si :

- profit factor entre `1.05` et `1.20` ;
- expectancy proche de zéro ou positive ;
- défaut identifiable ;
- drawdown contrôlable ;
- volume de trades suffisant pour justifier une analyse ;
- pas de dépendance évidente à une seule période.

Une stratégie `À RETRAVAILLER` n'est pas tradable. Elle autorise seulement une analyse plus profonde.

## REJETÉE

Une stratégie doit être `REJETÉE` si au moins un signal fort apparaît :

- profit factor < `1.0` ;
- expectancy négative ;
- drawdown élevé ;
- arrêt par max drawdown ;
- walk-forward mauvais ;
- Monte Carlo dangereux ;
- trop peu de trades ;
- performance concentrée sur une seule période ;
- amélioration obtenue uniquement par optimisation.

## Anti-Overfitting

- Ne pas optimiser une stratégie déjà rejetée.
- Préférer une zone robuste de paramètres à un point isolé.
- Comparer train/test, Monte Carlo et out-of-sample.
- Documenter les rejets dans `DECISIONS.md`.
