# Vision et positionnement de Kuma Data Core

## Raison d'être

Kuma Data Core est une infrastructure de données générique à confiance
tracée. Il définit, alimente et sert une base de données centrale conçue
pour agréger des données issues de sources publiques, d'enquêtes terrain
et de la littérature scientifique, en les enrichissant de métadonnées
rigoureuses, et en les rendant exploitables aussi bien éditorialement
(articles) que programmatiquement (outils).

La connaissance technique localisée fait défaut aux acteurs de
l'ingénierie énergétique africaine. Les bases de données existantes sont
soit globales et peu pertinentes à l'échelle d'une localité, soit
fragmentées, soit propriétaires et inaccessibles. Kuma Data Core adresse
ce manque avec un modèle de données à schéma physique unique et
générique, dans lequel une ressource ou une source nouvelle s'ajoute par
seed et migration, sans refonte.

## Principes structurants

Six principes non négociables guident les décisions techniques :

1. **Métadonnées systématiques** - chaque donnée est accompagnée de sa
   source primaire, de sa méthode de collecte, d'un niveau de confiance
   (A, B, C), de la date de collecte, d'une éventuelle date de
   péremption, de l'auteur de la saisie et d'un statut éditorial
   (`brut`, `valide_auto`, `valide_humain`, `publie`, `deprecie`).
2. **Versioning temporel** - aucune mise à jour destructive ; toute
   évolution d'une donnée crée une nouvelle ligne dotée d'une période de
   validité (`valide_du`, `valide_au`). Les séries journalières brutes en
   stockage dense font exception : une correction les réédite en bloc
   depuis un fichier versionné (ADR-0017).
3. **Table `sources` centrale** - toute donnée pointe vers une source
   documentée. La table `sources` est l'ossature de la crédibilité du
   système.
4. **Validation à deux niveaux** - validation automatique (cohérence,
   fourchettes, doublons) puis validation humaine pour les données
   critiques avant publication.
5. **Audit centralisé** - toute modification est tracée dans un
   `audit_log` unique.
6. **Aucune modification manuelle de la base de production** - toute
   évolution du schéma ou des données passe par une migration versionnée
   et par la chaîne d'intégration continue.

## Niveaux de confiance

Chaque mesure porte un niveau de confiance A / B / C :

- **A** - haute confiance, réservée aux mesures terrain directes et aux
  calculs exacts qui n'utilisent qu'elles.
- **B** - confiance moyenne (modèle satellitaire, réanalyse, ou grandeur
  calculée par un modèle ou à partir de valeurs B).
- **C** - confiance basse (estimation d'expert sans validation
  instrumentale, source de fiabilité faible, ou calcul tiré d'une valeur C).

Ce niveau est dérivé automatiquement à partir de la méthode de collecte
et de la fiabilité de la source ; une grandeur calculée prend le niveau le
plus bas de ses entrées, sans dépasser le plafond de sa méthode (ADR-0025).
Un override éditorial justifié reste possible.

## Burkina Faso

Ce dépôt contient les données solaires et météo du Burkina Faso aux
398 localités du découpage de 2025 : 47 provinces, 350 départements et
la commune de Ouagadougou (ADR-0007). Le rayonnement (GHI, DNI, DHI, ciel
clair) et la météo, aux pas mensuel, journalier et horaire, viennent de
NASA POWER, de SARAH-3 et ERA5 via PVGIS, d'ERA5-Land et de CAMS
Radiation ; les aérosols (particules fines, épaisseur optique) viennent de
CAMS EAC4. Toutes ces séries sont en confiance B. La base stocke aussi des
grandeurs dérivées (écarts entre sources, fraction diffuse), et l'API en
calcule d'autres à la demande (POA, productibles, énergie utile ECS,
degrés-jours, PR réaliste). La confiance A attend les stations au sol
(feuille de route, jalon 6). D'autres domaines (vent, hydrologie, biomasse,
infrastructure, usages) et d'autres pays peuvent s'ajouter sans changer le
schéma.

## Données publiques

Les valeurs ingérées sont versionnées dans ce dépôt, en CSV et Parquet
produits par les scripts d'ingestion (`src/kuma_data_core/db/seeds/donnees/`),
et servies par l'API.

## Opération

Kuma Data Core est opéré et soutenu par Kuma Science, média scientifique
d'ingénierie énergétique appliquée. Le média et les outils dérivés
partagent la même source de vérité, dont Kuma Data Core est l'expression
opérationnelle.
