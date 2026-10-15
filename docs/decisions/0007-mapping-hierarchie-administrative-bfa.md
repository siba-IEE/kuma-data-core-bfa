# ADR-0007 : mapping de la hiérarchie administrative du Burkina Faso

Date : 2026-10-15. Statut : accepté.

## Contexte

Le moteur range toute localité sur sept niveaux génériques (`type_localite`) :
`continent`, `region_supranationale`, `pays`, `region_administrative`,
`prefecture`, `commune`, `site`. Ajouter un pays ne demande aucune migration de
schéma : l'identité nationale est portée par la donnée (`nom`, `code`,
`notes`), pas par l'énumération.

Le Burkina Faso est découpé en régions, provinces, départements et villages. Le
découpage en vigueur a été adopté en Conseil des ministres le 2 juillet 2025 et
fixé par deux décrets signés le 7 août 2025 :

- n°2025-1012/PF/PRIM/MATM/MEF, réorganisation du territoire (composition en
  annexe II) ;
- n°2025-1003/PF/PRIM/MATM/MEF, dénominations des régions et de cinq provinces.

Le pays passe de 13 à 17 régions et de 45 à 47 provinces, pour 350
départements. Les régions Boucle du Mouhoun, Est et Sahel sont scindées ; les
dix autres sont renommées sans changement de limites. Les provinces Dyamongou
(Botou, Kantchari) et Karo-Peli (Arbinda, Koutougou) sont créées à partir des
provinces Tapoa et Soum. Cinq provinces sont renommées : Kossi en Koosin,
Oubritenga en Bassitenga, Sanmatenga en Sandbondtenga, Soum en Djelgodji,
Tapoa en Gobnangou.

L'article 6 du décret 2025-1012 omet les départements de Tambaga et
Tongomayel, que l'annexe II inclut. Seule l'annexe II totalise 350
départements ; c'est elle qui est retenue.

La norme ISO 3166-2:BF décrit encore le découpage de 2001. Ses codes de région
ne désignent plus aucune région ; ses codes de province restent valables pour
les provinces dont l'emprise n'a pas changé.

Sources : décrets signés, publiés par Wakat Séra le 19 août 2025
(<https://www.wakatsera.com/burkina-les-decrets-de-reorganisation-du-territoire-et-changement-de-denomination-de-provinces-et-de-regions/>) ;
compte rendu du Conseil des ministres n°022 du 2 juillet 2025
(<https://gouvernement.gov.bf/conseil-des-ministres/conseil-des-ministres-n22-du-02-juillet-2025/>).

## Décision

Le niveau suit la profondeur dans la hiérarchie.

| Palier | `type_localite` | Effectif | Lot |
|---|---|---|---|
| Région | `region_administrative` | 17 | 0.1.0 |
| Province | `prefecture` | 47 | 0.1.0 |
| Département | `commune` | 350 | 0.2.0 |
| Commune de Ouagadougou | `commune` | 1 | 0.2.0 |
| Village | `site` | | au besoin |

La commune de Ouagadougou, à statut particulier, n'appartient à aucun
département : elle est placée au niveau `commune`, sous la province du
Kadiogo, à côté des six départements de celle-ci.

Le niveau `prefecture` porte le nom d'un palier guinéen ; ici, il contient les
provinces. Le libellé du palier se lit dans `nom` et `notes`, pas dans
`type_localite`.

Codes métier : `bfa` pour le pays, `bfa_<slug>` pour les régions,
`bfa_prov_<slug>` pour les provinces. Le slug est le nom en ASCII minuscule
(« Djôrô » donne `djoro`). Le préfixe `prov_` évite la collision entre une
région et une province de même nom (Kadiogo, Sourou). Les départements sont
codés `bfa_dep_<slug>` ; un nom porté par deux départements (Boussouma,
Namissiguima) reçoit le slug de sa province en suffixe. La commune de
Ouagadougou est codée `bfa_com_ouagadougou`.

`code_administratif_national` porte le sous-code ISO 3166-2:BF à trois lettres
des 43 provinces dont l'emprise n'a pas changé, provinces renommées comprises.
Il reste vide pour les régions, pour Djelgodji et Gobnangou (réduites en 2025)
et pour Dyamongou et Karo-Peli (créées). Les anciens codes sont cités dans
`notes`.

Graphie : celle des décrets pour les entités renommées ou créées, dont la
région Koulsé (« Kuilsé » dans le communiqué du 2 juillet 2025). Les provinces
non renommées gardent leur graphie usuelle (INSD, ISO) ; celle de l'annexe II
(Lorum, Koulpelogo, Kourittenga) est citée en variante. Pour un département,
qu'aucun décret ne renomme, on retient la graphie que partagent au moins deux
des trois sources (INSD, annexe II, Wikidata), à défaut celle de l'INSD ; les
autres sont citées en variante.

Population : RGPH 2019 (INSD). Une entité inchangée reprend son chiffre ; une
entité créée ou modifiée reçoit la somme de ses composantes, seulement si la
composition est certaine. Un département reprend la population de la commune
de même nom (tableau 60) ; Bobo-Dioulasso et Ouagadougou, la somme de leurs
arrondissements. Les 38 communes non ou partiellement dénombrées en 2019, dont
l'INSD a estimé ou complété l'effectif par modélisation, le disent en note.

## Conséquences

- Aucune migration de schéma.
- Une mise à jour de la norme ISO pourra compléter `code_administratif_national`
  sans changer les codes métier.
