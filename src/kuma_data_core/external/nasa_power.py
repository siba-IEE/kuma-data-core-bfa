"""Client HTTP synchrone pour l'API NASA POWER.

Fournit ``fetch_hourly``, qui rend un objet pydantic typé
``NasaPowerResponse`` : c'est le client du relais horaire de
``/v1/horaire`` (``services/horaire.py`` convertit la réponse). Les scripts
``scripts/ingest_nasa_power_*.py`` interrogent l'API par
``external/_http_retry.py`` sans passer par ce module.

Endpoint utilisé (communauté Renewable Energy par défaut) :
https://power.larc.nasa.gov/api/temporal/hourly/point

NASA POWER accepte 15 paramètres au plus en horaire (cf. doc officielle) ;
pas de garde-fou applicatif.

Sentinelle valeur manquante : ``-999.0`` (header NASA POWER
``fill_value``), exposée comme constante ``SENTINELLE_VALEUR_MANQUANTE``.

Gestion d'erreurs (cf. ``kuma_data_core.exceptions``) :

- HTTP non-2xx : ``NasaPowerHttpError`` (+ sous-type
  ``NasaPowerRateLimitError`` pour 429).
- Payload JSON invalide ou non conforme schéma pydantic :
  ``NasaPowerPayloadError``.
- Timeout réseau : ``NasaPowerTimeoutError``.

Les réponses 429 et 503 et les timeouts sont retentés par
``external/_http_retry.py`` avant que l'erreur soit levée.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerPayloadError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external._http_retry import (
    RETRY_BACKOFF_SECONDES,
    HttpRetryHttpError,
    HttpRetryRateLimitError,
    HttpRetryTimeoutError,
    executer_get_avec_retry,
)

# === Constantes ============================================================

BASE_URL: str = "https://power.larc.nasa.gov/api/temporal"
"""URL racine de l'API NASA POWER. L'endpoint horaire en est un sous-chemin."""

DEFAULT_COMMUNITY: str = "RE"
"""Communauté NASA POWER par défaut : Renewable Energy. Cohérent avec
le focus solaire."""

DEFAULT_TIMEOUT: float = 30.0
"""Timeout HTTP par défaut (latence P95 < 30 s)."""

SENTINELLE_VALEUR_MANQUANTE: float = -999.0
"""Valeur sentinelle utilisée par NASA POWER pour les données
manquantes (cf. header ``fill_value`` de la réponse)."""

# Note : le retry vit canoniquement dans ``external/_http_retry.py`` ;
# le wrapper local ``_executer_get_avec_retry`` ci-dessous ne fait que
# le brancher au défaut ``RETRY_BACKOFF_SECONDES``.


# === Schémas pydantic ======================================================


class _ConfigPermissive:
    """Configuration pydantic permissive : ignore les champs inattendus du payload."""

    model_config = ConfigDict(extra="ignore")


class NasaPowerGeometry(_ConfigPermissive, BaseModel):
    type: Literal["Point"]
    coordinates: tuple[float, float, float]


class NasaPowerApiInfo(_ConfigPermissive, BaseModel):
    version: str
    name: str


class NasaPowerHeader(_ConfigPermissive, BaseModel):
    """En-tête de la réponse NASA POWER.

    ``sources`` peut être absent ou de structure variable ; typage souple
    en ``list[str | dict[str, str]] | None``.
    """

    title: str
    api: NasaPowerApiInfo
    fill_value: float
    time_standard: str | None = None
    start: str
    end: str
    sources: list[str | dict[str, str]] | None = None


class NasaPowerParameterMeta(_ConfigPermissive, BaseModel):
    units: str
    longname: str


class NasaPowerProperties(_ConfigPermissive, BaseModel):
    """Conteneur des valeurs temporelles par paramètre.

    Structure : ``{nom_parametre: {clé_date: valeur}}``.

    - Clé date de la réponse horaire : ``"YYYYMMDDHH"``.
    - Valeurs : ``float``. La sentinelle ``-999.0`` indique une donnée
      manquante (cf. ``SENTINELLE_VALEUR_MANQUANTE``).
    """

    parameter: dict[str, dict[str, float]]


class NasaPowerResponse(_ConfigPermissive, BaseModel):
    """Réponse complète NASA POWER (GeoJSON Feature enrichi)."""

    type: Literal["Feature"]
    geometry: NasaPowerGeometry
    properties: NasaPowerProperties
    header: NasaPowerHeader
    parameters: dict[str, NasaPowerParameterMeta]
    messages: list[str] = Field(default_factory=list)


# === Fonctions de fetch ====================================================


def _format_date_yyyymmdd(d: date) -> str:
    """Formate une date au format ``YYYYMMDD`` (paramètres ``start``/``end``)."""
    return d.strftime("%Y%m%d")


def _construire_url_et_params(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start_str: str,
    end_str: str,
    community: str,
    time_standard: str,
) -> tuple[str, dict[str, str]]:
    """Construit l'URL complète et les query params d'un appel horaire NASA POWER."""
    url = f"{BASE_URL}/hourly/point"
    query_params: dict[str, str] = {
        "parameters": ",".join(parameters),
        "community": community,
        "latitude": str(latitude),
        "longitude": str(longitude),
        "start": start_str,
        "end": end_str,
        "format": "JSON",
        "time-standard": time_standard,
    }
    return url, query_params


def _executer_get_avec_retry(
    *,
    client: httpx.Client,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    retry_backoff_seconds: tuple[float, ...] = RETRY_BACKOFF_SECONDES,
) -> httpx.Response:
    """Wrapper local sur le helper partagé ``external/_http_retry.py``.

    Rôle : rétrocompat tests (les tests T-RETRY importent ce symbole depuis
    ce module) + conversion aux frontières des exceptions génériques
    ``HttpRetry*Error`` vers les exceptions NASA POWER via ``raise ... from exc``.
    """
    try:
        return executer_get_avec_retry(
            client=client,
            url=url,
            query_params=query_params,
            timeout=timeout,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    except HttpRetryRateLimitError as exc:
        raise NasaPowerRateLimitError(
            status_code=exc.status_code,
            url=exc.url,
            body=exc.body,
        ) from exc
    except HttpRetryHttpError as exc:
        raise NasaPowerHttpError(
            status_code=exc.status_code,
            url=exc.url,
            body=exc.body,
        ) from exc
    except HttpRetryTimeoutError as exc:
        raise NasaPowerTimeoutError(
            url=exc.url,
            timeout_seconds=exc.timeout_seconds,
        ) from exc


def _executer_requete(
    *,
    url: str,
    query_params: dict[str, str],
    timeout: float,
    httpx_client: httpx.Client | None,
) -> NasaPowerResponse:
    """Exécute l'appel HTTP avec retry transverse puis parse la réponse.

    Si ``httpx_client`` est fourni (tests ``httpx.MockTransport``), il est
    utilisé tel quel ; sinon un client temporaire est créé. Le retry sur
    429/503/timeout est délégué à ``_executer_get_avec_retry`` ; les statuts
    >= 400 terminaux, le JSON non parsable et le payload hors schéma sont
    traités ici. Toutes les erreurs sont remontées comme sous-types de
    ``NasaPowerError``.
    """
    client_fourni = httpx_client is not None
    client = httpx_client if httpx_client is not None else httpx.Client(timeout=timeout)
    try:
        response = _executer_get_avec_retry(
            client=client,
            url=url,
            query_params=query_params,
            timeout=timeout,
        )

        url_complete = str(response.request.url)

        if response.status_code >= 400:
            raise NasaPowerHttpError(
                status_code=response.status_code, url=url_complete, body=response.text
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise NasaPowerPayloadError(
                message="Réponse non parsable en JSON",
                url=url_complete,
                body=response.text,
            ) from exc
    finally:
        if not client_fourni:
            client.close()

    try:
        return NasaPowerResponse.model_validate(payload)
    except ValidationError as exc:
        raise NasaPowerPayloadError(
            message=f"Payload ne respecte pas le schéma NasaPowerResponse : {exc}",
            url=url,
            body=str(payload)[:500],
        ) from exc


def fetch_hourly(
    *,
    latitude: float,
    longitude: float,
    parameters: Sequence[str],
    start: date,
    end: date,
    community: str = DEFAULT_COMMUNITY,
    timeout: float = DEFAULT_TIMEOUT,
    time_standard: str = "UTC",
    httpx_client: httpx.Client | None = None,
) -> NasaPowerResponse:
    """Récupère des séries horaires NASA POWER pour un point.

    Les paramètres ``start`` et ``end`` sont des dates (granularité jour) :
    NASA POWER renvoie toutes les heures comprises entre ``start 00:00``
    et ``end 23:00`` (UTC ou LST selon ``time_standard``). Constat
    empirique : le format YYYYMMDDHH initialement testé est rejeté par
    l'endpoint avec HTTP 422 ; YYYYMMDD est la forme acceptée.

    Args:
        latitude: latitude WGS84 en degrés décimaux (positif Nord).
        longitude: longitude WGS84 en degrés décimaux (positif Est).
        parameters: codes NASA POWER à demander (max 15 selon doc pour
            la granularité horaire).
        start: date de début (incluse, toutes heures à partir de 00:00).
        end: date de fin (incluse, toutes heures jusqu'à 23:00).
        community: communauté NASA POWER (``RE`` par défaut).
        timeout: timeout HTTP en secondes.
        time_standard: ``"UTC"`` (par défaut) ou ``"LST"`` (Local
            Solar Time).
        httpx_client: client httpx injectable.

    Returns:
        ``NasaPowerResponse`` parsé et validé. Les clés de
        ``properties.parameter[<nom>]`` sont au format ``YYYYMMDDHH``.

    Raises:
        NasaPowerTimeoutError, NasaPowerRateLimitError,
        NasaPowerHttpError, NasaPowerPayloadError.
    """
    url, query_params = _construire_url_et_params(
        latitude=latitude,
        longitude=longitude,
        parameters=parameters,
        start_str=_format_date_yyyymmdd(start),
        end_str=_format_date_yyyymmdd(end),
        community=community,
        time_standard=time_standard,
    )
    return _executer_requete(
        url=url, query_params=query_params, timeout=timeout, httpx_client=httpx_client
    )
