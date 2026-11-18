# D-010 — Stratégie C1 « portage du funding » figée avant calcul (2026-11-18)

Accord de Maxime (2026-11-18, 16:40). Commité avant tout backtest de C1.

## Principe

Acheter une crypto au comptant (spot) et vendre en même temps le même montant en X-Perp. Le prix n'a presque plus
d'effet ; on encaisse le funding versé par les acheteurs de perpétuels quand il est positif.

## Règles

- **Univers** : U20 (D-009). Jambe longue en spot OKX, jambe courte en X-Perp.
- **Taille** : notionnel total de **0,75x le capital** (jambe X-Perp à levier 3 : spot payé comptant + marge d'un tiers).
  Sans emprunt : dépasser 1x exigerait d'emprunter, ce qui coûterait plus que le funding.
- **Sélection hebdomadaire** (lundi 00:00 UTC) : score = funding moyen par jour sur les 14 derniers jours.
  Entrée : les 5 meilleurs scores ≥ 0,03 %/jour (≈ 11 %/an). Un actif détenu est conservé tant que son score reste ≥ 0
  et qu'il est dans les 8 premiers. Chaque position = 0,15x le capital (cases vides = cash non rémunéré).
- **Coûts par entrée ou sortie, par unité de notionnel** : spot 0,10 % + X-Perp 0,05 % + slippage 3 pb x 2 jambes
  + écart spot/perp 3 pb = 0,24 % (aller-retour 0,48 %). Rééquilibrage de marge quand le prix d'un actif a varié de plus
  de 25 % depuis le dernier rééquilibrage : 0,24 % du notionnel concerné.
- **Funding** : historique Binance (approximation, 2020–2026). Contrôle sur le vrai funding des X-Perps là où il existe
  (BTC, ETH depuis août 2026), à titre d'information.

## Critères pour passer en paper trading

- Chaque année civile complète 2021–2025 positive après coûts ;
- Sharpe ≥ 1,5 ; baisse maximale ≤ 10 % ;
- 12 derniers mois positifs.

## Limite connue

Le funding des X-Perps (marché européen séparé) est très différent de celui de Binance et de l'OKX global sur
la période commune (BTC : 0,005 %/jour contre 0,016 % ; corrélation quasi nulle). Le backtest sur l'historique
Binance surestime donc peut-être le rendement réel. Le paper trading sur les vrais X-Perps tranchera.
