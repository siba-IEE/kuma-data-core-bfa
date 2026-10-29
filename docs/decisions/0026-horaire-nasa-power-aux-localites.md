# ADR-0026 : horaire NASA POWER aux 398 localités, une série par maille

Date : 2026-10-29. Statut : accepté.

## Contexte

L'horaire stocké et contrôlé ne couvrait que les cinq points pilotes
(ADR-0014, ADR-0023). Ailleurs, `/v1/horaire` relayait NASA POWER sans
contrôle qualité, l'édition figée ne servait rien, et les grandeurs en
intégration horaire (POA, bifacial, productibles, énergie ECS, degrés-jours)
n'avaient pas de séries compagnes.

NASA POWER sert la même série horaire à toutes les localités d'une maille :
CERES SYN1deg de 1° pour le rayonnement, MERRA-2 de 0,5° × 0,625° pour la
température. Une série par localité ferait, sur 2021-2025, 68,9 millions de
lignes de plus dans `mesures_ressource_horaires`, dont chaque ligne porte un
statut, un commentaire et trois index.

## Décision

- **Périmètre :** GHI, DNI, DHI et température à 2 m horaires NASA POWER,
  2021-2025, aux 398 localités, comme aux pilotes (heure UTC commençant à
  l'instant, confiance B).
- **Une série par maille :** chaque localité a ses quatre séries, mais seule
  la porteuse d'une maille porte des mesures ; les autres séries lisent celles
  de leur porteuse (`serie_porteuse_id`), comme les séries denses
  (ADR-0017). La migration 0026 étend le mécanisme à l'horaire versionné :
  contrainte et garde de la porteuse (même famille et même stockage, un seul
  niveau), refus d'une mesure propre pour une série qui lit une porteuse, vue
  `v_mesures_horaires` qui rend à chaque série, porteuse ou non, les mesures
  horaires courantes. `/v1/horaire`, sa disponibilité, les grandeurs en
  intégration horaire et la capsule d'étude lisent par cette vue.
- **Mailles constatées sur les valeurs :** deux localités sont de la même
  maille quand leurs séries horaires 2021-2025 sont identiques, le GHI, le DNI
  et le DHI ensemble d'un côté, la température de l'autre. Le script interroge
  les 398 localités : 33 mailles de rayonnement et 83 de température. La
  porteuse d'une maille est son point pilote, dont la série est déjà stockée
  (migration 0011), sinon sa première localité dans l'ordre des codes. Les
  cinq pilotes sont dans des mailles distinctes, et NASA POWER leur sert
  toujours les valeurs de leurs fichiers : le script le vérifie.
- **Stockage versionné, pas dense :** chaque heure a son statut et son
  commentaire de contrôle qualité, que la table dense n'a pas, et peut
  recevoir un override.
- **Contrôle qualité avant le chargement :** doctrine v1 (ADR-0014), aux
  coordonnées de la porteuse, par `qualifier_series_horaires`. Elle calcule
  la géométrie et les bornes heure par heure avec les fonctions du contrôle
  existant et ne vectorise que les comparaisons ; elle redonne, ligne par
  ligne, le statut et le commentaire des 1 752 960 heures des pilotes (NASA
  POWER et CAMS Radiation), ce qu'un test vérifie. Chaque mesure entre avec
  son statut et son commentaire : pas de mise à jour après coup.
- **Fichiers :** `nasa_power_horaire_mailles_localites.csv` (porteuses de
  chaque localité) et un CSV gzip par grandeur des 28 porteuses de
  rayonnement et des 78 porteuses de température autres que les pilotes,
  33,5 Mo, écrits par `scripts/ingest_nasa_power_horaire.py --lot localites`
  (POWER Hourly API v2.10.3, consultée le 29 octobre 2026). La fiche de la
  source `nasa_power` le dit.

## Alternatives écartées

- **Une série par localité :** 68,9 millions de lignes au lieu de 7,1.
- **Stockage dense horaire :** compact, mais sans statut ni commentaire par
  heure, alors que `/v1/horaire` ne sert que l'horaire validé. À reconsidérer
  pour remonter à 2001, une quarantaine de millions de valeurs.
- **Contrôle après chargement, comme les migrations 0012 et 0022 :** il faut
  relire les 7,1 millions de lignes chargées, et leur mise à jour double la
  table et ses index. Le contrôle en mémoire prend 0,25 s par maille de
  rayonnement, contre 1,5 s pour le contrôle sur les lignes stockées.

## Conséquences

- 1 592 séries horaires NASA POWER, quatre par localité : 182 porteuses,
  dont les 20 des pilotes, et 1 410 séries qui lisent une porteuse.
  7 099 488 heures de plus dans `mesures_ressource_horaires`, chargées en
  7 min 13 s par la migration 0027 sur une base locale.
- Contrôle qualité : 7 099 487 heures `valide_auto`, dont 627 249 avec
  drapeaux, et une heure rejetée, le DHI de 607,85 W/m² servi à Falagountou
  le 18 février 2024 à 8 h UTC, au-dessus de la borne physique. Ce jour sort
  des intégrations horaires qui lisent ce DHI, à Falagountou et à Markoye,
  seules localités de la maille.
- `/v1/horaire` sert l'horaire validé NASA POWER de 2021-2025 aux
  398 localités ; pour ces quatre grandeurs, le relais ne sert plus que les
  plages qui débordent de 2021-2025, et l'édition figée sert l'horaire de
  toutes les localités.
- Le contrôle qualité d'une maille se fait aux coordonnées de sa porteuse.
  Les localités d'une maille de rayonnement sont à moins d'un degré de leur
  porteuse : la géométrie solaire diffère de quelques minutes au plus, ce qui
  ne joue qu'aux heures de lever et de coucher.
- Le POA horaire d'une commune prend la géométrie de la commune et le
  rayonnement de sa maille, comme en journalier.
- Les mailles de l'horaire sont celles du journalier : une localité et sa
  porteuse ont aussi le même GHI et la même température journaliers, ce qu'un
  test vérifie.
- La note des séries pilotes dit combien de localités les lisent : de 9
  (Dori) à 32 (Ouagadougou) pour le rayonnement, de 3 à 11 pour la
  température.
- CAMS Radiation horaire reste aux cinq pilotes (ADR-0023).
