# ADR-0025 : propagation de la confiance aux grandeurs calculées

Date : 2026-10-28. Statut : accepté.

## Contexte

La définition de la confiance A admet une donnée « calculée par une méthode
reconnue à partir de mesures elles-mêmes A ». Les règles R1 à R4 ne regardent
pourtant que la méthode de collecte de la série et la fiabilité de sa source.
Les calculs à la volée de `/v1/grandeurs` posaient B en dur, et la fraction
diffuse stockée par la migration 0009 écrit B en SQL. Une grandeur tirée d'une
valeur qu'un override éditorial a descendue en C sortait donc en B, plus sûre
que ce dont elle est faite. La règle de propagation P vient du moteur ;
ce dépôt la reprend.

## Décision

- **Règle P :** évaluée après R3 et avant R4, elle donne à une valeur calculée
  le niveau effectif (override sinon dérivé) le plus bas de ses entrées, sans
  dépasser le plafond de sa méthode (`propager_niveau_confiance`,
  `editorial/niveaux_confiance.py`).
- **Plafond :** B par défaut. Il monte à A seulement pour un calcul exact, sans
  modèle ni hypothèse de l'utilisateur : ratio (fraction diffuse), statistique
  (P50/P90 de `ghi_exceedance`). Il reste B pour les grandeurs paramétrables
  (POA, bifacial, productibles, énergie ECS, degrés-jours), qui reposent sur
  un modèle et sur des paramètres déclarés que le producteur ne vérifie pas,
  et pour les proxys (salissure HSU, PR réaliste). Chaque module de calcul
  déclare son `PLAFOND_CONFIANCE`.
- **Source du calcul :** comme R3 pour une mesure, A exige une source de calcul
  de fiabilité haute : `kuma_calculs` pour une grandeur stockée, l'API
  elle-même pour un calcul à la volée.
- **Période :** chaque valeur ne voit que les entrées de sa période, un jour, un
  mois, ou la normale 1991-2020 de `ghi_exceedance`. Les lecteurs de l'API
  rangent les niveaux par jour (UTC pour l'horaire) et par mois
  (`NiveauxEntrees`). La salissure HSU, modèle cumulatif, prend le niveau des
  entrées de tous les jours retenus, et le PR réaliste aussi quand il en tient
  compte ; sans salissure, le PR réaliste se calcule jour par jour. Un jour de
  pluie comblé à 0 mm (ADR-0017) n'apporte pas de niveau : la salissure prend
  déjà celui de toute la fenêtre.
- **Application :** les calculs à la volée de `/v1/grandeurs` (grandeurs
  paramétrables, `ghi_exceedance`, `taux_salissure_proxy`, `pr_realiste`)
  remplacent le niveau provisoire du calcul pur. La fraction diffuse stockée
  garde ses lignes : une migration mergée est immuable (`CONTRIBUTING.md`), et
  le B qu'écrit 0009 est déjà celui de la règle P, ses entrées NASA POWER
  étant B. Un test d'intégration vérifie cet invariant avec la forme SQL de la
  règle : les niveaux étant ordonnés comme leurs lettres, le plus bas des
  entrées est `max(coalesce(niveau_confiance_override,
  niveau_confiance_derive))`, à borner par le plafond.
- **Textes publics :** la migration 0025 dit « confiance au plus B » dans les
  descriptions de `pr_realiste` et de `taux_salissure_proxy`, et cite la règle
  P dans le commentaire de `grandeurs_metier.niveau_confiance_derive`.

## Hors périmètre

Les écarts entre sources (migration 0009) et la dégénérescence de pixel
(migration 0014) gardent le B que leurs migrations écrivent, par la règle R4 :
leurs entrées, satellitaires ou de réanalyse, sont toutes B.
`incertitude_inter_source` continue d'exiger B et répond 500 plutôt que
d'afficher un autre niveau. Un recalcul futur de ces indicateurs devra passer
par la règle P, avec le plafond B.

## Conséquences

- Les séries du Burkina Faso, satellitaires ou de réanalyse, donnent toujours
  B : aucun niveau ne change, ni dans la base, ni dans les réponses de l'API.
  L'avertissement `limite` de `pr_realiste` dit « confiance au plus B » au lieu
  de « confiance B ».
- Une entrée C fait descendre en C les seules valeurs calculées de sa
  période. Une normale de trente ans passe en C pour un seul mois C, ce que
  les éditeurs doivent savoir avant de poser un override.
- Une série dense n'a pas d'override par valeur (ADR-0017) : ses lignes
  portent le niveau dérivé de leur série.
- Un niveau stocké se fixe au calcul. Une migration qui pose un override sur
  une entrée de la fraction diffuse fait échouer le test d'invariant : elle
  doit recalculer la grandeur.
- La confiance A reste vide au Burkina Faso ; les stations sol (jalon 6) la
  donneront aux mesures, puis, par la règle P, aux calculs exacts tirés
  d'elles.
