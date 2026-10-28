# ADR-0024 : météo et rayonnement journaliers ERA5-Land

Date : 2026-10-28. Statut : accepté.

## Contexte

La météo journalière du dépôt vient de NASA POWER (ADR-0013, ADR-0021), donc
de la réanalyse MERRA-2, sur une maille de 0,5° × 0,625°. ERA5-Land est la
composante terrestre d'ERA5, rejouée par le CEPMMT sur une maille de 0,1°,
11 km environ (Muñoz-Sabater et al. 2021, ESSD 13:4349). Elle donne une
seconde réanalyse pour les mêmes grandeurs, mais pas plus fine pour toutes :
seules la température, l'humidité et la pression y sont ramenées à
l'altitude de la maille ; la pluie, le rayonnement et le vent sont le
forçage d'ERA5 (31 km environ), interpolé sans correction. La source
`ecmwf_era5_land` figurait au référentiel sans série, avec la fiche du dépôt
d'origine.

Le CDS Copernicus sert, par le jeu « ERA5-Land hourly time-series »
(`reanalysis-era5-land-timeseries`, DOI 10.24381/ee82e357, publié en 2025),
les valeurs horaires d'un point, celles de la maille la plus proche, sans
téléchargement de grilles.

## Décision

- **Grandeurs :** neuf grandeurs journalières, 2005-2025, aux 398 localités
  (lot `localites`), en stockage dense (ADR-0017), méthode `reanalyse`,
  confiance B (règle R4) :

  | Grandeur | Variable | Valeur du jour | Unité |
  |---|---|---|---|
  | `t2m` | `t2m` | moyenne des 24 heures | °C |
  | `t2m_min` | `t2m` | plus basse valeur horaire | °C |
  | `t2m_max` | `t2m` | plus haute valeur horaire | °C |
  | `point_rosee_2m` | `d2m` | moyenne des 24 heures | °C |
  | `pression_surface` | `sp` | moyenne des 24 heures | kPa |
  | `vent_10m` | `u10`, `v10` | moyenne des vitesses horaires | m/s |
  | `direction_vent_10m` | `u10`, `v10` | direction d'où souffle le vent moyen vectoriel | degrés depuis le nord |
  | `precipitation` | `tp` | cumul des heures | mm/jour |
  | `ghi` | `ssrd` | cumul des heures | kWh/m²/jour |

  Toutes figurent déjà au référentiel (ADR-0021 pour les grandeurs
  complémentaires). Les bornes sont celles de NASA POWER pour les mêmes
  grandeurs.
- **Jour UTC :** les valeurs instantanées de 0 h à 23 h ; les cumuls,
  datés de la fin de leur heure, de 1 h au lendemain 0 h. Les données le
  confirment : le centroïde du rayonnement tombe 0,46 h après le midi
  solaire, ce que donne un cumul daté de la fin de l'heure. La série servie
  s'arrête au 31 décembre 2025 à 23 h : ce jour-là, l'heure de 23 h à minuit
  manque aux cumuls. Elle est nocturne pour le rayonnement ; pour la pluie,
  les 23 autres heures de ce jour n'apportent pas 0,01 mm. La note de chaque
  série dit sa convention.
- **Contrôles de l'ingesteur :** heures régulières depuis le 1er janvier 2005
  à 0 h, mêmes instants d'une variable à l'autre, une seule maille par
  archive, à 0,05° au plus du point demandé, 184 080 heures sans manque,
  valeurs dans les bornes. Un cumul horaire très faiblement négatif, arrondi
  du modèle, compte zéro.
- **Ingesteur :** `scripts/ingest_era5_land_journalier.py`, une requête
  par localité (clé Copernicus, partagée par le CDS et l'ADS), deux à la
  fois, le CDS limitant les demandes en file ; archives brutes en cache.
  Migration 0023, qui réécrit aussi la fiche de `ecmwf_era5_land` pour le
  Burkina Faso (adresse, DOI et année du jeu horaire, notes, produits
  utilisés), rendue au `downgrade`.
- **Capsule d'étude :** les records de température y restent ceux de
  NASA POWER (`SOURCE_TEMPERATURES`) : sans ce choix explicite, la requête
  aurait pris les extrêmes des deux sources sous un seul code de source.

## Conséquences

- **Volume :** 3 582 séries, dont 3 339 porteuses (371 mailles par grandeur :
  27 mailles portent deux localités chacune). 70 119 lignes annuelles et
  25 610 130 valeurs, sans aucun jour manquant ; 107 Mo de valeurs en base,
  55 Mo de fichiers ; la migration dure une trentaine de secondes.
- **Moyennes sur 2005-2025, aux 398 localités :** température de 28,6 °C
  (minimum 22,9, maximum 34,7), point de rosée de 12,2 °C (8,7 au nord de
  13,5 °N, 15,7 au sud de 10,5 °N), pression de 97,5 kPa, vent de 2,5 m/s
  (3,2 au nord, 2,3 au sud), GHI de 6,04 kWh/m²/jour.
- **Écarts à NASA POWER, 2005-2025, jours communs :**

  | Grandeur | Écart d'ERA5-Land | Corrélation journalière |
  |---|---|---|
  | `t2m` (communes) | +0,8 °C | 0,90 |
  | `t2m_min` | +1,2 °C | 0,90 |
  | `t2m_max` | +0,0 °C | 0,90 |
  | `point_rosee_2m` | -1,4 °C | 0,96 |
  | `pression_surface` | -0,1 kPa | 0,87 |
  | `vent_10m` | -0,7 m/s | 0,78 |
  | `direction_vent_10m` | 13° d'écart médian | |
  | `precipitation` (communes) | -33 % | 0,45 |
  | `ghi` (communes) | +4,3 % | 0,60 |

  L'écart du point de rosée vaut -1,5 °C les jours où NASA POWER sert un
  point de rosée, -0,7 °C ceux où il sert un point de givre (14 % des jours).
- **Pluie :** ERA5-Land sert un tiers de pluie de moins que NASA POWER :
  611 mm par an aux communes contre 912 (323 contre 614 au nord, 861 contre
  1 168 au sud), et 87 jours à plus de 1 mm par an contre 139. Le rapport va
  de 0,56 à 0,74 selon l'année ; il descend à 0,45 en avril et 0,42 en mai,
  et remonte à 0,81 en août. La pluie d'ERA5-Land est celle d'ERA5,
  interpolée ; celle de NASA POWER est celle de MERRA-2 corrigée par des
  observations (`PRECTOTCORR`). Seules les stations sol départageront les
  deux sources (jalon 6). La note de chaque série le dit.
- **Rayonnement :** le GHI d'ERA5-Land est celui d'ERA5. Il dépasse en
  moyenne de 0,4 % le GHI mensuel d'ERA5 servi par PVGIS (ADR-0009), avec
  une corrélation de 0,998 et le même rapport en 2005-2015, 2016-2020 et
  2021-2023 : la hausse de 2021-2023 que l'ADR-0009 prêtait au produit
  PVGIS-ERA5 vient donc d'ERA5 lui-même. Il est proche en moyenne de CAMS
  (+0,7 %) et de SARAH-3 (-3,3 %), mais peu corrélé jour à jour (0,57 avec
  CAMS, 0,64 avec SARAH-3) : les nuages du modèle ne suivent qu'en partie
  ceux observés. C'est une source de comparaison, pas de référence.
- **Vent :** il est celui d'ERA5, interpolé, et plus faible que celui de
  NASA POWER de 0,7 m/s ; les deux réanalyses diffèrent, et seules les
  stations sol diront laquelle s'écarte.
- **Calculs :** les grandeurs calculées à partir du GHI trouvent la
  température ERA5-Land associée dans la même source (productible corrigé de
  la température, par exemple), et les degrés-jours partent directement de la
  température. Le GHI d'ERA5-Land n'a pas de DNI ni de DHI associés : le POA
  journalier qui en part passe par le repli isotrope (Erbs, puis Liu-Jordan),
  de précision dégradée.
- **Fiche de la source :** adresse, DOI et année du jeu horaire, notes au
  Burkina Faso, attribution « Contains modified Copernicus Climate Change
  Service information 2005-2025 ».
- **CI :** les migrations 0006 à 0023 prennent un quart d'heure environ sur
  un runner GitHub ; le job d'intégration a un plafond de 30 minutes.
