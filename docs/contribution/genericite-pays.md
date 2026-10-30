# Généricité pays

Le schéma accepte les données solaires de n'importe quel pays : rien n'y est
propre au Burkina Faso.

## Le pays est un niveau de localité

Aucune notion de pays n'est codée en dur. Les localités forment une
hiérarchie à sept niveaux :

`continent`, `region_supranationale`, `pays`, `region_administrative`,
`prefecture`, `commune`, `site`.

Le pays est un niveau de cette hiérarchie. Chaque localité a un code
`pays_iso3` (ISO 3166-1 alpha-3) et un code métier préfixé du code pays
(`bfa_kadiogo` pour une région, `bfa_prov_kadiogo` pour une province,
`bfa_dep_dori` pour un département, ADR-0007). La base vérifie la cohérence
entre parent et enfant.

Les noms de niveaux viennent du premier pays traité par le moteur : au Burkina
Faso, le niveau `prefecture` contient les provinces. Le rang administratif
d'une localité se lit dans son nom et ses notes, pas dans `type_localite`
(ADR-0007).

## Ajouter un pays

Les sources, les grandeurs, les unités, les règles de confiance et de statut,
les versions et l'audit sont communs à tous les pays. Ajouter un pays revient
à :

1. créer ses localités (la racine pays, puis ses descendants) ;
2. rattacher ses sources, ses séries et ses mesures ;
3. laisser les règles de confiance et de statut s'appliquer sans les modifier.

Aucune migration de schéma n'est nécessaire pour un nouveau pays.

## Un dépôt par pays

Chaque pays a son propre dépôt, créé à partir de
[Kuma Data Core](https://github.com/siba-IEE/kuma-data-core) sans les données
des autres pays. Ce dépôt est celui du Burkina Faso.

Pour contribuer des données ou une station, voir
[amener son pays ou sa station](pays-et-terrain.md).
