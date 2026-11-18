# D-007 — Version candidate v0.1 figée avant validation (2026-11-18)

Choix de Maxime (2026-11-18, 15:00) : la combinaison S1b + S2b.
Ce document est commité AVANT tout calcul sur la période de validation, pour qu'on ne puisse pas
ajuster quoi que ce soit après avoir vu les résultats.

## Composition

- Stratégies : `s1b_breakout` et `s2b_momentum` (src/okxbot/strategies/second_wave.py), mêmes grilles que la vague 2
  (16 et 36 configurations).
- Actifs : BTC, ETH, SOL, XRP, DOGE (perpétuels OKX globaux comme approximation des X-Perps).
- Sélection des paramètres : la procédure testée en vague 2, inchangée. Tous les 3 mois, pour chaque stratégie,
  choix de la config au meilleur Sharpe sur les 12 mois précédents (une config pour tous les actifs, ≥ 10 trades).
- Risque : 0,5 % du capital par trade.
- **Ajout au niveau du portefeuille (décidé maintenant)** : exposition notionnelle totale plafonnée à 1x le capital.
  Si une nouvelle position ferait dépasser ce plafond, elle est réduite à la place restante (ignorée si < 1 % du capital).
- Coûts : taker 0,05 %, maker 0,02 % (entrées limites), slippage 1 pb / 3 pb (stops), funding 0,01 %/8 h toujours payé.
  Test de résistance avec coûts doublés.

## Période de validation

Tests trimestriels de **janvier 2024 à octobre 2025** (8 trimestres, le dernier limité à octobre).
Les données à partir du 1er novembre 2025 restent scellées (test final).

## Critères (D-003, inchangés)

Sharpe ≥ 1,0 ; profit factor ≥ 1,3 ; DD max ≤ 15 % ; rentable avec coûts doublés ; ≥ 60 % de trimestres positifs ;
aucun actif ni aucune année > 50 % du profit ; Deflated Sharpe ≥ 95 % avec tous les essais cumulés.
Nombre de trades : avec 22 mois, le seuil de 150 trades s'applique au total.

## Règle de décision

- Si les critères passent : on passe à la Tâche 3 (règles finales, scoring, gestion du risque) sur cette base.
- S'ils échouent : on le dit, on n'ajuste pas les paramètres pour faire passer la validation. Les pistes suivantes
  seront testées comme de nouveaux essais, et la validation ne servira plus de juge neutre.
