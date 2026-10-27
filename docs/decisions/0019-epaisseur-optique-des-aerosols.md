# ADR-0019 : épaisseur optique des aérosols

Date : 2026-10-27. Statut : accepté.

## Contexte

Au Burkina Faso, les aérosols atténuent fortement le rayonnement en saison
sèche : poussières désertiques de l'harmattan et des soulèvements sahariens,
fumées des feux de végétation. Les particules fines de surface (ADR-0015,
ADR-0018) décrivent l'air au sol et la salissure des panneaux ; l'atténuation
du rayonnement dépend, elle, de la colonne entière, que mesure l'épaisseur
optique des aérosols (AOD). La réanalyse CAMS EAC4, déjà source des particules
fines, sert l'AOD à 550 nm totale et par espèce.

L'analyse EAC4 n'assimile que l'épaisseur optique totale (MODIS, et AATSR
jusqu'en 2012 ; Inness et al., 2019) : le partage entre espèces vient du
modèle, qui répartit entre elles la correction du total.

## Décision

- Trois grandeurs ajoutées au référentiel, stockées, sans unité :
  `aod550` (épaisseur optique totale à 550 nm), `aod550_poussiere`
  (poussières désertiques) et `aod550_organique` (matière organique). Les
  autres espèces (carbone suie, sulfates, sels marins) ne sont pas ingérées
  séparément ; elles restent comprises dans le total.
- Séries journalières 2005-2025 aux 398 localités (lot `localites` : 47
  provinces et 351 communes), en stockage dense (ADR-0017). Même recette que
  les particules fines : maille de 0,75° la plus proche, moyenne des huit pas
  de 3 h du jour UTC, arrondi à 4 décimales. Méthode `reanalyse`, confiance B.
- Bornes : 0 inclus en bas ; 5, 5 et 2 en haut, soit 1,6, 1,95 et 2,1 fois
  les maxima servis aux localités (3,14 pour le total et 2,56 pour les
  poussières le 19 mars 2022 au nord, 0,94 pour la matière organique le
  9 novembre 2014 à Kompienga). Sur toute la grille servie, la matière
  organique atteint 1,55 (22 décembre 2008, dans une maille qu'aucune
  localité n'utilise) ; aucun pas de 3 h n'est servi à zéro. Aucun écart
  admis.
- Les notes publiques disent le partage modélisé : la matière organique ne
  vaut indicateur de fumées qu'au sud, de novembre à mars.
- Ingesteur `scripts/ingest_cams_eac4_journalier.py --famille aod --lot
  localites` : même forme de requête que les particules fines (zone, pas de
  3 h, une requête par année ou par bloc d'années, onze au plus), mêmes
  fonctions de cache et même recette, fichiers de cache propres
  (`cams_eac4_aod_<année>.zip`) ; migration 0018, qui met aussi à jour la
  fiche de la source `cams_eac4`.

## Conséquences

- 51 mailles servent les 398 localités, les mêmes que pour les communes
  seules ; chaque province lit la série d'une commune de sa maille.
  1 194 séries, dont 153 porteuses ; 3 213 lignes annuelles et
  1 173 510 valeurs ; 2,1 Mo de fichiers.
- Moyennes sur les 398 localités et sur 2005-2025 : AOD totale de 0,34, de
  0,21 en décembre à 0,52 en mars ; les poussières en font 55 %, la matière
  organique 31 %. Les poussières sont plus fortes au nord de 13,5 °N (0,23)
  qu'au sud de 10,5 °N (0,14), la matière organique au sud (0,13 contre 0,09).
  La somme des poussières et de la matière organique ne dépasse jamais le
  total.
- Au sud, de novembre à mars, la matière organique porte les fumées des feux
  (0,13 en moyenne, contre 0,06 au nord). De mars à juin et au nord, elle
  monte surtout avec les épisodes de poussières (trois fois plus les jours de
  forte poussière au nord), effet du partage modélisé : elle n'y est pas un
  indicateur de feux.
- Une AOD de maille de 0,75° moyenne la colonne sur une cinquantaine de
  kilomètres ; elle ne remplace pas une mesure photométrique au sol, qui
  viendra avec le terrain (jalon 5).
- Ces séries ne corrigent encore aucune grandeur calculée : elles servent à
  lire les écarts entre sources de rayonnement et la saisonnalité de la
  ressource.
