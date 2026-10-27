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
en moyenne du jour, avec des pas de 3 h jusqu'à 2 247 et 3 086 µg/m³. Le cycle
du jour est cohérent (accumulation nocturne, dilution l'après-midi) et les
jours voisins montent et descendent avec lui : c'est une valeur extrême du
modèle, pas un artefact.

## Décision

- PM2.5 et PM10 journaliers CAMS EAC4 aux 351 communes, 2005-2025, même
  recette qu'aux provinces : maille de 0,75° la plus proche, moyenne des huit
  pas du jour UTC, conversion en µg/m³, arrondi à 4 décimales, pas servis à
  zéro gardés. Stockage dense, une série par maille partagée par les communes
  qui s'y trouvent (ADR-0017). Méthode `reanalyse`, confiance B.
- Bornes hautes relevées à 2 000 µg/m³ (PM2.5) et 3 000 µg/m³ (PM10), pour
  toutes les séries du contrat : elles restent au-dessus des maxima servis aux
  398 localités, et le panache de Madjoari est gardé tel que servi. Les
  séries des provinces sont inchangées.
- Ingesteur `scripts/ingest_cams_eac4_journalier.py --lot communes`, qui
  relit le même cache annuel que le lot des provinces ; migration 0017.

## Conséquences

- 51 mailles pour 351 communes, à 33 km du point en médiane, 56 km au plus.
  702 séries, dont 102 porteuses ; 2 142 lignes annuelles et
  782 340 valeurs ; 2,1 Mo de fichiers.
- PM2.5 de 40,2 µg/m³ en moyenne sur les communes et sur 2005-2025, PM10 de
  52,8, proches des provinces (39,6 et 51,6). 1 % des pas de 3 h sont servis
  à zéro ; 5,7 % des jours en comptent au moins un.
- Avec la pluie journalière NASA POWER des communes (ADR-0017), le proxy de
  salissure et le PR réaliste corrigé de la salissure deviennent calculables
  aux 351 communes. Un jour de pluie sans valeur (le 2 décembre 2025 à
  Sidéradougou et Tiéfora, valeur écartée) y compte 0 mm, aucun nettoyage ce
  jour-là, et la réponse le signale.
- Près d'un foyer de feux, la valeur d'une maille de 0,75° dépend des
  émissions de feux estimées par satellite (GFAS) que la réanalyse injecte
  dans la maille : elle ne se compare pas à une mesure ponctuelle. Les notes
  publiques citent le panache de Madjoari.
