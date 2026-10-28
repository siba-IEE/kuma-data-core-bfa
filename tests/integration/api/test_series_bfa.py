"""Tests d'intégration de l'API ``/v1/series`` sur les séries solaires Burkina Faso."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_listing_des_series_d_une_commune(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une commune porte 47 séries brutes (NASA POWER, SARAH-3, ERA5, CAMS) et 8 dérivées.

    NASA POWER : rayonnement mensuel et journalier, météo journalière (ADR-0017),
    météo complémentaire (ADR-0021) ; SARAH-3 : rayonnement mensuel (ADR-0009) et
    journalier (ADR-0022) ; CAMS EAC4 : particules fines (ADR-0018) et aérosols
    (ADR-0019) journaliers ; CAMS Radiation : rayonnement mensuel et journalier,
    ciel clair (ADR-0020) ; ERA5-Land : météo et rayonnement journaliers (ADR-0024).
    """
    response = client.get("/v1/series?localite=bfa_dep_fo", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 55
    familles = {(s["source_code"], s["grandeur_code"]) for s in payload["items"]}
    assert familles == {
        ("nasa_power", "ghi"),
        ("nasa_power", "dni"),
        ("nasa_power", "dhi"),
        ("nasa_power", "t2m"),
        ("nasa_power", "rh2m"),
        ("nasa_power", "precipitation"),
        ("nasa_power", "t2m_min"),
        ("nasa_power", "t2m_max"),
        ("nasa_power", "point_rosee_2m"),
        ("nasa_power", "vent_10m"),
        ("nasa_power", "vent_10m_max"),
        ("nasa_power", "direction_vent_10m"),
        ("nasa_power", "vent_50m"),
        ("nasa_power", "pression_surface"),
        ("nasa_power", "nebulosite"),
        ("sarah3_monthly", "ghi"),
        ("sarah3_monthly", "dni"),
        ("sarah3_monthly", "dhi"),
        ("era5_pvgis", "ghi"),
        ("era5_pvgis", "dni"),
        ("ecmwf_era5_land", "t2m"),
        ("ecmwf_era5_land", "t2m_min"),
        ("ecmwf_era5_land", "t2m_max"),
        ("ecmwf_era5_land", "point_rosee_2m"),
        ("ecmwf_era5_land", "pression_surface"),
        ("ecmwf_era5_land", "vent_10m"),
        ("ecmwf_era5_land", "direction_vent_10m"),
        ("ecmwf_era5_land", "precipitation"),
        ("ecmwf_era5_land", "ghi"),
        ("cams_radiation", "ghi"),
        ("cams_radiation", "dni"),
        ("cams_radiation", "dhi"),
        ("cams_radiation", "ghi_ciel_clair"),
        ("cams_radiation", "dni_ciel_clair"),
        ("cams_eac4", "pm2_5"),
        ("cams_eac4", "pm10"),
        ("cams_eac4", "aod550"),
        ("cams_eac4", "aod550_poussiere"),
        ("cams_eac4", "aod550_organique"),
        ("kuma_calculs", "ecart_relatif_ghi_sarah3_nasa"),
        ("kuma_calculs", "ecart_relatif_ghi_era5_nasa"),
        ("kuma_calculs", "ecart_relatif_ghi_cams_nasa"),
        ("kuma_calculs", "ecart_relatif_dni_sarah3_nasa"),
        ("kuma_calculs", "ecart_relatif_dni_era5_nasa"),
        ("kuma_calculs", "ecart_relatif_dni_cams_nasa"),
        ("kuma_calculs", "ecart_relatif_dhi_cams_nasa"),
        ("kuma_calculs", "fraction_diffuse"),
    }


def test_detail_d_une_serie_mensuelle(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le détail renvoie les mesures mensuelles bornées dans le temps."""
    response = client.get(
        "/v1/series/sarah3_ghi_mensuel_bfa_com_ouagadougou?from=2023-01&to=2023-12",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["localite_code"] == "bfa_com_ouagadougou"
    assert len(payload["mesures"]) == 12
    assert all(3.0 < m["valeur"] < 8.5 for m in payload["mesures"])


def test_detail_d_une_serie_journaliere(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une série journalière renvoie un jour par mesure, 29 février compris."""
    response = client.get(
        "/v1/series/nasa_power_ghi_journalier_bfa_prov_kadiogo?from=2024-02-01&to=2024-02-29",
        headers=headers_auth,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["localite_code"] == "bfa_prov_kadiogo"
    assert len(payload["mesures"]) == 29
    assert all(0.0 < m["valeur"] < 9.0 for m in payload["mesures"])


def test_detail_d_une_grandeur_derivee(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une série dérivée renvoie ses valeurs mensuelles et annuelles de grandeurs_metier."""
    response = client.get(
        "/v1/series/fraction_diffuse_nasa_power_bfa_prov_kadiogo?from=2024-01&to=2024-12",
        headers=headers_auth,
    )
    assert response.status_code == 200
    mesures = response.json()["mesures"]
    types = sorted(m["periode_type"] for m in mesures)
    assert types == ["annuel"] + ["mensuel"] * 12
    assert all(0.0 < m["valeur"] < 1.0 and m["niveau_effectif"] == "B" for m in mesures)


def test_detail_d_une_serie_dense(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une série dense de commune se lit comme une autre ; le jour écarté manque (ADR-0017)."""

    def mesures(code: str, debut: str, fin: str) -> list[dict[str, object]]:
        response = client.get(f"/v1/series/{code}?from={debut}&to={fin}", headers=headers_auth)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["localite_code"] == code.rsplit("_journalier_", 1)[1]
        return list(payload["mesures"])

    pluie = mesures(
        "nasa_power_precipitation_journalier_bfa_dep_tiefora", "2025-11-30", "2025-12-04"
    )
    assert [m["instant_mesure"] for m in pluie] == [
        "2025-11-30",
        "2025-12-01",
        "2025-12-03",
        "2025-12-04",
    ]
    assert all(m["type"] == "journalier" and m["statut"] == "brut" for m in pluie)
    # Tiéfora lit la série portée par Banfora (même maille de 1°).
    tiefora = mesures("nasa_power_ghi_journalier_bfa_dep_tiefora", "2024-02-01", "2024-02-29")
    banfora = mesures("nasa_power_ghi_journalier_bfa_dep_banfora", "2024-02-01", "2024-02-29")
    assert len(tiefora) == 29
    assert [m["valeur"] for m in tiefora] == [m["valeur"] for m in banfora]
