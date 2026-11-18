# okx-quant-bot

Système de trading algorithmique intraday sur OKX (X-Perps / spot), piloté depuis Telegram.
Projet mené étape par étape : recherche → backtests → validation → bot → paper trading → réel.

**Pour reprendre le projet : lire `PROJECT_STATUS.md`.**

## Architecture cible

- Python : moteur principal
- OKX (API v5, hôte EEA `eea.okx.com` pour les ordres) : exécution
- Telegram : pilotage et notifications
- Module quantitatif (`src/okxbot/backtest`, `research/`) : analyses et backtests
- Module de risque (`src/okxbot/risk`) : indépendant de la stratégie et de toute IA
- Module de surveillance (`src/okxbot/monitoring`) : alertes, kill switch

## Arborescence

```
docs/research/       rapports de recherche
docs/decisions/      journal des décisions
docs/sources.md      sources consultées
data/                données (hors Git)
research/            notebooks, journal des essais, relevés
src/okxbot/          code (data, strategies, backtest, risk, regime, execution, telegram, monitoring)
configs/             paramètres (YAML)
reports/             résultats de backtests
tests/               tests automatiques
.github/workflows/   collecte des données
```

## Sécurité

Aucun secret dans Git. Les clés API OKX n'auront **aucun droit de retrait**.
Copier `.env.example` en `.env` (ignoré par Git) pour la configuration locale.

## Bot en simulation (paper trading)

- Workflow `.github/workflows/paper-trading.yml`, toutes les 4 heures (xx:23 UTC). Aucun ordre réel, aucune clé OKX.
- Code : `src/okxbot/live/` (marché en direct, comptabilité simulée, Telegram, cycle).
- Capital fictif 1 000 € : 500 € poche tendance T3 (rééquilibrage quotidien), 500 € poche portage C1 (sélection le lundi).
  Prix et funding : vrais X-Perps d'OKX Europe ; signaux T3 : perpétuels OKX globaux (historique plus long).
- État conservé sur la branche `paper` (`state/paper_state.json`).
- Telegram : secrets du dépôt `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`. Commandes : /status /balance /positions
  /performance /history /risk /report /pause /resume /stop /start /killswitch (réponse au cycle suivant, ≤ 4 h).
- Coupe-circuit : baisse de 25 % depuis le plus haut → plus de nouvelles positions.
