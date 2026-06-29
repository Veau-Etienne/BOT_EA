# Trading Lab

Laboratoire local de trading algorithmique pour tester des hypothèses sur données MT5/FTMO avec une méthode stricte : diagnostic des données, backtests bruts, métriques, Monte Carlo, walk-forward, anti-overfitting et rejet rapide des idées faibles.

Statut scientifique actuel : aucune stratégie n'est validée. Toutes les hypothèses M15 testées jusqu'à V1.5 sont rejetées.

Ce dépôt ne fournit aucun conseil financier. Les résultats de backtest ne doivent jamais être utilisés comme promesse de performance ou comme justification d'un risque réel.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Vérification :

```bash
.venv/bin/python -m compileall src scripts
```

## Structure

```text
config/                 Paramètres actifs, risque et stratégies
data/raw/               CSV bruts MT5 locaux, non versionnés
data/resampled/         CSV M30/H1 générés, non versionnés
data/reports/           Rapports générés, non versionnés
reports/                Copies latest_*, non versionnées
docs/                   Méthodologie, règles de validation, FTMO
mql5/                   EAs et includes MQL5
scripts/                Commandes CLI
src/backtest/           Moteur, métriques, reporting, Monte Carlo, walk-forward
src/data/               Parser MT5, nettoyage, diagnostics, resampling
src/indicators/         EMA, ATR, Donchian, RSI
src/optimization/       Grid search avec garde-fous anti-overfitting
src/strategies/         Stratégies Python testables
```

## Workflow De Validation

1. Exporter les données depuis MT5 vers `data/raw/`.
2. Diagnostiquer le CSV.
3. Lancer un backtest brut.
4. Lire les métriques et le rapport.
5. Rejeter immédiatement les hypothèses faibles.
6. Scanner plusieurs familles de stratégies sans optimisation.
7. Optimiser légèrement uniquement les candidats non rejetés.
8. Valider par Monte Carlo, walk-forward et out-of-sample.
9. Ne créer ou lancer un EA de stratégie qu'après validation scientifique.

## Commandes Principales

Diagnostic data :

```bash
.venv/bin/python scripts/data_diagnostics.py --data data/raw/XAUUSD_M15.csv --output data/reports/XAUUSD_M15_diagnostics.md
```

Backtest :

```bash
.venv/bin/python scripts/run_backtest.py --data data/raw/XAUUSD_M15.csv --strategy xau_trend_breakout
```

Monte Carlo :

```bash
.venv/bin/python scripts/run_monte_carlo.py --trades reports/latest_trades.csv
```

Walk-forward :

```bash
.venv/bin/python scripts/run_walk_forward.py --data data/raw/XAUUSD_M15.csv --strategy xau_trend_breakout
```

Strategy Scanner brut :

```bash
.venv/bin/python scripts/run_strategy_scanner.py \
  --assets XAUUSD:data/raw/XAUUSD_M15.csv US100:data/raw/US100_M15.csv \
  --output data/reports/strategy_scanner.md
```

Strategy Scanner full sample non tradable :

```bash
.venv/bin/python scripts/run_strategy_scanner.py \
  --assets XAUUSD:data/raw/XAUUSD_M15.csv US100:data/raw/US100_M15.csv \
  --output data/reports/strategy_scanner_full_sample.md \
  --diagnostic-full-sample
```

Resampling M30/H1 :

```bash
.venv/bin/python scripts/resample_data.py \
  --data data/raw/XAUUSD_M15.csv \
  --timeframes M30,H1 \
  --output-dir data/resampled
```

Sanity check data/config :

```bash
.venv/bin/python scripts/run_sanity_check.py \
  --assets XAUUSD:data/raw/XAUUSD_M15.csv US100:data/raw/US100_M15.csv \
  --output data/reports/sanity_check.md
```

## Stratégies Disponibles

XAUUSD :

- `xau_trend_breakout`
- `xau_failed_breakout_reversal`
- `xau_pullback_trend`

US100/NAS100 :

- `nas_opening_breakout`
- `nas_post_open_mean_reversion`
- `nas_trend_pullback`
- `nas_opening_range_retest`

EURUSD :

- `eur_london_breakout`
- `eur_london_mean_reversion`

## Règles De Validation

Une stratégie ne peut être `VALIDABLE` que si elle respecte au minimum :

- profit factor > `1.20` ;
- expectancy positive ;
- nombre de trades suffisant, par défaut au moins `100` ;
- max drawdown < `8%` ;
- Monte Carlo 95% drawdown < `10%` ;
- walk-forward acceptable ;
- profit non concentré sur un seul mois.

Voir [docs/validation_rules.md](docs/validation_rules.md).

## État Scientifique Actuel

Résultat V1.5 :

- 7 stratégies testées ;
- 0 `VALIDABLE` ;
- 0 `À RETRAVAILLER` ;
- 7 `REJETÉE`.

Les stratégies M15 rejetées ne doivent pas être optimisées davantage. La V1.6 vérifie d'abord que le backtester, les coûts, les points, les spreads, les timezones et les sessions ne pénalisent pas artificiellement les résultats.

## Sécurité Git

Ne jamais commiter :

- `.env` ;
- `.venv/` ;
- gros CSV de marché ;
- rapports générés ;
- identifiants MT5, FTMO ou broker ;
- logs.

Les dossiers de données restent visibles via `.gitkeep`.

## Limites

- Backtest OHLC conservateur : si SL et TP sont touchés dans la même bougie, le SL est prioritaire.
- Pas de tick data, carnet d'ordres, latence ou liquidité dynamique.
- Le spread vient du CSV si disponible, sinon de la config.
- Aucun EA live ne doit être lancé tant qu'aucune stratégie n'est validée.
