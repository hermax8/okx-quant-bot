# Tâche 1 — Recherche des stratégies (2026-11-17)

Version éditable et complète (avec tous les liens) : https://claude.ai/artifact/6ERu3WYAom3QTnnG7fPgnh
Sources : voir `docs/sources.md`. Aucun backtest n'a été réalisé à ce stade : les résultats chiffrés
cités sont ceux des auteurs des études, pas les nôtres.

## 1. Résumé

Piste la plus prometteuse : **suivi de tendance intraday sélectif (15 min–1 h, filtré par la tendance 4 h),
long et short, sur BTC et ETH, via les X-Perps d'OKX Europe en levier x1.**

- Depuis la France, on passe par OKX Europe (MiCA). Dérivés = X-Perps : futures à échéance 5 ans,
  funding horaire, levier max 10x, frais 0,02 % maker / 0,05 % taker. Lancés le 15/04/2026 (licence MiFID, Malte).
- Les frais éliminent le scalping : ~0,10 % l'aller-retour en taker + slippage. Viser 0,6 à 2 % par trade,
  positions de 30 min à quelques heures.
- Base académique solide : momentum intraday Bitcoin, suivi de tendance (robuste en multi-jours, plus fragile
  en intraday), saisonnalité horaire de la volatilité, effet des annonces macro. Le ML seul est modeste et
  échoue souvent après frais.
- Hors de portée : scalping 1–5 min, carnet d'ordres / flux d'ordres (avantage de quelques secondes).

Points bloquants : accès aux données (workspace sans accès OKX → GitHub Actions), historique X-Perps court
(→ approximation par perpétuels globaux + spot depuis 2020), compte X-Perps à ouvrir (sinon spot long uniquement).

## 2. Marché choisi

| Option | Frais maker / taker | Short | Coût de portage | Verdict |
|---|---|---|---|---|
| X-Perps (OKX Europe) | 0,02 % / 0,05 % | Oui | Funding horaire | **Retenu** |
| Spot, avec compte X-Perps | 0,08 % / 0,10 % | Non | Aucun | Repli |
| Spot, sans compte dérivés | 0,10/0,20 % ou 0,20/0,35 % selon la source | Non | Aucun | Écarté |
| Marge spot (BTC/USDC, ETH/USDC) | Spot + intérêts | Oui | Intérêts | Moins intéressant |

API EEA : site my.okx.com, hôte API eea.okx.com pour compte/ordres ; données publiques X-Perps aussi sur l'hôte global.
Frais réels à lire via `/api/v5/account/trade-fee`. Actifs : BTC, ETH en priorité ; SOL, XRP, DOGE secondaires.
Liste exacte des ~85 X-Perps à vérifier.

## 3. Caractéristiques du marché

Relevé réel API OKX global, 17/11/2026 21:55 UTC (une seule photo) :

| Contrat | Volume 24 h (M$) | Écart (pb) | Amplitude 24 h (%) |
|---|---|---|---|
| BTC-USDT-SWAP | 7 355 | 0,02 | 3,4 |
| ETH-USDT-SWAP | 6 489 | 0,06 | 5,2 |
| ZEC-USDT-SWAP | 1 164 | 0,11 | 6,8 |
| SOL-USDT-SWAP | 909 | 1,36 | 4,6 |
| XRP-USDT-SWAP | 237 | 1,03 | 3,5 |
| HYPE-USDT-SWAP | 232 | 0,15 | 5,5 |
| DOGE-USDT-SWAP | 168 | 1,69 | 4,2 |
| PEPE-USDT-SWAP | 149 | 0,26 | 8,9 |

547 contrats ; top 10 = 81 % du volume ; BTC+ETH = 55 %. Contrats sur actions exclus.

- Frais/slippage : écart négligeable sur BTC/ETH ; coût dominant = taker 0,05 %/côté. Slippage modélisé pessimiste.
- Profondeur : à mesurer (Tardis.dev gratuit le 1er de chaque mois).
- Heures : volatilité max ~16 h UTC, min ~5 h UTC (Hansen et al.) ; tendances BTC plus fortes du dimanche soir
  au lundi soir UTC (Concretum), surtout depuis mi-2020.
- Macro : volatilité, volumes, écarts montent autour de FOMC, CPI, NFP depuis 2020 → filtre d'événements.
- Actifs : altcoins plus volatils, écarts 10–50x plus larges, très corrélés au BTC → gestion des positions corrélées.

## 4. Stratégies étudiées

| Famille | Recherche | Avantages | Inconvénients | Potentiel |
|---|---|---|---|---|
| Tendance / breakout (Donchian, cassure ATR) | Zarattini et al. 2025 : Sharpe > 1,5 net, alpha 10,8 %/an vs BTC (journalier). Concretum intraday : Sharpe brut ~1,6. Tendances courtes affaiblies récemment | Long et short, peu de trades, gros gains rares | Réussite < 45 %, pertes en range | **Élevé** |
| Momentum intraday | Shen, Urquhart, Wang 2022 : début de « journée » prédit la dernière demi-heure, plus fort avec volume/volatilité. Caporale & Plastun : momentum les jours anormaux | Base académique, combinable | Effets faibles, érosion | Moyen à élevé (filtre) |
| Saisonnalité horaire | Hansen et al. : cycles horaires/hebdo nets | Simple | Pas une stratégie seule ; surapprentissage | Moyen (filtre) |
| Retour à la moyenne | arXiv 2608.21888 : reversal court terme surtout après flux agressif ; coût de capture élevé | Réussite élevée en latéral | Pertes lourdes si tendance | Moyen (régime latéral) |
| Pairs ETH/BTC | Fil & Kristoufek 2020 : 11,61 %/mois en 5 min vs -0,07 % en journalier, très sensible aux coûts | Neutre au marché | Frais doublés, relations instables | Moyen (1 h) |
| Funding / positionnement | Contrarien à horizon semaines (K33) | Donnée gratuite | Horizon trop long | Faible à moyen (filtre) |
| Machine learning | Bysik & Ślepaczuk 2026 : signaux naïfs perdants à 0,10 % ; filtre coût-aware utile. AUC ~0,61 (Sobreiro et al.) | Idéal pour noter des signaux | Surapprentissage, dérive | Moyen (scoring) |
| Scalping 1–5 min | Frais > gains visés | — | Incompatible | **Écarté** |
| Carnet / flux d'ordres | Prédictif mais décroît en secondes ; adverse selection des ordres maker | — | Latence | **Écarté** |
| Grid / martingale | — | Régulier en range | Ruine en tendance, viole la règle de risque | **Écarté** |

Filtres moins connus : squeeze de volatilité, effet « quart d'heure » (arXiv 2607.09426), régimes HMM.

## 5. Classement à tester

| Rang | Stratégie | Régime | Unités de temps | Rôle |
|---|---|---|---|---|
| 1 | Breakout/tendance (Donchian + ATR), filtre 4 h, long/short | Haussier, baissier | 15 min, 1 h (+4 h) | Moteur principal |
| 2 | Momentum intraday conditionné heure/volume | Haussier, baissier | 15 min, 1 h | Moteur ou filtre |
| 3 | Squeeze puis expansion de volatilité | Forte volatilité | 15 min, 1 h | Moteur |
| 4 | Retour à la moyenne VWAP/Bollinger, seulement en latéral | Latéral | 5, 15 min | Moteur |
| 5 | Pairs ETH/BTC | Neutre | 1 h | Diversification |
| 6 | Meta-labeling LightGBM | — | — | Score /100 |
| 7 | Filtres : régime (ADX, choppiness, vol percentile, HMM), funding, macro, liquidité | — | — | Autoriser/bloquer |

Une stratégie qui échoue aux critères est abandonnée, pas ajustée jusqu'à ce qu'elle passe.

## 6. Sources de données

| Donnée | Source | Période |
|---|---|---|
| Bougies 1 min spot + perp USDT | OKX `/api/v5/market/history-candles` | 2020 → |
| Bougies X-Perps | même API | avr. 2026 → |
| Funding | `/api/v5/public/funding-rate-history` | max possible |
| Mark / index | `history-mark-price-candles`, `history-index-candles` | idem |
| Trades | `/api/v5/market/history-trades` | échantillons |
| Carnets complets | Tardis.dev (1er du mois gratuit) | 2021 → |
| Contrôle croisé | data.binance.vision | 2020 → |
| Calendrier macro | Fed (FOMC), BLS (CPI, emploi) | 2020 → 2027 |

Collecte via GitHub Actions (le workspace ne joint pas OKX). 6 ans de 1 min ≈ 3,2 M bougies ≈ 10 000–32 000 requêtes
par actif (~1 h de job). Pas de TradingView. Alternative : script à lancer sur l'ordinateur de Maxime.

## 7. Outils Python

pandas/polars/pyarrow ; python-okx ou ccxt (vérifier support eea.okx.com + X-Perps) ; vectorbt (recherche) ;
moteur événementiel maison ou NautilusTrader (validation, même code backtest/réel) ; numpy, scipy, statsmodels, arch ;
hmmlearn ; scikit-learn, LightGBM ; matplotlib, plotly ; pytest. Freqtrade écarté comme moteur principal.

## 8. Plan de backtesting

Découpage : développement 2020–2023 ; validation janv. 2024–oct. 2025 ; **test final scellé nov. 2025–nov. 2026**
(une seule exécution, strat figée).

Réalisme : signal sur bougie clôturée, exécution à l'ouverture suivante (+1 bougie en sensibilité) ; taker 0,05 %/côté ;
slippage demi-écart + impact (calibré Tardis), stress coûts x2 ; stops au pire cas, gaps ; funding historique ;
exécutions partielles et filtre de liquidité ; tailles minimales OKX pour 1 000 €.

Anti-surapprentissage : walk-forward 12 mois / 3 mois ; 3–5 paramètres max, journal de tous les essais ;
Deflated Sharpe ; PBO (CSCV) ; plateau à ±20 % ; Monte-Carlo et bootstrap ; entrées aléatoires et buy & hold
à vol égale ; résultats par régime, actif, année ; tests anti-look-ahead automatisés ; CV purgée avec embargo.

Score /100 : déciles de score vs gain moyen hors échantillon, doit être monotone.

## 9. Critères de sélection (proposés, à valider avant la Tâche 2)

| Critère | Seuil |
|---|---|
| Sharpe annualisé (journalier) | ≥ 1,0 |
| Deflated Sharpe | ≥ 95 % |
| PBO | ≤ 0,30 |
| Profit factor | ≥ 1,3 |
| Drawdown max (0,5–1 % de risque/trade) | ≤ 15 % (borne pessimiste Monte-Carlo) |
| Trades hors échantillon | ≥ 150 |
| Fenêtres WF gagnantes | ≥ 60 % |
| Coûts doublés | reste rentable |
| Concentration | aucune année/aucun actif > 50 % du profit |
| Stabilité | rentable à ±20 % |
| Comparaison | bat aléatoire et buy & hold à vol égale |

Si aucune stratégie ne passe : ne pas déployer.

## 10. Problèmes et prochaines étapes

Voir `PROJECT_STATUS.md`.
