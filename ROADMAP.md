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
- [x] CAMS Radiation, séries mensuelles aux provinces et aux communes
      (ADR-0011).
- [x] Séries journalières NASA POWER aux provinces (ADR-0010).

## Jalon 3 : grandeurs et qualité

- [x] Grandeurs dérivées stockées : écarts entre sources et fraction diffuse
      (ADR-0012).
- [x] Adapter `/v1/grandeurs/incertitude_inter_source` aux écarts de l'ADR-0012
      (ADR-0016).
- [x] Météo journalière NASA POWER et grandeurs métier calculées par l'API :
      POA, productibles, ECS, degrés-jours, P50/P90, PR réaliste corrigé de la
      température (ADR-0013).
- [x] Particules fines CAMS EAC4, salissure et PR réaliste corrigé de la
      salissure (ADR-0015).
- [x] Séries horaires aux cinq points pilotes et contrôle qualité horaire
      (ADR-0014).

## Jalon 4 : granularité journalière

- [x] Stockage dense des séries journalières et NASA POWER journalier aux
      351 communes, 2005-2025 : rayonnement et météo (ADR-0017).
- [ ] CAMS Radiation journalier aux 398 localités, 2005-2025 : GHI, DNI, DHI
      et ciel clair.
- [x] CAMS EAC4 aux communes : PM2.5 et PM10, salissure aux communes
      (ADR-0018).
- [x] CAMS EAC4 : épaisseur optique des aérosols (totale, poussières, matière
      organique) aux 398 localités (ADR-0019).

## Jalon 5 : terrain (confiance A)

Annoncé au jalon 4 par les ADR-0012, ADR-0014 et ADR-0016, avant que ce jalon ne passe à
la granularité journalière.

- [ ] Intégrer les stations sol ESMAP/WAPP du Burkina Faso (Dédougou, Dori, Kaya,
      Koupéla) comme première ancre de confiance A, et le calage terrain associé.

## Documentation

- [ ] Adapter `docs/` au contexte burkinabè.
