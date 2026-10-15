# Feuille de route

Instance dédiée au Burkina Faso du moteur Kuma Data Core. Le moteur est
générique (le pays est un axe de classification) ; cette feuille de route couvre
l'amorçage et la montée en charge de la donnée burkinabè.

## Jalon 1 : localités

- [x] Pays `bfa`, 17 régions (`region_administrative`) et 47 provinces
      (`prefecture`), découpage de 2025 (décrets n°2025-1012 et n°2025-1003).
- [x] Arrêter le mapping de la hiérarchie burkinabè (région, province,
      département, village) sur les 7 niveaux du schéma (ADR-0007) et la règle
      de sélection des coordonnées Wikidata (ADR-0008).
- [x] 350 départements et commune de Ouagadougou (niveau `commune`), avec
      coordonnées et population RGPH 2019.

## Jalon 2 : donnée solaire brute

- [x] Séries mensuelles brutes aux provinces et aux communes, en confiance B :
      NASA POWER, SARAH-3 et ERA5 via PVGIS (ADR-0009).
- [x] Chaîne d'ingestion reproductible : ingesteurs, CSV versionnés, migration
      sans réseau.
- [ ] CAMS Radiation (compte Copernicus ADS requis).
- [x] Séries journalières NASA POWER aux provinces (ADR-0010).

## Jalon 3 : grandeurs et qualité

- [ ] Grandeurs métier calculées (POA, productible, P50/P90, salissure, PR
      réaliste) exposées par l'API.
- [ ] Contrôle qualité horaire.

## Jalon 4 : terrain (confiance A)

- [ ] Intégrer les stations sol ESMAP/WAPP du Burkina Faso (Dédougou, Dori, Kaya,
      Koupéla) comme première ancre de confiance A, et le calage terrain associé.

## Documentation

- [ ] Adapter `docs/` au contexte burkinabè.
