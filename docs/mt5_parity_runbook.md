# MT5 Parity Runbook

## Objectif

Vérifier que les signaux du candidat `US100_H1 / nas_trend_pullback_exclude_monday` calculés en Python sont reproductibles côté MT5/MQL5. Cette vérification ne sert pas à trader. Elle sert uniquement à comparer timestamps, direction, entrée théorique, stop loss et take profit.

## Interdiction Live

- Ne pas lancer d'EA live.
- Ne pas activer AutoTrading pour cette vérification.
- Ne jamais ouvrir de position.
- Garder `EnableTrading=false`.
- Le fichier `US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5` est un vérificateur, pas un robot de trading.

## Prérequis

- Données Python : `data/resampled/US100_H1.csv`.
- EA vérificateur : `mql5/Experts/US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5`.
- MT5 installé via Wine ou wrapper MetaQuotes macOS.
- Symbole broker : `US100.cash`.
- Timeframe MT5 : H1.

## Chemins MT5 Attendus

Chemin probable :

`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/`

Le script de localisation affiche :

- `terminal64.exe`
- `metaeditor64.exe`
- `MQL5/Experts`
- `MQL5/Files`

Commande :

```bash
.venv/bin/python scripts/locate_mt5_wine.py
```

## Préparer L'EA

Commande :

```bash
.venv/bin/python scripts/prepare_mt5_verifier.py \
  --ea mql5/Experts/US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5
```

Le script copie l'EA vers `MQL5/Experts`. Si `metaeditor64.exe` et Wine sont disponibles, il tente une compilation automatique. Si la compilation automatique échoue ou n'est pas disponible, compiler manuellement.

## Compilation Manuelle

1. Ouvrir MetaEditor.
2. Ouvrir `US100_H1_TrendPullback_ExcludeMonday_Verifier.mq5`.
3. Compiler.
4. Corriger toute erreur de compilation.

## Générer Le CSV MT5

1. Ouvrir MT5.
2. Ouvrir le graphique `US100.cash` en H1.
3. Attacher `US100_H1_TrendPullback_ExcludeMonday_Verifier` au graphique.
4. Vérifier `EnableTrading=false`.
5. Ne pas activer AutoTrading.
6. Laisser l'EA lire les bougies et écrire `us100_h1_mt5_signals.csv`.

Le CSV doit apparaître dans `MQL5/Files/us100_h1_mt5_signals.csv`.

Quand l'EA est lancé via Strategy Tester, le CSV peut apparaître dans un dossier agent :

`Tester/Agent-127.0.0.1-3000/MQL5/Files/us100_h1_mt5_signals.csv`

`scripts/run_mt5_parity_check.py` cherche automatiquement dans les deux emplacements.

## Exporter Les Signaux Python

```bash
.venv/bin/python scripts/export_strategy_signals.py \
  --data data/resampled/US100_H1.csv \
  --strategy nas_trend_pullback_exclude_monday \
  --asset US100_H1 \
  --output data/reports/US100_H1_nas_trend_pullback_exclude_monday_signals.csv
```

## Comparer Python Et MT5

Commande automatique :

```bash
.venv/bin/python scripts/run_mt5_parity_check.py \
  --python-signals data/reports/US100_H1_nas_trend_pullback_exclude_monday_signals.csv \
  --output data/reports/US100_H1_signal_parity_report.md
```

Commande directe si le CSV MT5 est connu :

```bash
.venv/bin/python scripts/compare_mt5_python_signals.py \
  --python-signals data/reports/US100_H1_nas_trend_pullback_exclude_monday_signals.csv \
  --mt5-signals "<chemin>/MQL5/Files/us100_h1_mt5_signals.csv" \
  --output data/reports/US100_H1_signal_parity_report.md
```

## Lire Le Verdict

- `PARITY_OK` : signaux alignés dans la tolérance configurée.
- `PARITY_WARNING` : écarts limités, inspection nécessaire avant toute suite.
- `PARITY_FAIL` : parité échouée, corriger timezone, EMA, ATR, timestamp, spread ou SL/TP.
- `PARITY_BLOCKED_MT5_CSV_MISSING` : le CSV MT5 n'existe pas encore, générer le fichier depuis MT5.

## Dernier Résultat US100 H1

- Date : 2026-06-30.
- Compilation EA : OK via le Wine embarqué dans l'app MetaTrader 5.
- Strategy Tester : OK sur `US100.cash` H1, sans ordre réel.
- Signaux Python : 311.
- Signaux MT5 : 367.
- Verdict : `PARITY_FAIL`.
- Conclusion : ne pas promouvoir le candidat ; corriger d'abord la divergence de données ou de logique Python/MT5.
