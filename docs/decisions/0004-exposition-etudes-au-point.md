# ADR-0004 : exposition des études au point (résolution de cellule et référentiel de calage)

Date : 2026-07-20. Statut : accepté.

## Contexte

Le chantier Solar Bridge mini-réseaux (cadrage du 2026-07-20) fait de
l'API publique le guichet unique de données des études de
dimensionnement : le logiciel consomme le Core, il n'est jamais
l'autorité. Deux savoirs nécessaires aux études en un point quelconque
n'étaient pas servis par l'API :

1. **La climatologie au point.** Les points d'ingestion du
   référentiel échantillonnent les cellules de la grille de la source
   de climatologie (1 degré x 1 degré, frontières aux degrés entiers).
   Savoir quelle série représente un point est un savoir éditorial : le
   plus-proche-voisin naïf est faux dès que la localité la plus proche
   est dans une autre cellule que le point. La décision a été prise sur
   l'instance d'origine du moteur, où la moyenne 1991-2020 d'une série
   reproduisait à l'identique, sur les 12 mois, le relevé NASA POWER
   d'un point de la même cellule, alors que la localité la plus proche
   de ce point était dans la cellule voisine. Le laisser aux
   consommateurs garantirait des climatologies erronées.
2. **Le calage satellite/sol.** Les biais saisonniers mesurés à une
   station sol vivent dans des notes de méthodologie et leurs scripts
   reproductibles, pas dans l'édition servie.

Un premier cadrage envisageait un passe-plat climatologie au point
(relais amont à la demande) : contraire à la décision D6 de
l'ADR-0003 (édition figée, zéro dépendance sortante), abandonné. Un
deuxième envisageait d'ingérer une grille climatologique nationale :
redondant, les séries déjà ingérées couvrent le besoin.

## Décision

1. **Résolution au point servie par l'API** :
   `GET /v1/localites/resolution?lat=&lon=` retourne la localité du
   référentiel qui échantillonne la cellule du point (candidates :
   localités actives portant une série climatologie mensuelle active
   1991-2020 de la grandeur), avec bornes de cellule, distance et
   drapeau `meme_cellule`. Cellule non échantillonnée : la candidate
   la plus proche est renvoyée avec `meme_cellule=false`, à charge du
   consommateur d'afficher l'hypothèse de transport. Lecture pure du
   stocké, conforme D6.
2. **Référentiel de calage publié comme donnée éditoriale** : table
   `referentiels_calage` (une ligne par station, grandeur, saison :
   biais relatif satellite moins sol, provenance, portée de
   transport, version), seedée par migration, publiée dans l'édition
   (TABLES_PUBLIEES), servie par
   `GET /v1/calage/{localite}/{grandeur}` avec le facteur dérivé
   k = 1/(1+biais). Pas de grandeur recalculée à la volée : les
   lignes satellite horaires de l'appariement d'origine ne sont pas
   stockées, et le serveur public ne calcule que du reconstructible
   (D6). Le recalcul appartient à la chaîne de recherche (notes +
   scripts), l'édition publie le résultat avec sa provenance.
3. **Périmètre initial** : grandeur `ghi` seule pour la résolution ;
   un référentiel de calage par station et par grandeur, ajouté par
   migration quand un consommateur en a besoin (une migration = un
   changement).

## Conséquences

- Solar Bridge (et tout consommateur d'étude au point) obtient la
  climatologie juste et le calage tracé via l'API, sans embarquer ni
  géométrie de grille ni constantes de recherche.
- L'exposition n'atteint la production que par la publication d'une
  nouvelle édition (les données) et le redéploiement du conteneur API
  (le code des endpoints).
- La convention de cellule (1 degré, frontières entières) est
  documentée ; si une source de climatologie à grille différente entre
  au catalogue, la résolution devra porter la géométrie par source.

## Complément du 2026-07-20 au soir : couverture progressive

Décision du fondateur : les logiciels consommateurs ne couvrent
d'abord que la zone où le transport du calage est défendable, puis
grandissent ville par ville au rythme de la recherche. Le domaine de
couverture est une donnée servie, jamais une liste codée chez les
consommateurs :

- table `calage_couverture` (TABLES_PUBLIEES) : une ligne par localité
  qualifiée d'un référentiel, justification obligatoire ; servie par le
  champ `localites_couvertes` de `GET /v1/calage/{localite}/{grandeur}` ;
- domaine initial d'un référentiel : les localités voisines de la
  station sous le même régime climatique ;
- extension : qualification par la recherche (cohérence
  inter-source par cellule, campagnes de mesure, validation croisée
  quand une deuxième station sol existe), une édition à la fois ;
- côté consommateur : site hors domaine = refus honnête (décision
  produit Solar Bridge).

## État au Burkina Faso

- Aucune localité ne porte de série mensuelle bornée à 1991-2020 : la
  série mensuelle du GHI NASA POWER couvre 1991-2025 (ADR-0009).
  `/v1/localites/resolution` n'a donc aucune candidate et répond 404
  (`RESSOURCE_INTROUVABLE`).
- `referentiels_calage` et `calage_couverture` sont vides : aucune
  station sol n'est intégrée (feuille de route, jalon 6 ;
  [calage terrain](../methodologie/calage-terrain-solaire.md)).
  `GET /v1/calage` répond une liste vide, et
  `GET /v1/calage/{localite}/{grandeur}` 404.
- Aucun test d'intégration ne couvre ces deux endpoints.
