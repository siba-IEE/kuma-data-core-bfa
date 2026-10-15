# Kuma Data Core (Burkina Faso)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Instance dédiée au Burkina Faso du moteur Kuma Data Core. Moteur de données à
confiance tracée : chaque valeur porte sa source, sa méthode, son niveau de
confiance (A/B/C), ses dates de validité et son statut éditorial. Versionnement
temporel non destructif, audit applicatif par triggers. Base PostgreSQL, API
FastAPI. Domaine : la ressource solaire au Burkina Faso.

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

`alembic upgrade head` n'exige aucun accès réseau : les valeurs sont relues dans
des CSV versionnés, produits par les scripts d'ingestion.

### À faire

- CAMS Radiation (compte Copernicus ADS requis) et séries journalières.
- Grandeurs métier calculées et contrôle qualité.
- Stations sol ESMAP/WAPP (Dédougou, Dori, Kaya, Koupéla) pour la confiance A.
- Adaptation de la documentation `docs/` au contexte burkinabè.

## Attribution des données amont

Les localités s'appuient sur Wikidata (CC0), sur le 5e RGPH 2019 de l'INSD
Burkina Faso et sur les contours administratifs COD-AB de l'IGB, publiés par
OCHA sur HDX (CC BY-IGO, « IGB / OCHA, via HDX »).

Les séries solaires proviennent de :

- **NASA POWER** (CC BY 4.0), POWER Monthly and Annual API v2.10.0, consultée
  le 15 octobre 2026 : « The data was obtained from National Aeronautics and
  Space Administration (NASA) Langley Research Center's Prediction Of
  Worldwide Energy Resources (POWER) project funded through the NASA Earth
  Science Division. »
- **PVGIS** (Joint Research Centre de la Commission européenne), API v5_3
  `MRcalc`, consultée le 15 octobre 2026 : « PVGIS © Union européenne,
  2001-2026 ». Réutilisation autorisée sous réserve de citer la source
  (décision 2011/833/UE de la Commission). PVGIS sert ici deux bases :
  - **SARAH-3**, données du Satellite Application Facility on Climate
    Monitoring (CM SAF) d'EUMETSAT : « © 2005-2023 EUMETSAT » ;
  - **ERA5**, Copernicus Climate Change Service (C3S), ECMWF (CC BY 4.0) :
    « Contains modified Copernicus Climate Change Service information
    2005-2023 ».

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
