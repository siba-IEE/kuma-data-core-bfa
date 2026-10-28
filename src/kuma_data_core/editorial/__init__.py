"""Couche service des workflows éditoriaux Kuma Data Core.

Mécaniques transverses : statut éditorial, versioning temporel et niveau de
confiance A/B/C.

Sous-modules :

- ``statuts`` : machine d'état du statut éditorial des données métier.
- ``versioning`` : rotation versionnée atomique des lignes.
- ``niveaux_confiance`` : dérivation et override des niveaux A/B/C.

Les exceptions de ``statuts`` et de ``niveaux_confiance`` dérivent de
``kuma_data_core.exceptions.EditorialeError`` (racine) ; ``versioning`` lève
``ValueError`` sur une rotation qui changerait l'identité métier.
"""
