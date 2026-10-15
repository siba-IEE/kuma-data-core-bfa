# ADR-0010 : séries journalières NASA POWER

Date : 2026-10-15. Statut : accepté.

## Contexte

Les grandeurs journalières du moteur (variabilité, contrôle qualité,
productible au pas du jour) lisent la table `mesures_ressource`, que le lot
mensuel (ADR-0009) ne remplit pas. NASA POWER sert le journalier sur toute sa
période ; PVGIS ne sert SARAH-3 et ERA5 qu'au pas mensuel ou horaire, et CAMS
fera l'objet de son propre lot.

Une requête NASA POWER par point rend les trois grandeurs en moins de 2 s,
pour environ 60 Ko compressés par grandeur. Aux 398 localités des lots
mensuels, cela ferait plus de 12 millions de mesures et 70 Mo de CSV, pour des
séries que la maille de 1° de NASA POWER rend en grande partie identiques
(33 mailles pour 351 communes).

## Décision

- Points : les 47 provinces (lot `provinces`), soit 24 des 33 mailles NASA
  POWER couvertes par les communes.
- Contrats : mêmes grandeurs et mêmes périodes que le mensuel NASA POWER, GHI
  1991-2025, DNI et DHI 2001-2025. Valeur : total du jour en kWh/m²/jour, sans
  conversion. `modele_satellitaire`, confiance B (règle R4), statut `brut`,
  `granularite = 'journalier'`, source `nasa_power` (id 1). Codes
  `nasa_power_<grandeur>_journalier_<localité>`.
- Stockage : un CSV gzip par grandeur
  (`nasa_power_<grandeur>_journalier_provinces.csv.gz`), colonnes
  `localite_code, latitude, longitude, date, valeur`, même écriture
  déterministe et même validation que le mensuel, complétude vérifiée sur tous
  les jours civils. Ingesteur `scripts/ingest_nasa_power_journalier.py`, une
  requête par point. Ces fichiers dépassent 1 Mo : le hook de taille de
  `.pre-commit-config.yaml` exclut les seeds de `seeds/donnees/`.
- Bornes de plausibilité journalières : 9 kWh/m²/jour pour le GHI, 11 pour le
  DNI, 6,5 pour le DHI, au-dessus des maxima servis (8,39, 9,29 et 5,14).
- Migration 0007 : `COPY` dans `mesures_ressource`, trigger d'audit des
  mesures suspendu le temps du déversement (`docs/architecture/03-audit.md`,
  migrations de masse).

## Conséquences

- 141 séries et 1 459 162 mesures, 8,5 Mo de CSV. La migration 0007 dure
  1 min 45 environ en local, l'essentiel dans la contrainte d'exclusion de la
  table ; la table occupe 360 Mo.
- La moyenne des jours de chaque mois redonne la série mensuelle à l'arrondi
  près (écart maximal 0,00017 kWh/m²/jour). Aucun jour où le DHI dépasse le
  GHI.
- Les constats du mensuel valent ici : 24 séries distinctes par grandeur pour
  47 provinces (maille de 1°), GHI issu de deux produits (SRB avant 2001,
  CERES ensuite).
- GHI, DNI et DHI ne ferment pas : GHI - DHI dépasse le DNI pour 24 % des
  jours, jusqu'à 1,42 kWh/m²/jour. La proportion monte avec la couverture
  nuageuse ou la charge en poussières : au moins 90 % des jours dont le DNI
  est sous 2, aucun au-dessus de 5. Aucune grandeur ne doit donc être
  recalculée à partir des deux autres. Constat vérifié à la source ; la note
  publique des séries le rappelle avec la maille de 1°.
- Le journalier des communes reste possible au même format si un besoin le
  justifie.
