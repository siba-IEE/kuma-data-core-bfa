# Kuma Data Core (Burkina Faso)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Instance dédiée au Burkina Faso du moteur Kuma Data Core. Moteur de données à
confiance tracée : chaque valeur porte sa source, sa méthode, son niveau de
confiance (A/B/C), ses dates de validité et son statut éditorial. Versionnement
temporel non destructif, audit applicatif par triggers. Les séries journalières
brutes en masse font exception : stockage dense, sans versionnement par valeur,
rééditées en bloc depuis des fichiers versionnés (ADR-0017). Base PostgreSQL,
API FastAPI. Domaine : la ressource solaire au Burkina Faso.

Le code moteur est générique : le pays est un axe de classification, pas une base
séparée. Cette instance repart d'un socle propre, sans donnée d'une autre
instance.

## État

Socle en place. La donnée nationale se construit par lots.

- Schéma : baseline unique regroupant le schéma complet du moteur (tables, vues,
  contraintes, index, fonctions PL/pgSQL, triggers d'audit et de validation
  hiérarchique, extension `btree_gist`), sans donnée.
- Référentiels génériques : unités, catalogue des grandeurs, sources amont (NASA
  POWER, ERA5 et ERA5-Land, SARAH-3 via PVGIS, CAMS, ESMAP/WAPP, normes IEC et
  WMO).
- Localités : le pays `bfa` (ISO 3166-1 alpha-3 : BFA), les 17 régions (niveau
  `region_administrative`), les 47 provinces (niveau `prefecture`) et les
  351 communes (niveau `commune` : 350 départements et la commune de
  Ouagadougou) du découpage de 2025 (décrets n°2025-1012 et n°2025-1003), avec
  coordonnées Wikidata (deux centroïdes de contour COD-AB, ADR-0008) et
  population RGPH 2019 (INSD).
- Donnée solaire brute : séries mensuelles aux 47 provinces et aux 351 communes,
  en confiance B : NASA POWER (GHI 1991-2025, DNI et DHI 2001-2025), SARAH-3 et
  ERA5 via PVGIS (GHI et DNI 2005-2023). Voir
  l'[ADR-0009](docs/decisions/0009-series-solaires-mensuelles.md).
- Séries journalières NASA POWER aux 47 provinces, en confiance B (GHI
  1991-2025, DNI et DHI 2001-2025). Voir
  l'[ADR-0010](docs/decisions/0010-series-journalieres-nasa-power.md).
- Séries journalières NASA POWER aux 351 communes, 2005-2025, en confiance B :
  GHI, DNI, DHI, température, humidité et pluie, en stockage dense (une
  série par commune, les communes d'une même maille partageant les mêmes
  mesures). Voir
  l'[ADR-0017](docs/decisions/0017-stockage-dense-des-series-journalieres.md).
- Météo complémentaire NASA POWER aux 398 localités, 2005-2025, en confiance
  B et en stockage dense : températures minimale et maximale, point de rosée,
  vent à 10 et 50 m, direction du vent, pression et nébulosité. Voir
  l'[ADR-0021](docs/decisions/0021-meteo-complementaire-nasa-power.md).
- Météo et rayonnement journaliers ERA5-Land aux 398 localités, 2005-2025, en
  confiance B et en stockage dense : température moyenne, minimale et
  maximale, point de rosée, pression, vent et direction du vent, pluie et
  GHI. La pluie y est d'un tiers plus faible que chez NASA POWER. Voir
  l'[ADR-0024](docs/decisions/0024-era5-land-journalier.md).
- SARAH-3 journalier (PVGIS) aux 398 localités, 2005-2023, en confiance B et
  en stockage dense : GHI, DNI et DHI ; les heures que SARAH-3 ne sert pas
  sont complétées au prorata du ciel clair, sauf quand elles couvrent
  d'affilée plus de la moitié du jour, qui reste alors sans valeur. Voir
  l'[ADR-0022](docs/decisions/0022-sarah3-journalier.md).
- CAMS Radiation : séries mensuelles GHI, DNI et DHI aux 47 provinces et aux
  351 communes, 2005-2025, en confiance B. Voir
  l'[ADR-0011](docs/decisions/0011-series-cams-radiation.md). Séries
  journalières aux 398 localités, avec le GHI et le DNI par ciel clair, en
  stockage dense : voir
  l'[ADR-0020](docs/decisions/0020-cams-radiation-journalier.md). Séries
  horaires 2021-2025 aux cinq points pilotes, avec le GHI par ciel clair,
  contrôlées par la doctrine QC v1 et servies par `/v1/horaire` avec
  `source=cams_radiation` : voir
  l'[ADR-0023](docs/decisions/0023-cams-radiation-horaire.md).
- Grandeurs dérivées stockées aux 398 localités, calculées en base depuis les
  séries mensuelles : écarts relatifs mensuels à NASA POWER (GHI et DNI de
  SARAH-3, ERA5 et CAMS ; DHI de CAMS) et fraction diffuse NASA POWER,
  mensuelle et annuelle. Voir
  l'[ADR-0012](docs/decisions/0012-grandeurs-derivees-stockees.md).
- Météo journalière NASA POWER aux 47 provinces (température, humidité, pluie,
  1991-2025) et grandeurs métier calculées par l'API : POA, productibles,
  énergie utile ECS, degrés-jours, P50/P90, PR réaliste corrigé de la
  température. Voir
  l'[ADR-0013](docs/decisions/0013-meteo-journaliere-et-grandeurs-calculees.md).
- Séries horaires NASA POWER (GHI, DNI, DHI, température, 2021-2025) à cinq
  points pilotes, Ouagadougou et les quatre sites des stations sol, contrôlées
  par la doctrine QC v1 et servies par `/v1/horaire` ; grandeurs métier en
  intégration horaire. Voir
  l'[ADR-0014](docs/decisions/0014-series-horaires-et-controle-qualite.md).
- Particules fines CAMS EAC4 (PM2.5 et PM10 journaliers, 2005-2025) aux
  47 provinces, en confiance B, et grandeurs qui en dépendent : proxy de
  salissure et PR réaliste corrigé de la salissure. Voir
  l'[ADR-0015](docs/decisions/0015-particules-fines-cams-eac4.md). Mêmes séries
  et mêmes grandeurs aux 351 communes, en stockage dense : voir
  l'[ADR-0018](docs/decisions/0018-particules-fines-aux-communes.md).
- Fiche d'incertitude inter-source aux 398 localités : écart de SARAH-3, ERA5
  et CAMS à NASA POWER sur 2005-2023, et nombre de localités qui partagent la
  même maille NASA POWER. Voir
  l'[ADR-0016](docs/decisions/0016-incertitude-inter-source.md).
- Épaisseur optique des aérosols à 550 nm (totale, poussières, matière
  organique), CAMS EAC4, journalière 2005-2025 aux 398 localités, en stockage
  dense et en confiance B. Voir
  l'[ADR-0019](docs/decisions/0019-epaisseur-optique-des-aerosols.md).

`alembic upgrade head` n'exige aucun accès réseau : les valeurs sont relues dans
des CSV et des fichiers Parquet versionnés, produits par les scripts
d'ingestion.

### À faire

- Stations sol ESMAP/WAPP (Dédougou, Dori, Kaya, Koupéla) pour la confiance A
  (jalon 6).
- Correction du POA en moyenne journalière, biaisé par la géométrie du midi
  solaire (ADR-0020).
- Adaptation de la documentation `docs/` au contexte burkinabè.

## Attribution des données amont

Les localités s'appuient sur Wikidata (CC0), sur le 5e RGPH 2019 de l'INSD
Burkina Faso et sur les contours administratifs COD-AB de l'IGB, publiés par
OCHA sur HDX (CC BY-IGO, « IGB / OCHA, via HDX »).

Les séries proviennent de :

- **NASA POWER** (CC BY 4.0), POWER Monthly and Annual API, POWER Daily API
  v2.10.0 et POWER Hourly API v2.10.2, consultées le 15 octobre 2026 ; POWER
  Daily API v2.10.1 pour les communes et la météo complémentaire, consultée le
  27 octobre 2026. « The
  data was obtained from National Aeronautics and Space Administration (NASA)
  Langley Research Center's Prediction Of Worldwide Energy Resources (POWER)
  project funded through the NASA Earth Science Division. » NASA POWER tire sa
  météo de la réanalyse MERRA-2 du GMAO (NASA), et sa nébulosité de CERES.
- **PVGIS** (Joint Research Centre de la Commission européenne), API v5_3
  `MRcalc`, consultée le 15 octobre 2026, et `seriescalc` (séries horaires
  SARAH-3), consultée le 27 octobre 2026 : « PVGIS © Union européenne,
  2001-2026 ». Réutilisation autorisée sous réserve de citer la source
  (décision 2011/833/UE de la Commission). PVGIS sert ici deux bases :
  - **SARAH-3**, données du Satellite Application Facility on Climate
    Monitoring (CM SAF) d'EUMETSAT : « © 2005-2023 EUMETSAT » ;
  - **ERA5**, Copernicus Climate Change Service (C3S), ECMWF (CC BY 4.0) :
    « Contains modified Copernicus Climate Change Service information
    2005-2023 ».
- **ERA5-Land**, réanalyse du CEPMMT pour le Copernicus Climate Change
  Service (C3S, CC BY 4.0), jeu « ERA5-Land hourly time-series » du CDS
  Copernicus (DOI 10.24381/ee82e357), consulté les 27 et 28 octobre 2026 :
  « Contains modified Copernicus Climate Change Service information
  2005-2025 ».
- **CAMS Radiation**, Copernicus Atmosphere Monitoring Service (CC BY 4.0),
  service v4.6 (Vaisala, MINES ParisTech et DLR) diffusé par l'ADS
  Copernicus, consulté le 15 octobre 2026 (séries mensuelles), le 27 octobre
  2026 (séries journalières) et les 27 et 28 octobre 2026 (séries horaires) :
  « Contains modified Copernicus Atmosphere Monitoring Service information
  2005-2025 ».
- **CAMS EAC4**, réanalyse globale de composition atmosphérique du Copernicus
  Atmosphere Monitoring Service (CEPMMT, CC BY 4.0), jeu
  `cams-global-reanalysis-eac4` (DOI 10.24381/d58bbf47) diffusé par l'ADS
  Copernicus, consulté le 16 octobre 2026 (particules fines) et le 27 octobre
  2026 (épaisseur optique des aérosols) : « Contains modified Copernicus
  Atmosphere Monitoring Service information 2005-2025 ». Référence : Inness,
  A. et al. (2019), « The CAMS reanalysis of atmospheric composition »,
  *Atmos. Chem. Phys.*, 19, 3515-3556, doi:10.5194/acp-19-3515-2019.

Ni la Commission européenne, ni le CEPMMT (ECMWF), ni EUMETSAT / CM SAF ne
sauraient être tenus responsables de l'usage fait de ces informations et
données transformées.

## Démarrage rapide

Pré-requis : Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/siba-IEE/kuma-data-core-bfa.git
cd kuma-data-core-bfa
uv sync --group dev
cp docker/.env.example .env      # renseigner les mots de passe (champs changeme_*)
docker compose -f docker/docker-compose.yml --env-file .env up -d
uv run alembic upgrade head
uv run uvicorn kuma_data_core.api.main:app --reload
```

L'API écoute sur `http://127.0.0.1:8000` (`/docs` en dev).

## Stack

Python 3.12, PostgreSQL 16, FastAPI, SQLAlchemy 2.x, Alembic, Redis, Docker
Compose, uv, ruff, mypy, pytest. CI GitHub Actions (lint, types, tests unitaires
et d'intégration, contrôle de cohérence Alembic).

## Structure

| Chemin | Rôle |
|---|---|
| `src/kuma_data_core/db/` | Modèles SQLAlchemy, sessions, seeds de référentiels |
| `src/kuma_data_core/api/` | Application FastAPI (auth Bearer) |
| `src/kuma_data_core/services/grandeurs/` | Modules de calcul par grandeur |
| `src/kuma_data_core/ingestion/` | Ingestion des sources externes |
| `src/kuma_data_core/editorial/` | Statuts éditoriaux, confiance A/B/C, versionnement |
| `migrations/versions/` | Migrations Alembic (baseline, référentiels, localités) |
| `migrations/sql/` | SQL de la baseline schéma et des référentiels |
| `tests/` | Tests unitaires et d'intégration |
| `docs/` | Architecture, conventions, méthodologie |

## Conventions

Le SQL et les identifiants métier sont en français. Toute évolution du schéma
passe par une migration Alembic. Détails dans
[docs/conventions/](docs/conventions/) et [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Distribué sous licence AGPL-3.0-or-later (voir [LICENSE](LICENSE)). Exploité comme
service en réseau, l'AGPL impose de publier les modifications sous la même
licence.

Projet développé et soutenu par Kuma Science
([kumascience.com](https://kumascience.com)).

## Contact

Siba Kalivogui, Kuma Science.
