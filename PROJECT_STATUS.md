# PROJECT_STATUS — Bot de trading intraday OKX

> Fichier central de suivi. À lire en premier à chaque nouvelle session.
> Dernière mise à jour : 2026-11-18 (T3 tendance multi-jours)

## Objectif

Construire un système de trading algorithmique intraday, à risque modéré, statistiquement validé,
sélectif (« 3 excellents trades plutôt que 20 médiocres »), connecté à OKX, piloté depuis Telegram,
autonome au quotidien et capable d'analyser ses performances deux fois par semaine.
Capital de départ indiqué : 1 000 €. Aucun levier sans validation.

## Étape actuelle

**Tâche 2 : aucune stratégie validée après 3 familles (intraday, 4 h, tendance multi-jours T3 sur 20 cryptos : Sharpe 0,49, DD -58 %). Pas de déploiement. Prochaine piste proposée à Maxime : stratégies neutres au marché (portage du funding), et bot en mode simulation.**
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
| 3 | Collecte des données | ✅ Fait (2026-11-18), complément X-Perps + funding Binance lancé |
| 4 | Premiers backtests | ✅ Vague 1 faite (2026-11-18) |
| 5 | Comparaison des résultats | ✅ Vagues 1 et 2 (2026-11-18) |
| 6 | Optimisation raisonnable | ✅ v0.1 figée (D-007) |
| 7 | Validation statistique | ✗ v0.1 (validation) et v0.2 (test scellé) échouent (2026-11-18) |
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

- Collecte vérifiée : 7 séries 2020→2026, couverture 100 %, aucun trou, aucune bougie incohérente
  (rapport : `docs/research/2026-11-18_T2_collecte_donnees.md`). 262 X-Perps identifiés ;
  BTC X-Perp = BTC-USD_UM_XPERP-310404, contrat 0,0001 BTC, minimum 1 contrat.
- Funding OKX limité aux 3 derniers mois via l'API → ajout du funding Binance depuis 2020.

- Vague 1 (`docs/research/2026-11-18_T2_premiers_backtests.md`) : moteur événementiel numba
  (stops minute par minute, pire cas, frais, slippage, funding, sans levier), 65 configs × 2 actifs,
  walk-forward 2021–2023. Sharpe OOS : S1 -0,03 ; S2 0,55 ; S3 -0,46 ; S4 -3,36. Tout négatif avec coûts x2.
  Les frais mangent la moitié de l'avantage brut. 19 tests passent.
- Bug corrigé : unités ms/ns dans le moteur (trades sans fin) — test de régression ajouté.

- Vague 2 (`docs/research/2026-11-18_T2_vague2_backtests.md`) : 4 h + entrées limites + 5 actifs.
  S1b Sharpe 1,11 (DD 17 %, DOGE 55 % du profit), S2b 1,49 (DD 12,5 %, PBO 0,09), S2c 1 h limites 0,38,
  combinaison 1,61 (DD 19 %). 525 essais cumulés. L'horizon est le levier principal.
- Moteur : ordres limites (remplissage strict, frais maker), 24 tests passent.
- Collecte : bug de récupération de la branche data corrigé (erreur 128) ; journaux d'erreur publiés.
  Les X-Perps montrent des minutes à volume nul : liquidité à mesurer.

- Validation v0.1 (`docs/research/2026-11-18_T2_validation_v0.1.md`) : +35,1 %, Sharpe 0,91, DD -24,6 %, PF 1,15,
  6/8 trimestres positifs, coûts x2 : +13 %. S2b seule : Sharpe 1,19 ; S1b : 0,50. BTC perdant. Validation consommée :
  le seul juge neutre restant est le test scellé (nov. 2025 → nov. 2026).

- Maxime (18/11, 15:30) : veut la stratégie la plus rentable, accepte le levier, délègue les choix à Claude.
- Analyse du risque (`research/experiments/t2_risk_sizing.py`) : Kelly estimé ~4 %/trade (surestimé) ; choix 1 %.
- X-Perps : BTC ~94 M$/jour, ETH ~22 M$/jour, 17–25 % de minutes sans échange, écart de prix p95 ~20 pb vs global.
  Funding Binance 2020–2026 et OKX intégrés (funding réel signé dans le moteur).
- Test scellé v0.2 (`docs/research/2026-11-18_T2_test_scelle_v0.2.md`) : ÉCHEC, -2,7 % dans une année où
  les cryptos ont perdu 41 à 69 % ; shorts +9,8 %, longs -9,7 %.

- Maxime (18/11, 15:54) : accord pour positions multi-jours long/short et bot en simulation.
- Collecte du panier U20 (bougies 4 h + funding Binance) réussie.
- T3 (`docs/research/2026-11-18_T3_tendance_multi_jours.md`) : règles figées D-009, ÉCHEC (3/6 années positives,
  DD -58 %, shorts perdants sur la période complète, +20 % sur les 12 derniers mois).

- C1 portage du funding (`docs/research/2026-11-18_C1_portage_funding.md`) : D-010, ÉCHEC de justesse
  (CAGR 7,5 %, Sharpe 5,8, DD -1 %, mais 0 % sur 12 mois : rien à porter depuis 2025).

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

Décision de Maxime : (a) piste neutre au marché (portage du funding : long spot / short X-Perp quand le funding
est positif, levier modéré), à pré-enregistrer puis tester ; (b) construction du bot en mode simulation
(GitHub Actions + Telegram) indépendante de la stratégie.

## Journal des sessions

- 2026-11-17 — Session 1 : Tâche 1 (recherche), création du dossier projet et de Git.
- 2026-11-17 — Session 1 (suite) : validation de Maxime, collecteur de données + workflow GitHub Actions.
- 2026-11-18 — Vérification de la première collecte, ajout X-Perps et funding Binance.
- 2026-11-18 — Vague 1 de backtests (4 stratégies, BTC/ETH, 2020–2023).
- 2026-11-18 — Vague 2 (4 h, entrées limites, 5 actifs) ; correction de la collecte.
- 2026-11-18 — Choix de Maxime : combinaison S1b+S2b ; pré-enregistrement D-007 ; validation 2024–2025 : échec aux critères.
- 2026-11-18 — Délégation à Claude ; analyse du risque ; D-008 ; test scellé v0.2 : échec.
- 2026-11-18 — Accord multi-jours + simulation ; D-009 ; collecte U20 ; T3 : échec.
