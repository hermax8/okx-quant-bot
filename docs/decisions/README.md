# Journal des décisions

| ID | Date | Décision | Statut |
|---|---|---|---|
| D-001 | 2026-11-17 | Marché : OKX Europe, X-Perps levier x1 (long+short), BTC/ETH prioritaires ; repli spot si pas de compte X-Perps | Validée (2026-11-17) |
| D-002 | 2026-11-17 | Classement des stratégies à tester (voir rapport T1 §5) ; scalping, carnet d'ordres, grid/martingale écartés | Validée (2026-11-17) |
| D-003 | 2026-11-17 | Critères de sélection (rapport T1 §9), figés avant tout backtest | Validée (2026-11-17) |
| D-004 | 2026-11-17 | Données : API OKX via GitHub Actions ; découpage dev 2020–2023 / validation 2024–oct. 2025 / test scellé nov. 2025–nov. 2026 | Validée (2026-11-17) |

Statuts : Proposée → Validée (par Maxime) → Remplacée.
| D-005 | 2026-11-18 | Abandon de S3 (squeeze) et S4 (retour à la moyenne 15 min) après la vague 1 | Validée (2026-11-18) |
| D-006 | 2026-11-18 | Vague 2 limitée à S1 et S2 : horizon plus long, entrées maker, combinaison, extension aux altcoins | Validée (2026-11-18) |
| D-007 | 2026-11-18 | Version candidate v0.1 (S1b + S2b, 5 actifs, plafond 1x) figée avant validation — voir D-007_candidate_v0.1_preregistration.md | Validée (2026-11-18) |
| D-008 | 2026-11-18 | v0.2 : S2b seule, 1 % de risque/trade, levier de compte max 3x, coûts X-Perps, funding réel ; critères du test scellé — voir D-008_v0.2_preregistration_test_scelle.md | Validée (2026-11-18) |
| D-009 | 2026-11-18 | Stratégie T3 tendance multi-jours long/short sur 20 cryptos, règles et critères figés avant calcul — voir D-009_tendance_multi_jours_preregistration.md | Validée (2026-11-18) |
| D-010 | 2026-11-18 | Stratégie C1 portage du funding (spot long + X-Perp court), règles et critères figés avant calcul — voir D-010_portage_funding_preregistration.md | Validée (2026-11-18) |
| D-011 | 2026-11-18 | Bot en simulation (T3 + C1 en observation, 1 000 € fictifs, GitHub Actions toutes les 4 h, Telegram) — voir D-011_bot_simulation.md | Validée (2026-11-18) |
| D-012 | 2026-11-23 | Passage en réel décidé par Maxime : T3 seule (C1 exclue, jambe spot non gérée), capital plafonné par BOT_CAPITAL_USD, levier total ≤ 3x, stops chez OKX à 4σ, coupe-circuit -25 %, GitHub Actions avec clé sans IP ni retrait, Telegram limité aux ouvertures/fermetures et alertes graves — voir D-012_passage_reel.md | Validée (2026-11-23) |
