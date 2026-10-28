"""Schémas Pydantic des endpoints `/api/v1/horaire/<localite>/<grandeur>`.

Cinq schémas pour le passe-plat horaire :

- :class:`ParametresHoraire` : paramètres communs (localité, grandeur,
  plage temporelle, format de sortie, source de la série stockée).
- :class:`ResultatHoraire` : un point horaire passe-plat (instant ISO,
  valeur ou null, unité, statut éditorial).
- :class:`PlageTemporelle` : helper structurel pour les plages
  temporelles inclusives.
- :class:`ReponseHoraire` : réponse complète d'un endpoint data, avec la
  source de la série servie.
- :class:`ReponseDisponibilite` : réponse de l'endpoint
  ``/disponibilite``.

Une localité peut porter plusieurs séries horaires de la même grandeur :
le paramètre ``source`` choisit la série, le champ ``source`` de la réponse
nomme celle qui a servi (ADR-0023). Le statut éditorial
``passe_plat_non_valide`` signale une donnée relayée, non validée par Kuma.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# === Constantes module ====================================================


PLAGE_MAX_JOURS: int = 366
"""Plage temporelle maximale par requête (année bissextile incluse)."""

DATE_DEBUT_DISPONIBILITE: date = date(2001, 1, 1)
"""Borne historique de début de la disponibilité passe-plat horaire."""


# === Schémas paramètres ===================================================


SourceHoraire = Literal["nasa_power", "cams_radiation"]
"""Sources des séries horaires (ADR-0023)."""


class ParametresHoraire(BaseModel):
    """Paramètres communs aux endpoints du passe-plat horaire.

    Le champ ``format_sortie`` est exposé en query string sous le nom
    URL ``format`` via ``Query(alias="format")`` côté handler - alias
    nécessaire pour éviter le shadow du built-in Python ``format``.
    """

    # Toute localité du référentiel, par son code complet
    # (ex. bfa_com_ouagadougou), vérifiée par le handler contre la table.
    localite: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    grandeur: Literal[
        "ghi",
        "dni",
        "dhi",
        "ghi_ciel_clair",
        "t2m",
        "rh2m",
        "kt",
        "vent_2m",
        "vent_10m",
        "precipitation",
    ]
    periode_debut: date = Field(..., ge=DATE_DEBUT_DISPONIBILITE)
    periode_fin: date
    format_sortie: Literal["json", "csv"] = Field(
        default="json",
        alias="format",
        description="Format de reponse : 'json' (defaut) ou 'csv'.",
    )
    source: SourceHoraire | None = Field(
        default=None,
        description=(
            "Source de la serie horaire stockee. Par defaut, NASA POWER, source du relais. "
            "Avec 'cams_radiation', seule la serie stockee est servie, sans relais si elle ne "
            "couvre pas la plage (ADR-0023)."
        ),
    )

    @model_validator(mode="after")
    def _valider_plage_temporelle(self) -> ParametresHoraire:
        if self.periode_fin < self.periode_debut:
            raise ValueError("periode_fin doit etre superieure ou egale a periode_debut")
        if (self.periode_fin - self.periode_debut).days > PLAGE_MAX_JOURS:
            raise ValueError(f"plage maximale {PLAGE_MAX_JOURS} jours par requete")
        return self


# === Schémas résultats ====================================================


class PlageTemporelle(BaseModel):
    """Plage temporelle inclusive [début, fin]."""

    debut: date
    fin: date


class ResultatHoraire(BaseModel):
    """Un point horaire (24 par jour, fuseau UTC).

    ``statut_editorial`` distingue les deux régimes de service :

    - ``valide_auto`` : donnée horaire **stockée et validée** par le
      contrôle qualité algorithmique Kuma (confiance B).
    - ``passe_plat_non_valide`` : donnée relayée à la volée (passe-plat),
      non validée éditorialement - servie en repli là où aucune donnée
      validée ne couvre la plage demandée.
    """

    instant: datetime
    valeur: float | None = Field(
        default=None,
        description=(
            "Valeur numerique ou null si donnee manquante (sentinelle "
            "amont ou indice physique non defini selon la grandeur)."
        ),
    )
    unite: str
    statut_editorial: Literal["valide_auto", "passe_plat_non_valide"] = "passe_plat_non_valide"


# === Schémas réponses =====================================================


class ReponseHoraire(BaseModel):
    """Réponse complète d'un endpoint passe-plat horaire data."""

    localite: str
    grandeur: str
    source: str = Field(
        description="Source de la serie servie (stockee ou relayee), ex. 'nasa_power'."
    )
    periode_demandee: PlageTemporelle
    resultats: list[ResultatHoraire]


class ReponseDisponibilite(BaseModel):
    """Réponse de l'endpoint `/disponibilite`."""

    localite: str
    grandeur: str
    source: str = Field(
        description="Source dont la plage est donnee : relais (nasa_power) ou serie stockee."
    )
    plage_disponible: PlageTemporelle
    statut_editorial: Literal["valide_auto", "passe_plat_non_valide"] = "passe_plat_non_valide"
