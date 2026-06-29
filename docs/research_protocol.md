# Research Protocol

## Principe

Aucune stratégie n'est validée tant qu'elle ne passe pas l'ensemble du pipeline : backtest strict, Monte Carlo, walk-forward, analyse de concentration, sensibilité des paramètres et holdout temporel.

## Règles Anti-Overfitting

- Les filtres doivent avoir une justification de marché.
- Un filtre n'est accepté que s'il améliore la stabilité, pas seulement le profit net.
- Toute combinaison trop spécifique est suspecte.
- On préfère un profit factor plus faible mais stable à un profit factor élevé concentré sur quelques trades ou quelques mois.
- Le dernier segment temporel doit être gardé comme holdout si possible.
- Le full sample diagnostic ne prouve jamais qu'une stratégie est tradable.
- Les filtres qui suppriment trop de trades doivent être pénalisés.
- Une amélioration sur un seul segment n'est pas une validation.

## Décision

Un candidat peut passer en validation avancée seulement si la robustesse se maintient sur research, holdout, segments temporels et tests de sensibilité. Sinon il reste à retravailler ou il est rejeté.
