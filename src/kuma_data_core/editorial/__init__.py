"""Couche service des workflows éditoriaux Kuma Data Core.

Mécaniques transverses du statut éditorial et du niveau de confiance A/B/C.

Sous-modules :

- ``statuts`` : machine d'état du statut éditorial des données métier.
- ``niveaux_confiance`` : dérivation et override des niveaux A/B/C.

Toutes les exceptions levées par ces modules dérivent de
``kuma_data_core.exceptions.EditorialeError`` (racine).
"""
