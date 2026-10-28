# Guide de contribution de données

Ce dépôt est l'instance Burkina Faso du moteur
[Kuma Data Core](https://github.com/siba-IEE/kuma-data-core). Ce guide
explique comment une donnée est modélisée dans le Core, pour que vous sachiez
ce que vous contribuez.

## Le modèle, entité par entité

- **Localité** : le lieu. Une hiérarchie à sept niveaux (continent, région
  supranationale, pays, région administrative, préfecture, commune, site) avec
  un code `pays_iso3`. Le pays est un niveau de cette hiérarchie, pas une
  notion câblée en dur (voir [généricité pays](genericite-pays.md)). Au
  Burkina Faso : le pays, 17 régions, 47 provinces au niveau `prefecture` et
  351 communes (ADR-0007).
- **Source** : la provenance. Une source ouverte (satellite, réanalyse,
  station) porte une fiabilité (`haute`, `moyenne`, `faible`).
- **Grandeur** : ce qui est mesuré. Deux niveaux : le référentiel
  (`grandeurs_referentiel`, la définition catalogue) et la valeur métier
  (`grandeurs_metier`, une valeur calculée ou stockée).
- **Série** (`series_metadonnees`) : une localité, une grandeur et une source,
  sur une période et à une granularité (mensuelle, journalière ou horaire).
  Elle porte la méthode de collecte (`mesure_directe`, `modele_satellitaire`,
  `reanalyse`, `expertise_humaine`, entre autres).
- **Mesure** : la valeur elle-même, journalière, mensuelle ou horaire, avec sa
  date, sa valeur, sa confiance, son statut et sa validité temporelle.

## Trois propriétés de première classe

Chaque valeur porte, en plus de sa source et de sa méthode :

- une **confiance** A/B/C dérivée par des règles, avec override motivé ;
- un **statut éditorial** (de `brut` à `publie`) ;
- une **validité temporelle** : rien n'est écrasé en place. Une nouvelle valeur
  supplante l'ancienne par versionnement (`valide_du`, `valide_au`) ; les
  lectures ne renvoient que la version courante. Les séries journalières
  denses font exception : une correction les réédite en bloc (ADR-0017).

Le détail est dans [confiance et statuts](confiance-et-statuts.md).

## Comment une donnée entre aujourd'hui

Par un script d'ingestion et une migration. Le script
(`scripts/ingest_*.py`) interroge la source et écrit un fichier versionné,
CSV gzip ou Parquet, dans `src/kuma_data_core/db/seeds/donnees/`. La migration
relit ce fichier, sans accès réseau, contrôle ses valeurs contre le contrat de
la série (période, bornes) et les insère. Une donnée proposée suit le même
chemin : elle entre par une migration, écrite à partir de ce que vous
fournissez.

## Où contribuer

Données, stations, moteur, connecteurs et méthodes : via les
[issues](https://github.com/siba-IEE/kuma-data-core-bfa/issues) de ce dépôt,
avec le modèle adapté.

Conventions de nommage et de schéma :
[docs/conventions/01-naming.md](../conventions/01-naming.md).
