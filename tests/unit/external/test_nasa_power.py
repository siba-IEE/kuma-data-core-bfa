"""Tests unitaires du client NASA POWER.

Couvre les chemins fonctionnels et erreurs de
``kuma_data_core.external.nasa_power`` via ``httpx.MockTransport``,
sans appel réseau réel. Les tests d'intégration avec NASA POWER
effective relèvent d'un script d'extraction dédié.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from kuma_data_core.exceptions import (
    NasaPowerHttpError,
    NasaPowerPayloadError,
    NasaPowerRateLimitError,
    NasaPowerTimeoutError,
)
from kuma_data_core.external.nasa_power import (
    BASE_URL,
    DEFAULT_COMMUNITY,
    SENTINELLE_VALEUR_MANQUANTE,
    NasaPowerResponse,
    fetch_hourly,
)

pytestmark = pytest.mark.unit

_LATITUDE: float = 12.35
_LONGITUDE: float = -1.51666667


# ---------------------------------------------------------------------------
# Payload de référence (Ouagadougou, 1er juillet 2024, 2 paramètres)
# ---------------------------------------------------------------------------


def _payload_horaire_valide() -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [_LONGITUDE, _LATITUDE, 306.0],
        },
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"2024070100": 0.0, "2024070112": 812.4},
                "T2M": {"2024070100": 27.1, "2024070112": 33.6},
            }
        },
        "header": {
            "title": "NASA/POWER Source Native Resolution Hourly Data",
            "api": {"version": "v2.10.2", "name": "POWER Hourly API"},
            "fill_value": -999.0,
            "time_standard": "UTC",
            "start": "20240701",
            "end": "20240701",
            "sources": ["MERRA-2", "CERES SYN1deg"],
        },
        "parameters": {
            "ALLSKY_SFC_SW_DWN": {
                "units": "Wh/m^2",
                "longname": "All Sky Surface Shortwave Downward Irradiance",
            },
            "T2M": {"units": "C", "longname": "Temperature at 2 Meters"},
        },
        "messages": [],
    }


def _client_avec_handler(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _appeler(client: httpx.Client, **options: Any) -> NasaPowerResponse:
    return fetch_hourly(
        latitude=_LATITUDE,
        longitude=_LONGITUDE,
        parameters=["ALLSKY_SFC_SW_DWN", "T2M"],
        start=date(2024, 7, 1),
        end=date(2024, 7, 1),
        httpx_client=client,
        **options,
    )


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_fetch_hourly_happy_path_parse_le_payload() -> None:
    payload = _payload_horaire_valide()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json=payload)

    with _client_avec_handler(httpx.MockTransport(handler)) as client:
        result = _appeler(client)

    assert isinstance(result, NasaPowerResponse)
    assert result.geometry.coordinates == (_LONGITUDE, _LATITUDE, 306.0)
    assert result.properties.parameter["ALLSKY_SFC_SW_DWN"]["2024070112"] == 812.4
    assert result.header.fill_value == SENTINELLE_VALEUR_MANQUANTE
    assert result.parameters["ALLSKY_SFC_SW_DWN"].units == "Wh/m^2"


def test_fetch_hourly_construit_lurl_avec_format_yyyymmdd_et_time_standard() -> None:
    """L'endpoint hourly accepte les paramètres
    ``start``/``end`` au format ``YYYYMMDD``, pas ``YYYYMMDDHH``. Les
    clés de réponse restent en ``YYYYMMDDHH``.
    """
    urls_appelees: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_appelees.append(str(request.url))
        return httpx.Response(200, json=_payload_horaire_valide())

    with _client_avec_handler(httpx.MockTransport(handler)) as client:
        fetch_hourly(
            latitude=_LATITUDE,
            longitude=_LONGITUDE,
            parameters=["ALLSKY_SFC_SW_DWN", "T2M"],
            start=date(2024, 7, 1),
            end=date(2024, 7, 31),
            httpx_client=client,
        )

    assert len(urls_appelees) == 1
    url = urls_appelees[0]
    assert url.startswith(f"{BASE_URL}/hourly/point")
    assert "start=20240701" in url
    assert "end=20240731" in url
    assert "time-standard=UTC" in url
    assert "parameters=ALLSKY_SFC_SW_DWN%2CT2M" in url or "parameters=ALLSKY_SFC_SW_DWN,T2M" in url
    assert f"community={DEFAULT_COMMUNITY}" in url
    assert f"latitude={_LATITUDE}" in url
    assert f"longitude={_LONGITUDE}" in url
    assert "format=JSON" in url


# ---------------------------------------------------------------------------
# 2. HTTP 429 - NasaPowerRateLimitError
# ---------------------------------------------------------------------------


def test_fetch_hourly_http_429_leve_nasapowerratelimit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    with (
        _client_avec_handler(httpx.MockTransport(handler)) as client,
        pytest.raises(NasaPowerRateLimitError) as exc_info,
    ):
        _appeler(client)

    erreur = exc_info.value
    assert erreur.status_code == 429
    assert "Too Many Requests" in erreur.body
    # Sous-type de NasaPowerHttpError donc isinstance valide
    assert isinstance(erreur, NasaPowerHttpError)


# ---------------------------------------------------------------------------
# 3. HTTP 500 - NasaPowerHttpError générique
# ---------------------------------------------------------------------------


def test_fetch_hourly_http_500_leve_nasapowerhttperror_generique() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    with (
        _client_avec_handler(httpx.MockTransport(handler)) as client,
        pytest.raises(NasaPowerHttpError) as exc_info,
    ):
        _appeler(client)

    erreur = exc_info.value
    assert erreur.status_code == 500
    assert not isinstance(erreur, NasaPowerRateLimitError)


# ---------------------------------------------------------------------------
# 4. JSON invalide - NasaPowerPayloadError
# ---------------------------------------------------------------------------


def test_fetch_hourly_json_invalide_leve_nasapowerpayload_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not a valid json {{{")

    with (
        _client_avec_handler(httpx.MockTransport(handler)) as client,
        pytest.raises(NasaPowerPayloadError) as exc_info,
    ):
        _appeler(client)

    assert "non parsable en JSON" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. JSON parsable mais hors schéma - NasaPowerPayloadError
# ---------------------------------------------------------------------------


def test_fetch_hourly_payload_hors_schema_leve_nasapowerpayload_error() -> None:
    payload_invalide: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 0.0]},
        # `properties`, `header`, `parameters` manquants → ValidationError pydantic
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload_invalide)

    with (
        _client_avec_handler(httpx.MockTransport(handler)) as client,
        pytest.raises(NasaPowerPayloadError) as exc_info,
    ):
        _appeler(client)

    assert "schéma NasaPowerResponse" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. Timeout - NasaPowerTimeoutError
# ---------------------------------------------------------------------------


def test_fetch_hourly_timeout_leve_nasapowertimeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Mocked timeout", request=request)

    with (
        _client_avec_handler(httpx.MockTransport(handler)) as client,
        pytest.raises(NasaPowerTimeoutError) as exc_info,
    ):
        _appeler(client, timeout=5.0)

    assert exc_info.value.timeout_seconds == 5.0
