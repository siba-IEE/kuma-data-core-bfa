"""Couche service de calcul des grandeurs Kuma.

Un module par grandeur. Les grandeurs calculées à la volée (POA, productibles,
énergie ECS, degrés-jours, P50/P90, salissure, PR réaliste) sont des fonctions
pures appelées par les routes de ``/v1/grandeurs``. Les modules des grandeurs
stockées lisent les mesures amont, agrègent selon la formule de la fiche
méthodologique et insèrent dans ``grandeurs_metier``.

Au Burkina Faso, la fraction diffuse et les écarts entre sources sont calculés
en SQL par la migration 0009 (ADR-0012), la dégénérescence de pixel par la
migration 0014 (ADR-0016). Les modules ``hep``, ``humidex``,
``variabilite_journaliere``, ``productible_specifique_*``,
``indicateur_qualite_donnees``, ``fraction_diffuse``, ``ecart_dni_cams``,
``degenerescence_pixel`` et ``referentiels``, hérités de l'instance d'origine,
ne sont appelés nulle part ici.
"""
