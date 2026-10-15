"""Tests d'intégration de l'API ``/v1/series`` sur les séries solaires Burkina Faso."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_listing_des_series_d_une_commune(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une commune porte 7 séries mensuelles : NASA POWER, SARAH-3 et ERA5."""
    response = client.get("/v1/series?localite=bfa_dep_fo", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 7
    familles = {(s["source_code"], s["grandeur_code"]) for s in payload["items"]}
    assert familles == {
        ("nasa_power", "ghi"),
        ("nasa_power", "dni"),
        ("nasa_power", "dhi"),
        ("sarah3_monthly", "ghi"),
        ("sarah3_monthly", "dni"),
        ("era5_pvgis", "ghi"),
        ("era5_pvgis", "dni"),
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
