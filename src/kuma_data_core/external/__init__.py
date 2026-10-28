"""Accès HTTP aux API externes.

- ``nasa_power`` : client typé de l'API horaire NASA POWER, appelé par le
  relais de ``/v1/horaire``.
- ``_http_retry`` : GET avec retry transverse, partagé par ce client et par
  les scripts d'ingestion NASA POWER et PVGIS.
"""
