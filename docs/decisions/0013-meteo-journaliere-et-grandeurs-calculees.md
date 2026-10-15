# ADR-0013 : météo journalière NASA POWER et grandeurs calculées

Date : 2026-10-15. Statut : accepté.

## Contexte

Les grandeurs métier du moteur, calculées à la volée par `/v1/grandeurs/*`,
lisent des séries journalières et cherchent des séries compagnes de même
localité et de même source. Au Burkina Faso, seul le productible à PR fourni
sans correction donnait un résultat juste :

- la température, l'humidité et la pluie manquaient ;
- la recherche des compagnes exigeait le même début de période, alors que le
  GHI journalier commence en 1991 et le DNI et le DHI en 2001 ;
- le P50/P90 pouvait lire la série journalière au lieu de la mensuelle et
  mêlait 35 années sous l'étiquette 1991-2020 ;
- le repli du POA, sans DNI ni DHI, appliquait une corrélation horaire à des
  totaux journaliers et traitait tout le rayonnement comme diffus.

## Décision

- Météo journalière NASA POWER aux 47 provinces, 1991-2025, même début que le
  GHI journalier : `t2m` (moyenne du jour, °C), `rh2m` (%) et `precipitation`
  (paramètre `PRECTOTCORR`, mm/jour). NASA POWER les tire de la réanalyse
  MERRA-2 (maille de 0,5° × 0,625°) : méthode `reanalyse`, confiance B.
  Bornes de plausibilité : 0 à 50 °C, 0 à 100 %, 0 à 500 mm ; les contrats
  gagnent une borne basse incluse, sans laquelle une valeur doit rester
  strictement positive (rayonnement). Ingesteur
  `scripts/ingest_nasa_power_journalier.py --famille meteo`, migration 0010
  (`COPY`, trigger d'audit des mesures suspendu).
- Correctifs du moteur :
  - séries compagnes : recouvrement des périodes au lieu de l'égalité des
    débuts, la compagne de même début passant en premier, puis celle qui
    recouvre le plus la source. Un GHI 1991-2025 trouve son DNI 2001-2025 ;
    les jours sans compagne restent traités par l'appelant (repli du POA,
    intersection des dates ailleurs) ;
  - P50/P90 : série mensuelle seulement, lecture bornée à 1991-2020, années
    complètes seulement, textes rendus génériques (maille NASA POWER partagée
    par les localités voisines) ;
  - repli du POA : le total du jour est décomposé par la corrélation
    journalière d'Erbs et al. (1982), indice de clarté `KT = H / H0`, puis le
    direct est ramené au midi solaire.
- Tests d'intégration de chaque grandeur sur une province (Kadiogo).

## Conséquences

- 141 séries et 1 802 544 mesures, 8,7 Mo de CSV ; la migration 0010 dure
  2 min 40 environ. 36 séries distinctes par grandeur pour 47 provinces
  (maille MERRA-2).
- Climat des provinces : température moyenne de 24 °C en décembre et janvier à
  32,5 °C en avril ; humidité de 18 % en février à 81 % en août ; 840 mm de
  pluie par an en moyenne, de 310 à 1 717 mm selon la province et l'année.
- Une valeur suspecte : 321,8 mm le 2 décembre 2025 dans la Comoé et la
  Léraba (même maille), en saison sèche, au-dessus du record connu au Burkina
  Faso (263 mm à Ouagadougou le 1er septembre 2009) ; de 1991 à 2024, aucun
  jour de décembre ne dépasse 7,5 mm. Elle est gravée telle que la source la
  sert et signalée dans la note publique de ces deux provinces ; le contrôle
  qualité tranchera.
- La pluie n'est pas homogène dans le temps : sur l'ensemble des provinces,
  52 jours par an dépassent 50 mm à partir de 2015, contre 2,7 de 1991 à 2014,
  et le nombre de jours de pluie tombe de 148 à 124 par an. Avant 2015, les
  extrêmes sont lissés (27,5 mm au Kadiogo pour l'épisode de 263 mm de 2009).
  Ces séries ne servent pas à l'étude des extrêmes ni des tendances ; la note
  publique de chaque série de pluie le dit.
- Grandeurs désormais calculables aux provinces : POA paramétrable et
  bifacial, productible avec correction thermique, PR fourni corrigé de la
  température, énergie utile ECS, degrés-jours de climatisation, PR réaliste
  corrigé de la température ; P50/P90 aux 398 localités. Au Kadiogo en 2024 :
  GHI de 5,78 kWh/m²/jour, POA de 6,46 sur un plan incliné de 15° plein sud ;
  P50 de 2 140 et P90 de 2 096 kWh/m²/an sur 1991-2020.
- Le POA journalier applique le modèle de Perez au midi solaire sur des
  totaux du jour. Au Kadiogo en 2024, il dépasse le GHI de 6 % sur un plan
  horizontal et surestime d'environ 8 % le plan à 15° plein sud face à un
  calcul horaire fermé (5,98 à 6,00 kWh/m²/jour au lieu de 6,46). Le repli,
  lui, conserve le GHI sur un plan horizontal : une série 1991-2025 change
  donc de méthode le 1er janvier 2001, et le rapport POA/GHI y saute de 9 %
  (plan horizontal) à 12 % (15° plein sud). Ne pas moyenner un POA à cheval
  sur 2001 ; le mode horaire lève ces biais.
- Les autres méthodes journalières du moteur gardent leurs limites : le
  productible avec correction thermique, calculé sur l'éclairement moyen des
  24 heures, ne perd que 3,6 % par la température au lieu de 10 % en horaire
  (productible surestimé d'environ 7 %) ; les degrés-jours de climatisation
  sont 25 % sous le calcul horaire en base 26 °C ; le PR réaliste ne couvre
  que 2000-2025, fenêtre fixée par le code.
- La salissure et le PR réaliste corrigé de la salissure attendent les
  particules fines CAMS EAC4.
