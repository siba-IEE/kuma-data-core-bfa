# Généricité pays

Note d'architecture à l'intention des contributeurs : **le Core ingère la
donnée solaire brute de n'importe quel pays.** Cette instance sert le Burkina
Faso ; rien dans le schéma n'est propre à ce pays.

## Le pays est un axe de classification

Il n'y a aucune notion de pays câblée en dur. Les localités forment une
hiérarchie à sept niveaux :

`continent`, `region_supranationale`, `pays`, `region_administrative`,
`prefecture`, `commune`, `site`.

Le pays est un niveau de cette hiérarchie. Chaque localité porte un code
`pays_iso3` (ISO 3166-1 alpha-3) et un code métier préfixé du code pays
(`bfa_kadiogo` pour une région, `bfa_prov_kadiogo` pour une province,
`bfa_dep_dori` pour un département, ADR-0007). La cohérence parent-enfant est
validée côté base.

Les noms de niveaux viennent du premier pays servi par le moteur : au Burkina
Faso, le niveau `prefecture` porte les provinces. Le palier d'une localité se
lit dans son nom et ses notes, pas dans `type_localite` (ADR-0007).

## Ce qu'un nouveau pays branche

Le socle est partagé : sources, grandeurs, unités, confiance, statut,
versionnement, audit. Ajouter un pays revient à :

1. créer ses localités (la racine pays, puis ses descendants) ;
2. rattacher ses sources, ses séries et ses mesures ;
3. laisser la machinerie de confiance et de statut s'appliquer telle quelle.

Aucune migration de schéma n'est nécessaire pour un nouveau pays.

## Une instance par pays

Chaque pays a son dépôt d'instance, qui repart du moteur commun
([Kuma Data Core](https://github.com/siba-IEE/kuma-data-core)) sur un socle
sans donnée d'une autre instance. Ce dépôt est celui du Burkina Faso.

Pour contribuer des données ou une station, voir
[amener son pays ou sa station](pays-et-terrain.md).
