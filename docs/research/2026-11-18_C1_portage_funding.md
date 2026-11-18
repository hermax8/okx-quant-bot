# C1 — Portage du funding (2026-11-18) : ÉCHEC de justesse

**Règles figées avant calcul (D-010). Sur 2020 → octobre 2026 : CAGR +7,5 %, Sharpe 5,8, baisse max -1,0 %,
toutes les années 2021–2025 positives. Mais 0,00 % sur les 12 derniers mois (aucune position ouverte :
le funding est resté sous le seuil d'entrée), donc le critère « 12 derniers mois positifs » n'est pas atteint.**

Script : `research/experiments/c1_carry.py`. Résultats : `reports/c1_carry/`.

| Année | Funding encaissé | Coûts | **Net** | Net coûts x2 |
|---|---|---|---|---|
| 2020 | 16,5 % | 2,5 % | **+15,0 %** | +12,2 % |
| 2021 | 33,5 % | 6,1 % | **+31,4 %** | +23,6 % |
| 2022 | 1,7 % | 1,7 % | **+0,05 %** | -1,6 % |
| 2023 | 5,0 % | 2,4 % | **+2,7 %** | +0,3 % |
| 2024 | 9,5 % | 4,1 % | **+5,5 %** | +1,3 % |
| 2025 | 0,9 % | 0,7 % | **+0,2 %** | -0,5 % |
| 2026 (à oct.) | 0 % | 0 % | **0,0 %** | 0,0 % |

Capital investi en moyenne : 0,37x (le reste en cash faute d'opportunités). Actifs les plus souvent portés :
XRP, FIL, AAVE, LINK, BCH, ETH.

## Lecture

- **Très sûr, mais l'opportunité a quasiment disparu** : le funding élevé n'existe que dans les marchés très haussiers
  (2020–2021, début 2024). Depuis 2025, il ne couvre plus les frais.
- **Les vrais X-Perps paient encore moins sur BTC** : depuis août 2026, funding BTC X-Perp ≈ 1,5 %/an contre 5,9 %
  chez Binance ; ETH ≈ 6,7 %/an contre 4,7 %.
- La stratégie a le bon réflexe (rester en cash quand rien ne paie), mais elle ne rapporte rien aujourd'hui.
  Elle reste utile comme stratégie « dormante » qui se réveille dans les phases d'euphorie.
