"""Tests d'intégration de l'API ``/v1/localites`` sur le référentiel Burkina Faso.

Relit par l'API le seed de la migration 0003 : listing filtré par pays, par
niveau et par parent, puis détail d'une province créée en 2025.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_listing_par_pays(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Pays, 17 régions et 47 provinces portent ``pays_iso3 = BFA``."""
    response = client.get("/v1/localites?pays_iso3=BFA&limit=100", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 65
    types = {item["type_localite"] for item in payload["items"]}
    assert types == {"pays", "region_administrative", "prefecture"}


def test_listing_provinces_d_une_region(client: TestClient, headers_auth: dict[str, str]) -> None:
    """La région du Soum (créée en 2025) porte Djelgodji et Karo-Peli."""
    response = client.get(
        "/v1/localites?type_localite=prefecture&parent_code=bfa_soum", headers=headers_auth
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {item["code"] for item in payload["items"]} == {
        "bfa_prov_djelgodji",
        "bfa_prov_karo_peli",
    }
    assert {item["parent_code"] for item in payload["items"]} == {"bfa_soum"}


def test_detail_province_creee(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Détail de Dyamongou : niveau, parent et pays."""
    response = client.get("/v1/localites/bfa_prov_dyamongou", headers=headers_auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["nom"] == "Dyamongou"
    assert payload["type_localite"] == "prefecture"
    assert payload["parent_code"] == "bfa_tapoa"
    assert payload["pays_iso3"] == "BFA"
