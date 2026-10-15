# Changelog

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et
le projet suit le versionnement sémantique.

## 0.2.0

- Localités : les 351 communes (niveau `commune`), soit les 350 départements de
  l'annexe II du décret n°2025-1012 et la commune de Ouagadougou, rattachées à
  leur province, avec coordonnées Wikidata (deux centroïdes de contour COD-AB,
  ADR-0008) et population RGPH 2019 (INSD).

## 0.1.0

Amorçage de l'instance Burkina Faso, à partir d'un socle propre.

- Schéma : baseline unique regroupant le schéma complet du moteur (tables, vues,
  contraintes, index, fonctions PL/pgSQL, triggers d'audit et de validation
  hiérarchique, extension `btree_gist`), sans donnée.
- Référentiels génériques : unités, catalogue des grandeurs, sources amont (NASA
  POWER, ERA5 et ERA5-Land, SARAH-3 via PVGIS, CAMS, ESMAP/WAPP, normes IEC et
  WMO).
- Localités : le pays `bfa` (ISO 3166-1 alpha-3 : BFA), les 17 régions
  (`region_administrative`) et les 47 provinces (`prefecture`) du découpage de
  2025 (décrets n°2025-1012 et n°2025-1003), avec coordonnées Wikidata et
  population RGPH 2019 (INSD). Mapping de la hiérarchie et règle de sélection
  des coordonnées : ADR-0007 et ADR-0008. Départements à venir.
- Ingestion en mode direct (appel des sources amont), sans repli hors-ligne sur
  seed.
