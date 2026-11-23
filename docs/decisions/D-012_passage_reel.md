# D-012 — Passage en réel (2026-11-23)

Décision de Maxime, contre la recommandation d'attendre : aucune stratégie n'a passé les critères pré-enregistrés
(T3 : Sharpe 0,49, perte max -58 % en backtest 2020–2026 ; +20 % sur les 12 derniers mois).

Règles du bot réel (src/okxbot/live/real.py, .github/workflows/live-trading.yml) :
- stratégie T3 (D-009) seule ; C1 non tradée en réel (elle exige une jambe spot) ;
- capital utilisé = min(valeur du compte, BOT_CAPITAL_USD) ; levier total ≤ 3x, ≤ 1x par actif ; levier de marge 3, marge croisée ;
- compte obligatoirement en mode de position « net » ; rééquilibrage une fois par jour (cycle de 00:37 UTC) par différence
  avec les positions lues chez OKX ; seuil 2 % ; réductions avant ouvertures ; identifiants d'ordre déterministes ;
- stops de protection chez OKX à 4 écarts-types journaliers, remplacés à chaque rééquilibrage ;
- coupe-circuit -25 % depuis le plus haut (plus d'ouvertures jusqu'à /resume) ; /pause /stop /resume /killswitch /status ;
- aucun ordre si LIVE_TRADING ≠ « oui » ; lancement manuel « verification » = rapport sans ordre ;
- hébergement GitHub Actions ; clé Lecture + Trading, sans retrait, sans IP (choix de Maxime, pas de serveur), stockée
  uniquement dans les secrets GitHub, rotation mensuelle ; sous-compte dédié recommandé ;
- Telegram : un message à chaque ouverture et fermeture de position ; exceptions : alertes graves (anomalie, coupe-circuit,
  kill switch) et réponses aux commandes.
