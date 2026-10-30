# Kuma Data Core (Burkina Faso)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Données de ressource solaire et de météo des 398 localités du Burkina Faso
(47 provinces et 351 communes du découpage de 2025), servies par une API
FastAPI sur PostgreSQL. Instance burkinabè du moteur Kuma Data Core.

Chaque valeur garde sa source, sa méthode, son niveau de confiance (A, B ou C)
et son statut éditorial. Une correction ajoute une version sans effacer
l'ancienne, sauf pour les séries journalières en stockage dense, rechargées
en bloc depuis leurs fichiers versionnés (ADR-0017).

## Données

Toutes les séries sont en confiance B ; le niveau A viendra des stations sol
ESMAP/WAPP ([feuille de route](ROADMAP.md), jalon 6).

| Source | Grandeurs | Pas | Localités | Période |
|---|---|---|---|---|
| NASA POWER | GHI, DNI, DHI | mois | 398 | 1991-2025 (DNI et DHI 2001-2025) |
| NASA POWER | GHI, DNI, DHI, température, humidité, pluie | jour | 47 provinces | 1991-2025 (DNI et DHI 2001-2025) |
| NASA POWER | GHI, DNI, DHI, température, humidité, pluie | jour | 351 communes | 2005-2025 |
| NASA POWER | température (min., max.), point de rosée, vent à 10 m (moyen, max.) et à 50 m, direction du vent, pression, nébulosité | jour | 398 | 2005-2025 |
| NASA POWER | GHI, DNI, DHI, température | heure | 398 | 2021-2025 |
| SARAH-3 (PVGIS) | GHI, DNI | mois | 398 | 2005-2023 |
| SARAH-3 (PVGIS) | GHI, DNI, DHI | jour | 398 | 2005-2023 |
| ERA5 (PVGIS) | GHI, DNI | mois | 398 | 2005-2023 |
| ERA5-Land | température (moy., min., max.), point de rosée, pression, vent à 10 m et direction, pluie, GHI | jour | 398 | 2005-2025 |
| CAMS Radiation | GHI, DNI, DHI | mois | 398 | 2005-2025 |
| CAMS Radiation | GHI, DNI, DHI, GHI et DNI par ciel clair | jour | 398 | 2005-2025 |
| CAMS Radiation | GHI, DNI, DHI, GHI par ciel clair | heure | 5 points pilotes | 2021-2025 |
| CAMS EAC4 | PM2.5, PM10, épaisseur optique des aérosols à 550 nm (totale, poussières, matière organique) | jour | 398 | 2005-2025 |

Les points pilotes sont Ouagadougou et les quatre sites des stations sol
(Dédougou, Dori, Kaya, Koupéla). Les séries horaires passent par le contrôle
qualité v1 (ADR-0014).

La base stocke aussi la fraction diffuse et les écarts mensuels de SARAH-3,
ERA5 et CAMS à NASA POWER (ADR-0012). L'API calcule à la demande
(`/v1/grandeurs`) le POA, les productibles, l'énergie utile ECS, les
degrés-jours de climatisation, les P50/P90 du GHI, le proxy de salissure, le
PR réaliste et l'incertitude inter-source. Une grandeur calculée prend le
niveau de confiance le plus bas de ses entrées, plafonné selon la méthode
(ADR-0025).

La [référence de l'API](docs/architecture/06-api-reference-publique.md)
détaille chaque grandeur ; les choix de méthode sont dans les
[ADR](docs/decisions/).

## Démarrage rapide

Prérequis : Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/siba-IEE/kuma-data-core-bfa.git
cd kuma-data-core-bfa
uv sync --group dev
cp docker/.env.example .env      # renseigner les mots de passe (champs changeme_*)
docker compose -f docker/docker-compose.yml --env-file .env up -d
uv run alembic upgrade head
uv run uvicorn kuma_data_core.api.main:app --reload
```

Les migrations chargent les données depuis les fichiers du dépôt, sans accès
réseau ; elles prennent une vingtaine de minutes en CI. L'API écoute sur
`http://127.0.0.1:8000` (`/docs` en dev).

## Stack

Python 3.12, PostgreSQL 16, FastAPI, SQLAlchemy 2.x, Alembic, Redis, Docker
Compose, uv, ruff, mypy, pytest. CI GitHub Actions (lint, types, tests unitaires
et d'intégration, contrôle de cohérence Alembic).

## Structure

| Chemin | Rôle |
|---|---|
| `src/kuma_data_core/db/` | Modèles SQLAlchemy, sessions, seeds de référentiels |
| `src/kuma_data_core/db/seeds/donnees/` | Données versionnées (CSV, Parquet) lues par les migrations |
| `src/kuma_data_core/api/` | Application FastAPI (auth Bearer) |
| `src/kuma_data_core/services/grandeurs/` | Modules de calcul par grandeur |
| `src/kuma_data_core/editorial/` | Statuts éditoriaux, confiance A/B/C, versionnement |
| `scripts/` | Scripts d'ingestion des sources externes et d'exploitation |
| `migrations/versions/` | Migrations Alembic |
| `migrations/sql/` | SQL de la baseline schéma et des référentiels |
| `tests/` | Tests unitaires et d'intégration |
| `docs/` | Architecture, conventions, méthodologie |

## Conventions

Le SQL et les identifiants métier sont en français. Toute évolution du schéma
passe par une migration Alembic. Détails dans
[docs/conventions/](docs/conventions/) et [CONTRIBUTING.md](CONTRIBUTING.md).

## Attribution des données amont

- NASA POWER (CC BY 4.0), API v2.10.0 à v2.10.3, consultée les 15, 27 et
  29 octobre 2026 : « The data was obtained from National Aeronautics and
  Space Administration (NASA) Langley Research Center's Prediction Of
  Worldwide Energy Resources (POWER) project funded through the NASA Earth
  Science Division. »
- PVGIS (JRC, Commission européenne), API v5_3, consultée les 15 et
  27 octobre 2026 : « PVGIS © Union européenne, 2001-2026 ». La décision
  2011/833/UE autorise la réutilisation sous réserve de citer la source. PVGIS
  sert ici SARAH-3, du CM SAF d'EUMETSAT (« © 2005-2023 EUMETSAT »), et ERA5,
  du Copernicus Climate Change Service (C3S, CC BY 4.0 : « Contains modified
  Copernicus Climate Change Service information 2005-2023 »).
- ERA5-Land, CEPMMT pour le C3S (CC BY 4.0, DOI 10.24381/ee82e357),
  consulté les 27 et 28 octobre 2026 : « Contains modified Copernicus Climate
  Change Service information 2005-2025 ».
- CAMS Radiation v4.6, Copernicus Atmosphere Monitoring Service (CC BY 4.0 ;
  Vaisala, MINES ParisTech, DLR), consulté les 15, 27 et 28 octobre 2026 :
  « Contains modified Copernicus Atmosphere Monitoring Service information
  2005-2025 ».
- CAMS EAC4, CEPMMT pour le CAMS (CC BY 4.0, DOI 10.24381/d58bbf47),
  consulté les 16 et 27 octobre 2026 : « Contains modified Copernicus
  Atmosphere Monitoring Service information 2005-2025 ». Inness, A. et al.
  (2019), « The CAMS reanalysis of atmospheric composition », *Atmos. Chem.
  Phys.*, 19, 3515-3556, doi:10.5194/acp-19-3515-2019.

Les localités viennent de Wikidata (CC0), du 5ᵉ RGPH 2019 de l'INSD et des
contours COD-AB de l'IGB publiés par OCHA sur HDX (CC BY-IGO, « IGB / OCHA,
via HDX »).

Ni la Commission européenne, ni le CEPMMT (ECMWF), ni EUMETSAT / CM SAF ne
sauraient être tenus responsables de l'usage fait de ces informations et
données transformées.

## Licence

Distribué sous licence AGPL-3.0-or-later (voir [LICENSE](LICENSE)). Si le
logiciel est exploité comme service en réseau, l'AGPL impose d'en publier les
modifications sous la même licence.

Projet développé et soutenu par Kuma Science
([kumascience.com](https://kumascience.com)).

## Contact

Siba Kalivogui, Kuma Science.
