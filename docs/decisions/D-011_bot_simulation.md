# D-011 — Bot en mode simulation (2026-11-18)

Accord de Maxime (2026-11-18, 16:40). Aucune stratégie n'a passé ses critères ; le bot tourne donc en
**observation**, sans argent réel, pour récolter des résultats en temps réel (le seul juge neutre restant).

- Poches : T3 tendance multi-jours (D-009, positive sur les 12 derniers mois mais en échec global) et C1 portage
  (D-010, dormante tant que le funding est faible). 500 € fictifs chacune.
- Exécution simulée au dernier prix des X-Perps, frais T3 0,08 %, coûts C1 0,24 % par côté, funding réel des X-Perps.
- Fréquence : toutes les 4 h via GitHub Actions (≈ 300 min/mois). Suffisant pour des stratégies journalières et
  hebdomadaires ; pour du réel, un serveur dédié serait nécessaire (stops côté OKX, réactivité).
- Garde-fous codés hors stratégie : modes actif / stop / pause, kill switch Telegram, coupe-circuit à -25 %,
  seul le chat Telegram autorisé est obéi.
- Bilan prévu : point hebdomadaire automatique ; revue complète après 3 mois de simulation (février 2027).
  Le passage au réel reste une décision explicite de Maxime.
