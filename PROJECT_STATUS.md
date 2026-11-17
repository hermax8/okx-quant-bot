# PROJECT_STATUS — Bot de trading intraday OKX

> Fichier central de suivi. À lire en premier à chaque nouvelle session.
> Dernière mise à jour : 2026-11-17 (fin de session 1)

## Objectif

Construire un système de trading algorithmique intraday, à risque modéré, statistiquement validé,
sélectif (« 3 excellents trades plutôt que 20 médiocres »), connecté à OKX, piloté depuis Telegram,
autonome au quotidien et capable d'analyser ses performances deux fois par semaine.
Capital de départ indiqué : 1 000 €. Aucun levier sans validation.

## Étape actuelle

**Tâche 1 terminée (recherche des stratégies) — en attente de validation de Maxime.**
Aucun backtest réalisé à ce stade. Aucune ligne de code de bot.

## Étapes (ordre imposé par la Tâche 11)

| # | Étape | Statut |
|---|---|---|
| 1 | Recherche des stratégies | ✅ Fait (2026-11-17) |
| 2 | Identification des stratégies prometteuses | ✅ Fait (classement provisoire) |
| 3 | Collecte des données | ⏳ Bloqué : dépôt GitHub à créer |
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

## Décisions proposées (à valider — voir docs/decisions/)

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

1. Valider ou corriger D-001 à D-004.
2. Le compte dérivés X-Perps (questionnaire MiFID) est-il ouvert ?
3. Créer un dépôt GitHub **privé et vide** `okx-quant-bot` et donner l'accès à Claude.

## Prochaine action

Dès validation + dépôt créé : pousser ce dossier, écrire le workflow GitHub Actions de collecte
(bougies 1 min spot + SWAP 2020→2026 pour BTC, ETH, SOL, XRP, DOGE ; funding ; mark price),
contrôles qualité, puis premiers backtests des stratégies 1 à 4 (Tâche 2).

## Journal des sessions

- 2026-11-17 — Session 1 : Tâche 1 (recherche), création du dossier projet et de Git.
