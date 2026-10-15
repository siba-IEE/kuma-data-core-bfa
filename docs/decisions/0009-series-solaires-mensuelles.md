# ADR-0009 : séries solaires mensuelles brutes

Date : 2026-10-15. Statut : accepté.

## Contexte

Le jalon 2 verse la donnée solaire brute, en confiance B, aux localités du
référentiel. Le contrat de ces séries est celui du moteur : une série par
localité, source et grandeur, valeurs figées dans des CSV compressés
versionnés, migrations sans accès au réseau. Ce lot l'applique directement sur
toute la période servie par les sources.

## Décision

Points : les 47 provinces et les 351 communes (migrations 0003 et 0004), à
leurs coordonnées gravées. Les régions ne reçoivent pas de série : un point
unique ne représente pas une région, et une valeur régionale relèvera d'une
agrégation des provinces.

| Source | Grandeurs | Période | Méthode |
|---|---|---|---|
| NASA POWER (id 1) | GHI / DNI / DHI | 1991 / 2001 / 2001 à 2025 | `modele_satellitaire` |
| SARAH-3 via PVGIS (id 11) | GHI / DNI | 2005 à 2023 | `modele_satellitaire` |
| ERA5 via PVGIS (id 16) | GHI / DNI | 2005 à 2023 | `reanalyse` |

- Valeur : moyenne journalière du mois, en kWh/m²/jour (grandeurs `ghi`,
  `dni`, `dhi`). NASA POWER sert directement cette moyenne ; PVGIS sert le
  total mensuel, divisé par le nombre de jours du mois.
- Période : la couverture réelle de chaque source à la date d'ingestion.
  NASA POWER ne sert pas le DNI avant 2001 et son DHI est en rupture avant
  2001 ; le GHI part de 1991 pour couvrir la normale 1991-2020. PVGIS s'arrête
  en 2023.
- Table `mesures_ressource_mensuelles`, statut `brut`, confiance B (règle R4).
- ERA5 est une réanalyse : source de comparaison, pas de référence. La
  migration 0005 ajoute la méthode `reanalyse` et la source `era5_pvgis`,
  distincte du produit CDS `ecmwf_era5` (id 2).
- Stockage : un CSV gzip par source, grandeur et lot sous
  `src/kuma_data_core/db/seeds/donnees/`, écrit de façon déterministe et
  validé à la relecture (période, bornes, doublons, complétude, coordonnées,
  localités). Les fichiers sont produits par
  `scripts/ingest_nasa_power_mensuel.py` et `scripts/ingest_pvgis_mensuel.py` ;
  la migration 0006 les relit sans accès au réseau.
- Bornes de plausibilité : 8,5 kWh/m²/jour pour le GHI, 10 pour le DNI, 6
  pour le DHI, au-dessus des maxima servis (7,83, 8,20 et 3,89) et sous le
  plafond physique par ciel clair à ces latitudes.
- CAMS Radiation n'est pas inclus : son service exige un compte Copernicus
  ADS. Il fera l'objet d'un lot distinct.

## Conséquences

- 2 786 séries et 768 936 mesures mensuelles. La migration 0006 dure 40 s
  environ ; le trigger d'audit des mesures est suspendu le temps du
  déversement (`docs/architecture/03-audit.md`, migrations de masse).
- Un contrôle a réinterrogé les API pour un échantillon tiré au hasard
  (12 localités pour NASA POWER, 9 par base PVGIS, 20 448 mesures) : aucun
  écart au-delà de l'arrondi à 4 décimales.
- NASA POWER sert le rayonnement sur une maille de 1° (CERES SYN1deg, produit
  SRB avant 2001) : les 351 communes tombent dans 33 mailles, les 47 provinces
  dans 24. Deux localités d'une même maille ont la même série NASA POWER, ce
  que précise la note publique. SARAH-3 et ERA5 donnent une série propre à
  chaque point.
- La normale 1991-2020 du GHI NASA POWER enchaîne ces deux produits. Le niveau
  moyen ne saute pas en 2001, mais le cycle saisonnier change (écart entre
  décembre-février et juillet-septembre de -0,11 avant 2001, +0,25 après), sans
  qu'on puisse séparer l'effet du produit de celui du retour des pluies.
- GHI cohérent entre sources : moyenne 2005-2023 sur les communes de 6,22
  (SARAH-3), 6,02 (ERA5) et 5,79 kWh/m²/jour (NASA POWER), croissante du sud
  au nord (corrélation avec la latitude de 0,93 à 0,99 selon la source).
- DNI divergent sur la même période : 5,77 (SARAH-3), 6,36 (ERA5) et
  3,89 kWh/m²/jour (NASA POWER), un tiers sous SARAH-3. Le DNI NASA POWER ne
  ferme pas toujours avec le GHI et le DHI : pour 8 % des mois, GHI - DHI
  dépasse le DNI. Ce lot verse les valeurs brutes sans arbitrer ; le choix
  d'une référence relève du contrôle qualité.
- SARAH-3 : des journées satellite manquantes ou partielles dans la source
  abaissent six mois sur tout le pays (janvier, mars et mai 2008, janvier et
  avril 2009, octobre 2016), jusqu'à 20 % environ en janvier 2009. Constat
  vérifié à Ouagadougou sur la série horaire PVGIS. Valeurs non corrigées,
  signalées dans la note publique.
- ERA5 : niveau 2021-2023 au-dessus de 2016-2020 (GHI +1,7 %, DNI +3,5 % sur
  les communes, pour une variabilité interannuelle de 1,1 % et 2,0 %), plus
  que SARAH-3 (+0,6 %, +0,9 %). Changement probable du produit PVGIS-ERA5,
  non établi. Valeurs non corrigées, signalées dans la note publique.
- Un nouveau lot (autre source, autre période) suit le même contrat : un
  ingesteur, des CSV, une migration.
