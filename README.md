# Trading Lab

Laboratoire local de trading algorithmique pour tester des hypothèses sur données MT5/FTMO avec une méthode stricte : diagnostic des données, backtests bruts, métriques, Monte Carlo, walk-forward, anti-overfitting et rejet rapide des idées faibles.

Statut scientifique actuel : aucune stratégie n'est validée. Toutes les hypothèses M15 testées jusqu'à V1.5 sont rejetées.

Statut courant V2.4 : la recherche ne vise pas une stratégie parfaite unique, mais un portefeuille d'edges robustes peu corrélés. Le candidat prioritaire `US100_H1 / nas_trend_pullback_exclude_monday` reste fragile (PF 1.335 base, 1.163 sous coûts x1.5). L'exploration V2.4 sur XAUUSD M15/M30 a testé 4 nouvelles familles : 3 rejetées, 1 à retravailler (`xau_m30_session_momentum_continuation`, PF 1.118). Aucun live, aucune activation AutoTrading, aucune exécution réelle.

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

Validation réaliste du candidat US100 H1 :

```bash
.venv/bin/python scripts/run_backtest.py \
  --data data/resampled/US100_H1_FROM_MT5.csv \
  --strategy nas_trend_pullback_exclude_monday \
  --timeframe H1 \
  --entry-mode next_bar_open

.venv/bin/python scripts/run_backtest.py \
  --data data/resampled/US100_H1_FROM_MT5.csv \
  --strategy nas_trend_pullback_exclude_monday \
  --timeframe H1 \
  --entry-mode next_bar_open \
  --cost-multiplier 1.5

.venv/bin/python scripts/run_monte_carlo.py \
  --trades reports/latest_trades.csv \
  --output data/reports/US100_H1_FROM_MT5_next_open_cost15_monte_carlo.json
```

Parité trade Python/MT5, uniquement avec un EA de replay sans ordre réel :

```bash
.venv/bin/python scripts/compare_mt5_python_trades.py \
  --python-trades reports/latest_trades.csv \
  --mt5-trades data/reports/US100_H1_mt5_trade_replay_cost15.csv \
  --output data/reports/US100_H1_trade_parity_cost15_report.md
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

- `xau_trend_breakout` (rejetée)
- `xau_failed_breakout_reversal` (rejetée)
- `xau_pullback_trend` (rejetée)
- `xau_liquidity_sweep_reversal` (V2.4 — rejetée)
- `xau_m30_htf_trend_pullback` (V2.4 — rejetée)
- `xau_volatility_compression_retest` (V2.4 — rejetée)
- `xau_m30_session_momentum_continuation` (V2.4 — à retravailler)

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

Résultat V2.4 (cumul) :

- 14 combinaisons testées.
- 0 `VALIDABLE` (stratégie entièrement validée).
- 1 candidat fragile : `US100_H1 / nas_trend_pullback_exclude_monday`, PF 1.335 base, non tradable.
- 1 `À RETRAVAILLER` XAU : `xau_m30_session_momentum_continuation` M30, PF 1.118, 649 trades.
- Le reste : `REJETÉE`.
- Objectif portefeuille : chercher plusieurs edges peu corrélés avant d'envisager un live.

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
