# ADR-0019 : épaisseur optique des aérosols

Date : 2026-10-27. Statut : accepté.

## Contexte

Au Burkina Faso, les aérosols pèsent sur la ressource solaire plus que les
nuages une bonne partie de l'année : poussières désertiques de l'harmattan et
des soulèvements sahariens, fumées des feux de végétation. Les particules
fines de surface (ADR-0015, ADR-0018) décrivent l'air au sol et la salissure
des panneaux ; l'atténuation du rayonnement dépend, elle, de la colonne
entière, que mesure l'épaisseur optique des aérosols (AOD). La réanalyse CAMS
EAC4, déjà source des particules fines, sert l'AOD à 550 nm totale et par
espèce.

## Décision

- Trois grandeurs ajoutées au référentiel, stockées, sans unité :
  `aod550` (épaisseur optique totale à 550 nm), `aod550_poussiere`
  (poussières désertiques) et `aod550_organique` (matière organique, feux de
  végétation surtout). Les autres espèces (carbone suie, sulfates, sels
  marins) ne sont pas ingérées séparément ; elles restent comprises dans le
  total.
- Séries journalières 2005-2025 aux 398 localités (lot `localites` : 47
  provinces et 351 communes), en stockage dense (ADR-0017). Même recette que
  les particules fines : maille de 0,75° la plus proche, moyenne des huit pas
  de 3 h du jour UTC, arrondi à 4 décimales. Méthode `reanalyse`, confiance B.
- Bornes : 0 inclus en bas ; 5, 5 et 2 en haut, au-dessus des maxima servis
  (3,14 pour le total et 2,56 pour les poussières le 19 mars 2022 au nord,
  0,94 pour la matière organique le 9 novembre 2014). Aucun écart admis.
- Ingesteur `scripts/ingest_cams_eac4_journalier.py --famille aod --lot
  localites`, qui partage avec les particules fines la requête annuelle,
  le cache et la recette ; migration 0018.

## Conséquences

- 51 mailles servent les 398 localités, les mêmes que pour les communes
  seules : 1 194 séries, dont 153 porteuses ; 3 213 lignes annuelles et
  1 173 510 valeurs ; 2,1 Mo de fichiers.
- Sur 2005-2025 : AOD totale de 0,34 en moyenne, de 0,22 en décembre à 0,52 en
  mars ; les poussières en font 56 %, la matière organique 31 %. Les
  poussières sont plus fortes au nord (0,24 contre 0,14 au sud), la matière
  organique au sud (0,13 contre 0,08). La somme des poussières et de la
  matière organique ne dépasse jamais le total.
- Une AOD de maille de 0,75° moyenne la colonne sur une cinquantaine de
  kilomètres ; elle ne remplace pas une mesure photométrique au sol, qui
  viendra avec le terrain (jalon 5).
- Ces séries ne corrigent encore aucune grandeur calculée : elles servent à
  lire les écarts entre sources de rayonnement et la saisonnalité de la
  ressource.
