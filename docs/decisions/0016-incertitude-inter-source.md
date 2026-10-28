# ADR-0016 : fiche d'incertitude inter-source

Date : 2026-10-27. Statut : accepté.

## Contexte

L'endpoint `/v1/grandeurs/incertitude_inter_source`, hérité du dépôt
d'origine, assemble pour une localité deux indications distinctes : l'écart
entre sources et la dégénérescence de pixel, c'est-à-dire le nombre d'autres
localités qui lisent la même maille NASA POWER. Il lisait deux grandeurs que
seul le dépôt d'origine calculait (`ecart_relatif_referentiel`,
`ecart_relatif_dni_cams`) sur 2021-2023 et une dégénérescence jamais
calculée au Burkina Faso : il répondait 404 partout. Les sept écarts
mensuels à NASA POWER de l'ADR-0012 étaient gravés mais ignorés.

## Décision

- Sept paires, celles de l'ADR-0012 : GHI et DNI de SARAH-3, d'ERA5 et de
  CAMS, DHI de CAMS, chacun comparé à NASA POWER, `(source - NASA) / NASA`.
  Fenêtre commune 2005-2023 : SARAH-3 et ERA5 s'arrêtent en 2023, et une
  fenêtre commune évite de comparer des paires sur des années différentes.
  Pour chaque paire, la médiane des écarts mensuels en valeur absolue (signal
  principal) et leur moyenne signée (orientation seulement), calculées en
  base.
- Dégénérescence de pixel matérialisée par la migration 0014 : pour chaque
  localité, nombre d'autres localités du référentiel dont la série mensuelle
  GHI NASA POWER 1991-2025 est identique, donc dans la même maille CERES de 1°.
  Une ligne statique par localité, confiance B, la liste des jumeaux en
  commentaire. GHI, DNI et DHI partagent cette grille. 398 lignes : le
  trigger d'audit reste actif.
- La collection lit une page de fiches en trois requêtes (périmètre, écarts,
  dégénérescence), au lieu de quatre par localité.
- Le texte d'avertissement de la fiche rappelle que SARAH-3 et CAMS
  partagent l'imagerie Meteosat : leur accord ne vaut pas confirmation
  indépendante (ADR-0011).

## Conséquences

- 398 fiches, une par province et par commune. Au Kadiogo : écart médian de
  7,2 % pour le GHI de SARAH-3, 4,7 % pour celui d'ERA5, 2,7 % pour celui de
  CAMS ; 46,8 %, 63,8 % et 21,4 % pour le DNI ; 5,1 % pour le DHI de CAMS.
- Sur les 398 localités, la médiane de ces écarts va de 3,4 % (GHI de CAMS) à
  63,5 % (DNI d'ERA5). Pour le DNI, la moyenne signée des écarts mensuels est
  positive dans toutes les localités et pour les trois sources : de 15 % à
  103 % selon la source et la localité (moyenne d'écarts, à ne pas confondre
  avec le rapport des moyennes, ADR-0012).
- 33 mailles NASA POWER pour 398 localités : 17,8 jumeaux en moyenne, 32 au
  plus (la maille de Ouagadougou réunit 33 localités, dont quatre
  provinces) ; seuls les départements de Botou et de Mangodara ont leur
  maille à eux. Les 47 provinces tiennent dans 24 mailles.
- Une fiche répond en 0,1 s, la collection complète en moins d'une seconde.
- Un écart ne dit pas quelle source a raison, et la fiche n'est pas une barre
  d'erreur calibrée au sol : seules les stations du jalon 4 le permettront.
