# ADR-0008 : règle de sélection des coordonnées Wikidata

Date : 2026-10-15. Statut : accepté.

## Contexte

Les coordonnées des localités viennent de Wikidata (propriété `P625`), sans
valeur inventée ; à défaut de point Wikidata valable, une commune reçoit le
centroïde de son contour officiel. Trois cas se présentent : un seul point,
plusieurs points de rangs différents, ou un point manifestement faux. Le
découpage de 2025 (ADR-0007) en ajoute un quatrième : des éléments Wikidata
d'avant 2025, renommés en place, dont le point décrit une emprise qui a changé
(ex-régions Boucle du Mouhoun, Est et Sahel, ex-province Soum). Certaines
entités créées en 2025 n'ont pas encore d'élément, ou un élément sans point.

## Décision

1. L'élément retenu doit désigner l'entité du bon niveau (`P31`), et non une
   ville ou un département homonyme.
2. Parmi plusieurs `P625`, on retient le rang `preferred`, sinon le premier
   statement `normal` dans l'ordre de l'API `wbgetentities`. Le rang
   `deprecated` est exclu.
3. Si le point est faux (hors de l'entité, ou décrivant une emprise d'avant
   2025), ou si l'entité n'a pas d'élément ou pas de point, on retient le
   `P625` du chef-lieu. La note de la localité le dit, avec le motif.
4. Pour les communes, un point est jugé hors de l'entité s'il tombe hors de
   son contour au-delà d'une marge de 2 km, selon le jeu COD-AB de l'IGB
   (version v03, valide au 1er août 2025, publié par OCHA sous licence
   CC BY-IGO, <https://data.humdata.org/dataset/cod-ab-bfa>). On essaie alors,
   dans l'ordre, les autres statements de l'élément, le point du chef-lieu,
   puis le centroïde du contour COD-AB, cité avec son p-code.
5. Toute coordonnée tombe dans l'enveloppe du pays (latitude 9,3 à 15,1,
   longitude −5,6 à 2,5), et deux localités de même niveau ne partagent pas un
   point. Les deux contrôles sont des tests d'intégration.

Une région et une province de même chef-lieu peuvent partager un point.

## Conséquences

- Dans le lot 0.1.0, 12 des 64 régions et provinces prennent le point de leur
  chef-lieu. Dans le lot 0.2.0, sur 351 communes, 339 prennent le premier
  point de leur élément, 2 un autre statement, 8 le point du chef-lieu et 2 le
  centroïde du contour.
- Une correction en amont (élément mis à jour, point corrigé) se reprend par
  une migration de correction, sans changer la règle.
