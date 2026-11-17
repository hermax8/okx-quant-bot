# PROJECT_STATUS — Bot de trading intraday OKX

> Fichier central de suivi. À lire en premier à chaque nouvelle session.
> Dernière mise à jour : 2026-11-17 (session 1, suite)

## Objectif

Construire un système de trading algorithmique intraday, à risque modéré, statistiquement validé,
sélectif (« 3 excellents trades plutôt que 20 médiocres »), connecté à OKX, piloté depuis Telegram,
autonome au quotidien et capable d'analyser ses performances deux fois par semaine.
Capital de départ indiqué : 1 000 €. Aucun levier sans validation.

## Étape actuelle

**Tâche 2 en cours : dépôt GitHub hermax8/okx-quant-bot créé (privé), première collecte lancée le 17/11/2026 vers 22:35 UTC.**
Aucun backtest réalisé à ce stade. Aucune ligne de code de bot.

Réponses de Maxime (2026-11-17, 23:15) : 1) d'accord pour passer par GitHub Actions ;
2) d'accord pour s'appuyer sur le spot ou une autre plateforme pour compenser l'historique court des X-Perps ;
3) le compte X-Perps est ouvert. Le classement et les critères de sélection n'ont pas été contestés :
ils sont considérés comme validés (D-001 à D-004).

## Étapes (ordre imposé par la Tâche 11)

| # | Étape | Statut |
|---|---|---|
| 1 | Recherche des stratégies | ✅ Fait (2026-11-17) |
| 2 | Identification des stratégies prometteuses | ✅ Fait (classement provisoire) |
| 3 | Collecte des données | ⏳ Première collecte en cours (GitHub Actions) |
| 4 | Premiers backtests | ⬜ |
| 5 | Comparaison des résultats | ⬜ |
| 6 | Optimisation raisonnable | ⬜ |
| 7 | Validation statistique | ⬜ |
| 8 | Présentation de la stratégie finale | ⬜ |
| 9 | Validation par Maxime | ⬜ |
| 10 | Développement du bot | ⬜ |
| 11 | Connexion Telegram | ⬜ |
| 12 | Connexion OKX | ⬜ |
| 13 | Paper trading | ⬜ |
| 14 | Validation en conditions réelles simulées | ⬜ |
| 15 | Passage progressif au réel (après autorisation) | ⬜ |

## Résultats obtenus (session 1)

- Rapport Tâche 1 : `docs/research/2026-11-17_T1_recherche_strategies.md`
  (version éditable : https://claude.ai/artifact/6ERu3WYAom3QTnnG7fPgnh).
- Relevé réel des volumes OKX (perpétuels USDT, marché global, 17/11/2026 21:55 UTC) :
  `research/snapshots/2026-11-17_okx_swap_tickers.json`. BTC + ETH = 55 % du volume.

- Collecteur (`src/okxbot/data/`) : client API publique OKX avec limitation de débit et reprise,
  bougies en Parquet mensuel, funding, instruments global + EEA, contrôle qualité. 6 tests passent.
- Workflow `.github/workflows/collect-data.yml` : perpétuels BTC, ETH en 1 min, SOL, XRP, DOGE en 5 min,
  spot BTC, ETH en 5 min, depuis 2020 ; funding et instruments ; publication sur la branche `data` ;
  relance chaque dimanche 03:17 UTC et à chaque modification du collecteur. Budget estimé :
  ~430 min de GitHub Actions pour la première collecte, ~25 min/semaine ensuite (quota gratuit 2 000 min/mois).
- Vérifié via l'API réelle : OKX fournit les bougies 1 min de BTC-USDT-SWAP au moins depuis janvier 2020.
  En revanche, l'historique public du funding ne remonte pas à 2020 (réponse vide pour septembre 2020) :
  il faudra compléter avec le funding de Binance (data.binance.vision) comme approximation.

## Décisions (voir docs/decisions/)

- D-001 Marché : OKX Europe, X-Perps en levier x1 (long + short), BTC et ETH en priorité.
- D-002 Classement : 1) breakout/tendance 15 min–1 h filtré 4 h ; 2) momentum intraday ;
  3) squeeze de volatilité ; 4) retour à la moyenne en régime latéral ; 5) pairs ETH/BTC ;
  6) meta-labeling = score /100 ; 7) filtres (régime, macro, funding, liquidité).
  Écartés : scalping 1–5 min, carnet d'ordres, grid/martingale.
- D-003 Critères de sélection (hors échantillon, nets de coûts) : Sharpe ≥ 1, DSR ≥ 95 %,
  PBO ≤ 0,30, PF ≥ 1,3, DD ≤ 15 %, ≥ 150 trades, ≥ 60 % de fenêtres WF gagnantes,
  rentable avec coûts doublés.
- D-004 Données : API publique OKX via GitHub Actions (le poste de travail Claude ne joint pas OKX).
  Découpage : dev 2020–2023, validation 2024–oct. 2025, test scellé nov. 2025–nov. 2026.

## Problèmes rencontrés

- L'espace de travail de Claude ne joint ni OKX, ni Binance, ni Hugging Face (proxy 403). GitHub et PyPI OK.
- Jeton GitHub de la session invalide : Claude ne peut pas créer de dépôt.
- X-Perps lancés le 15/04/2026 : historique court, funding horaire (≠ 8 h sur le global).
- Frais spot sans compte dérivés : sources contradictoires (0,10/0,20 % ou 0,20/0,35 %).
- GitHub Actions inadapté pour faire tourner le bot 24 h/24 → VPS à prévoir (Tâche 6).

## Questions ouvertes pour Maxime

Aucune pour l'instant. Note : Claude ne peut pas lire l'état des exécutions GitHub Actions (pas de jeton API) ;
il vérifie le résultat via la branche `data`.

## Prochaine action

Vérifier la branche `data` (rapports dans reports/collect/), les rapports qualité, ajouter le funding Binance, puis premiers backtests des stratégies 1 à 4.
Pour reprendre depuis la sauvegarde : `git clone okx-quant-bot.bundle okx-quant-bot`.

## Journal des sessions

- 2026-11-17 — Session 1 : Tâche 1 (recherche), création du dossier projet et de Git.
- 2026-11-17 — Session 1 (suite) : validation de Maxime, collecteur de données + workflow GitHub Actions.
