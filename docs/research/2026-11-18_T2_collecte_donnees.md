# Tâche 2 — Première collecte de données (2026-11-18)

Collecte GitHub Actions terminée le 2026-11-18 à 00:32 UTC. Données sur la branche `data`,
rapports bruts dans `reports/collect/` de cette branche.

## Bougies (API publique OKX, marché global)

| Instrument | Pas | Bougies | Début | Couverture | Trous | OHLC incohérents | Bougies à volume nul | Variations > 10 % sur une bougie |
|---|---|---|---|---|---|---|---|---|
| BTC-USDT-SWAP | 1 min | 3 618 629 | 2020-01-01 | 100 % | 0 | 0 | 7 702 (0,2 %) | 0 |
| ETH-USDT-SWAP | 1 min | 3 618 629 | 2020-01-01 | 100 % | 0 | 0 | 15 998 (0,4 %) | 1 |
| SOL-USDT-SWAP | 5 min | 612 187 | 2021-01-22 | 100 % | 0 | 0 | 279 | 23 |
| XRP-USDT-SWAP | 5 min | 723 726 | 2020-01-01 | 100 % | 0 | 0 | 2 953 | 31 |
| DOGE-USDT-SWAP | 5 min | 668 682 | 2020-07-10 | 100 % | 0 | 0 | 1 109 | 62 |
| BTC-USDT (spot) | 5 min | 723 730 | 2020-01-01 | 100 % | 0 | 0 | 332 | 5 |
| ETH-USDT (spot) | 5 min | 723 734 | 2020-01-01 | 100 % | 0 | 0 | 334 | 8 |

Remarques :
- Aucun trou : OKX semble combler lui-même les minutes sans échange (bougies plates à volume nul,
  par exemple pendant les maintenances). À filtrer dans les backtests (pas de signal sur une bougie à volume nul).
- SOL et DOGE ont un historique plus court (cotation des perpétuels plus tardive).
- Les grosses variations sur une bougie (jusqu'à 62 % sur DOGE en 5 min) correspondent à des épisodes réels
  extrêmes (2021) : à vérifier une par une avant les backtests sur altcoins.

## Funding

- API OKX : seulement les 3 derniers mois (depuis le 2026-08-17), règlement toutes les 8 h.
  Le workflow l'accumule désormais chaque semaine.
- Ajouté : funding Binance depuis 2020 (data.binance.vision) comme approximation de l'historique ancien.

## X-Perps (instruments OKX Europe)

262 X-Perps actifs. Identifiants des actifs visés (échéance 04/04/2031, règlement en USD) :

| X-Perp | Valeur d'un contrat | Taille minimale | Pas de prix | Levier max |
|---|---|---|---|---|
| BTC-USD_UM_XPERP-310404 | 0,0001 BTC | 1 contrat | 0,1 | 50x |
| ETH-USD_UM_XPERP-310404 | 0,001 ETH | 1 contrat | 0,01 | 50x |
| SOL-USD_UM_XPERP-310404 | 0,01 SOL | 1 contrat | 0,01 | 50x |
| XRP-USD_UM_XPERP-310404 | 1 XRP | 1 contrat | 0,0001 | 20x |
| DOGE-USD_UM_XPERP-310404 | 10 DOGE | 1 contrat | 0,00001 | 20x |

Le BTC X-Perp est coté depuis le 30/03/2026. Taille minimale de l'ordre de 10 $ pour BTC (au cours du jour) :
compatible avec 1 000 € et 0,5–1 % de risque par trade.
Les listes d'instruments EEA et globales sont identiques via l'API publique.

## Suite

Ajout au workflow : bougies 1 min des X-Perps BTC et ETH depuis mars 2026 (comparaison avec les perpétuels globaux),
funding X-Perps, funding Binance.
