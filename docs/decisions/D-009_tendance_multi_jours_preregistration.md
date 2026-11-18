# D-009 — Stratégie T3 « tendance multi-jours » figée avant tout calcul (2026-11-18)

Accord de Maxime (2026-11-18, 15:54) : positions de plusieurs jours (plus seulement intraday), longues ET courtes
selon les circonstances ; construction du bot en mode simulation. Ce document est commité avant tout backtest de T3.

## Pourquoi cette famille

C'est l'approche la plus robuste documentée sur les cryptos (ensembles de canaux de Donchian, Zarattini, Pagani,
Barbon 2025) et nos vagues 1–2 montrent que les horizons longs résistent mieux aux frais.
Limite assumée : ce choix est éclairé par nos résultats passés ; l'historique n'est donc plus un juge parfaitement
neutre. Le vrai juge sera le paper trading.

## Règles (aucun paramètre optimisé)

- **Univers U20** : les 20 cryptos disponibles en X-Perps, avec un perpétuel OKX coté avant juillet 2023, classées par
  volume du 17/11/2026 : BTC, ETH, SOL, XRP, DOGE, PEPE, NEAR, UNI, SUI, AAVE, FIL, BNB, ADA, LINK, AVAX, BCH, LTC,
  ICP, ARB, OP. Biais du survivant reconnu (cryptos choisies avec le recul d'aujourd'hui). Un actif entre dans le
  portefeuille après 200 jours d'historique.
- **Bougies journalières** (clôture 00:00 UTC).
- **Signal par actif** : pour chaque durée L ∈ {10, 20, 40, 80, 160} jours, état +1 si la clôture dépasse le plus haut
  des L jours précédents, -1 si elle passe sous le plus bas, sinon état inchangé (stop-and-reverse). Score = moyenne
  des 5 états, entre -1 (vendeur) et +1 (acheteur).
- **Taille** : poids brut = score / volatilité (EWMA 30 jours), puis mise à l'échelle du portefeuille pour viser
  **30 % de volatilité annuelle** (covariance sur 90 jours). Plafonds : 1x le capital par actif, **3x au total**.
- **Exécution** : décision à la clôture journalière, ordre au marché juste après. On ne retouche une position que si
  le changement dépasse 2 % du capital ou si le sens s'inverse.
- **Coûts** : 0,05 % de frais + 3 pb de slippage par transaction ; funding réel signé (Binance ; à défaut 0,01 %/8 h
  payé par les positions longues et reçu par les courtes). Test de résistance : coûts x2.

## Évaluation

Toute la période disponible (début 2020 → 16/11/2026), sans optimisation, avec détail par année et sur les 12 derniers mois.
Variantes calculées À TITRE D'INFORMATION seulement (non sélectionnables) : acheteur seul, volatilité visée 20 % et 40 %.

Critères pour passer en paper trading :
- Sharpe ≥ 0,8 sur toute la période ; Sharpe ≥ 0,5 avec coûts x2 ;
- au moins 4 années civiles complètes positives sur 6 (2020–2025) ;
- 12 derniers mois positifs ;
- baisse maximale ≤ 35 %.

Un premier calcul sur les 5 actifs déjà disponibles (BTC, ETH, SOL, XRP, DOGE) est fait en attendant les données
des 20 ; seul le calcul sur U20 décide.
