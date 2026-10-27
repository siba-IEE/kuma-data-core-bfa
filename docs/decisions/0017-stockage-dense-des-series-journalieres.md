# ADR-0017 : stockage dense des séries journalières

Date : 2026-10-27. Statut : accepté.

## Contexte

Le jalon 4 vise des séries journalières 2005-2025 aux 398 localités pour NASA
POWER, CAMS Radiation et CAMS EAC4, soit une cinquantaine de millions de
valeurs. `mesures_ressource` versionne chaque valeur (période de validité,
contrainte d'exclusion GiST, statut éditorial, audit ligne à ligne) : environ
260 octets par valeur, index compris, sur une base neuve. La CI rejoue toutes
les migrations sur une base vide : sur `main`, le job d'intégration dure
11 min 40 s, dont 10 min 40 s de migrations, pour un plafond de 20 minutes. Les
valeurs du jalon sont brutes, rejouables depuis des fichiers versionnés, et ne sont
jamais éditées une à une.

Une source maillée sert en outre la même série à toutes les localités d'une
maille : pour les 351 communes, NASA POWER sert 33 séries de rayonnement
distinctes par grandeur (maille CERES de 1°) et 82 séries météo par grandeur
(maille MERRA-2 de 0,5° × 0,625°).

## Décision

- Table `mesures_journalieres_denses` : une ligne par série et par année
  (`serie_id`, `annee`, `niveau_confiance_derive`, `valeurs_e4`), les valeurs
  du 1er janvier au 31 décembre dans un tableau d'entiers en dix-millièmes,
  absentes (NULL) pour un jour sans valeur ; clé primaire `(serie_id, annee)`,
  un jour par jour de l'année (contrainte). Sans versionnement, statut ni
  audit ligne à ligne ; le statut est `brut` par construction.
- `series_metadonnees.stockage` vaut `versionne` (défaut) ou `dense` ; une
  série dense est journalière.
- `series_metadonnees.serie_porteuse_id` : une série identique à une autre de
  la même famille (même source, grandeur, période et granularité, même maille)
  ne porte pas de lignes et lit celles de sa porteuse, la série de la première
  localité de la maille dans l'ordre des codes.
- Vue `v_mesures_journalieres` : mesures journalières courantes de
  `mesures_ressource` et mesures denses dépliées, rendues à chaque série,
  porteuse ou non. `/v1/series`, les grandeurs calculées par l'API et les
  services de grandeurs lisent le journalier par cette vue, par identifiant de
  série. La vue ne reçoit pas le prédicat d'une jointure (sa branche dense
  contient elle-même une jointure) : une requête résout d'abord ses séries,
  puis lit la vue par `serie_id = ANY(ARRAY(...))`.
- Garde-fous en base (triggers) : aucune mise à jour de ligne dense ; lignes
  denses réservées aux séries denses porteuses, dans les années de leur
  période ; aucune mesure versionnée pour une série dense (insertion,
  changement de série ou passage d'une série en stockage dense) ; une
  porteuse est dense, de la même famille et ne lit elle-même aucune porteuse
  (un seul niveau) ; une porteuse lue par d'autres séries ne change ni de
  famille ni de stockage.
- Une correction réédite la série : la migration de réédition supprime ses
  lignes et la recharge depuis le nouveau fichier. L'édition précédente quitte
  la base et ne survit que dans l'historique du dépôt (fichier et migration).
- Fichiers Parquet sous `seeds/donnees/denses/`, un par contrat et par lot,
  écrits par `series_denses.ecrire_series_denses` : chaque série distincte une
  fois, sous le code de sa première localité ; valeurs en dix-millièmes
  entiers (exactes à 4 décimales, comme les CSV), absentes (NULL) quand la
  valeur manque ; compression zstd. Métadonnées : représentante de chaque
  localité, latitude et longitude interrogées (comparées aux coordonnées en
  base au chargement), service, version et date de consultation de la source,
  valeurs écartées avec la valeur servie. L'écriture valide le contrat, relit
  le fichier et le compare à son contenu avant de le mettre en place ; à
  version de pyarrow égale, les mêmes données donnent les mêmes octets.
  pyarrow rejoint les dépendances.
- Une valeur hors des bornes de plausibilité du contrat n'est écartée que si
  le contrat la liste (`ecarts_admis` : localité, jour) ; toute autre valeur
  hors bornes arrête l'ingestion, si bien qu'une erreur d'unité ne passe pas
  en écarts silencieux. Le jour écarté n'a pas de valeur, et la note publique
  de la série dit le jour, la valeur servie et la borne. Les CSV des
  provinces continuent de refuser toute valeur hors bornes.
- La table dense sort du périmètre d'audit : ses écritures sont des
  déversements rejouables à l'identique (voir `docs/architecture/03-audit.md`).
  Les séries elles-mêmes restent auditées dans `series_metadonnees`.

## Alternatives écartées

Mesurées sur le lot NASA POWER des communes :

| Stockage | Lignes | Taille en base | Migration 0016 |
|---|---|---|---|
| Une ligne par jour, sans partage de maille | 16,2 millions | 1,35 Go | 2 min 22 s |
| Une ligne par jour, avec partage | 2,65 millions | 222 Mo | 26 s |
| Une ligne par année, avec partage (retenu) | 7 245 | 14 Mo | 7 s |

Une ligne par jour aurait porté CAMS Radiation (15 millions de lignes, sans
partage possible) à 1,3 Go et ajouté environ trois minutes à la CI.
Partitionner la table par lot aurait accéléré les rechargements sans réduire
la taille.

## Conséquences

- Premier lot, migration 0016 : NASA POWER journalier aux 351 communes,
  2005-2025, GHI, DNI, DHI, température, humidité et pluie. 2 106 séries,
  dont 345 porteuses ; 7 245 lignes annuelles, 2 646 149 valeurs ; 5,7 Mo de
  fichiers (33 Mo sans partage de maille).
- Une série se lit par identifiant en 4 ms pour 21 ans ; la vue déplie les
  tableaux de la série demandée seulement, mais toutes ses années, même pour
  une fenêtre d'un mois (2 ms).
- Banfora et la province de la Comoé ont les mêmes coordonnées : leurs six
  grandeurs ont les mêmes valeurs depuis 2005, d'un stockage à l'autre. La
  moyenne des jours de chaque mois redonne la série mensuelle NASA POWER des
  communes.
- Pluie de décembre 2025 : de 2005 à 2024, aucun jour de décembre ne dépasse
  3 mm sur les 398 localités ; en décembre 2025, NASA POWER sert un épisode
  sur l'ouest et le sud-ouest, jusqu'à 514,64 mm le 2 décembre à Sidéradougou
  et Tiéfora, au-delà de la borne de 500 mm : ces deux valeurs, seuls écarts
  admis, sont écartées. Les autres jours de décembre 2025 au-dessus de 3 mm
  (jusqu'à 472,8 mm le 2, jusqu'à 13,3 mm les 3, 13 et 14) sont gardés tels
  que servis et signalés dans la note de 125 communes et de 13 provinces
  (notes de la migration 0010 complétées). Les valeurs
  au-dessus du record national de 263 mm (Kpuéré, 345,4 mm le 12 août 2022 ;
  Sidéradougou et Tiéfora, 275,2 mm le 15 juin 2025) sont signalées aussi.
- Le proxy de salissure et le PR réaliste exigent une pluie sans trou. Le lot
  des particules fines aux communes devra compter 0 mm un jour de pluie sans
  valeur (aucun nettoyage) et le signaler dans la réponse : à Sidéradougou et
  Tiéfora, le 2 décembre 2025 tombe en saison sèche.
- Une série dense n'a ni statut éditorial ni override de confiance par
  mesure ; la passer en stockage versionné demanderait de la recharger dans
  `mesures_ressource`.
- Projection pour la suite du jalon : CAMS Radiation journalier aux
  398 localités (cinq grandeurs, une série propre par localité) donnerait
  environ 42 000 lignes, 70 Mo et une trentaine de secondes de migration, et
  30 Mo de fichiers ; CAMS EAC4 aux communes (particules fines et aérosols,
  51 mailles), quelques milliers de lignes. La CI garde sa marge.
