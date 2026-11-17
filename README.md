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
