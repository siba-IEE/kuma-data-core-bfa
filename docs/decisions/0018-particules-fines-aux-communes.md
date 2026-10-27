# ADR-0018 : particules fines aux communes

Date : 2026-10-27. Statut : accepté.

## Contexte

L'ADR-0015 a ingéré le PM2.5 et le PM10 journaliers de la réanalyse CAMS
EAC4 aux 47 provinces, avec une borne haute de 1 000 µg/m³ (PM2.5) et
1 500 µg/m³ (PM10) placée au-dessus des maxima servis aux provinces. Le
jalon 4 étend la granularité journalière aux communes, dans le stockage dense
de l'ADR-0017. Aux communes, la réanalyse sert des valeurs plus fortes : le
13 novembre 2013, la maille de Madjoari, en bordure des parcs de l'Est, porte
un panache de feux de brousse de 1 143 µg/m³ de PM2.5 et 1 567 µg/m³ de PM10
en moyenne du jour, avec des pas de 3 h jusqu'à 2 247 et 3 086 µg/m³. C'est
une valeur extrême du modèle, pas un artefact : le cycle du jour est cohérent
(accumulation nocturne, 1 534 à 2 247 µg/m³ de 0 à 6 h UTC, dilution à 123 et
157 l'après-midi) ; les jours voisins montent et descendent avec lui (340 le
12, 402 le 14, 176 le 15) ; les mailles voisines portent le même panache (744
au nord, 458 à l'ouest, 433 à l'est) ; la même maille atteint 905 µg/m³ de
PM2.5 le 9 novembre 2014, et son PM10 dépasse 900 µg/m³ lors de six saisons de
feux (novembre 2007, 2009, 2011, 2013 et 2014, décembre 2025).

## Décision

- PM2.5 et PM10 journaliers CAMS EAC4 aux 351 communes, 2005-2025, même
  recette qu'aux provinces : maille de 0,75° la plus proche, moyenne des huit
  pas du jour UTC, conversion en µg/m³, arrondi à 4 décimales, pas servis à
  zéro gardés. Stockage dense, une série par maille partagée par les communes
  qui s'y trouvent (ADR-0017). Méthode `reanalyse`, confiance B.
- Bornes hautes relevées à 2 000 µg/m³ (PM2.5) et 3 000 µg/m³ (PM10), pour
  toutes les séries du contrat, en remplacement de celles de l'ADR-0015 : le
  panache de Madjoari est gardé tel que servi. Elles restent 1,55 et 1,7 fois
  au-dessus du maximum journalier de toute la grille servie (1 289 et
  1 773 µg/m³ le 21 décembre 2008, dans une maille qu'aucune localité
  n'utilise), et arrêtent toujours une erreur d'unité. Les séries des
  provinces sont inchangées.
- Un écart admis (ADR-0017) aurait écarté la valeur au lieu de la garder :
  il est réservé aux valeurs que la source sert à tort, pas aux extrêmes
  qu'elle modélise.
- Ingesteur `scripts/ingest_cams_eac4_journalier.py --lot communes`, qui
  relit le même cache annuel que le lot des provinces ; migration 0017.

## Conséquences

- 51 mailles pour 351 communes, à 33 km du point en médiane, 56 km au plus.
  702 séries, dont 102 porteuses ; 2 142 lignes annuelles et
  782 340 valeurs ; 2,2 Mo de fichiers. Les 94 séries des provinces sont
  identiques à celles de la commune de leur maille.
- Sur les 351 communes et sur 2005-2025 : PM2.5 de 39,3 µg/m³ en moyenne,
  PM10 de 51,2 (39,6 et 51,6 sur les 47 provinces) ; PM10 de 43,7 µg/m³ au
  sud de 10,5 °N, 63,2 au nord de 13,5 °N. 1 % des pas de 3 h sont servis à
  zéro ; 5,7 % des jours en comptent au moins un.
- Avec la pluie journalière NASA POWER des communes (ADR-0017), le proxy de
  salissure et le PR réaliste corrigé de la salissure deviennent calculables
  aux 351 communes : perte moyenne de 1,2 % au sud de 10,5 °N à 2,9 % au nord
  de 13,5 °N (4,7 % à Oursi et Tin-Akoff, jusqu'à 20 % en fin de saison
  sèche), 2,2 % à Ouagadougou comme au Kadiogo (ADR-0015). Un jour de pluie
  sans valeur (le 2 décembre 2025 à Sidéradougou et Tiéfora, valeur écartée)
  y compte 0 mm, aucun nettoyage ce jour-là, et la réponse le signale ; au-delà
  de dix jours sans valeur, la série est refusée.
- Près d'un foyer de feux, la valeur d'une maille de 0,75° dépend des
  émissions de feux estimées par satellite (GFAS) que la réanalyse injecte
  dans la maille : elle ne se compare pas à une mesure ponctuelle. Les notes
  publiques citent le panache de Madjoari.
