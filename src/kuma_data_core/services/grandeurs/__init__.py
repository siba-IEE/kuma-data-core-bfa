"""Couche service de calcul des grandeurs Kuma.

Un module par grandeur calculée à la volée (POA, productibles, énergie ECS,
degrés-jours, P50/P90, salissure, PR réaliste) : des fonctions pures, sans
accès à la base, appelées par les routes de ``/v1/grandeurs``.

Les grandeurs dérivées gardées en base ne passent pas par ces modules : la
migration 0009 calcule en SQL la fraction diffuse et les écarts entre sources
(ADR-0012), la migration 0014 la dégénérescence de pixel (ADR-0016).
"""
