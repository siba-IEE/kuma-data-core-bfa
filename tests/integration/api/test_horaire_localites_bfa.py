"""Tests d'intégration de l'horaire stocké aux 398 localités (ADR-0026).

Hors des points pilotes, ``/v1/horaire`` sert la série validée de la maille,
lue sur sa porteuse, et les grandeurs en intégration horaire trouvent leurs
compagnes horaires.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from kuma_data_core.core.config import get_settings
from kuma_data_core.db.seeds.mailles_horaires import lire_mailles

pytestmark = pytest.mark.integration

DEUX_JOURS = {"periode_debut": "2024-06-01", "periode_fin": "2024-06-02"}


def _horaire(client: TestClient, headers: dict[str, str], chemin: str) -> dict[str, Any]:
    response = client.get(f"/v1/horaire/{chemin}", params=DEUX_JOURS, headers=headers)
    assert response.status_code == 200, response.text
    reponse: dict[str, Any] = response.json()
    return reponse


def test_horaire_de_la_maille_hors_des_pilotes(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Le Kadiogo sert, validé, le GHI et la température horaires de ses porteuses."""
    maille = next(m for m in lire_mailles() if m.localite_code == "bfa_prov_kadiogo")
    for grandeur in ("ghi", "t2m"):
        kadiogo = _horaire(client, headers_auth, f"bfa_prov_kadiogo/{grandeur}")
        porteuse = _horaire(client, headers_auth, f"{maille.porteuse(grandeur)}/{grandeur}")
        assert kadiogo["source"] == "nasa_power"
        assert len(kadiogo["resultats"]) == 48
        assert {r["statut_editorial"] for r in kadiogo["resultats"]} == {"valide_auto"}
        assert kadiogo["resultats"] == porteuse["resultats"]


def test_disponibilite_stockee_en_edition_figee(
    client: TestClient, headers_auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans relais, une commune a la plage de sa série stockée, 2021-2025."""
    figee = get_settings().model_copy(update={"edition_figee": True})
    monkeypatch.setattr("kuma_data_core.api.v1.horaire.get_settings", lambda: figee)
    response = client.get("/v1/horaire/bfa_dep_fo/dhi/disponibilite", headers=headers_auth)
    assert response.status_code == 200, response.text
    reponse = response.json()
    assert (reponse["source"], reponse["plage_disponible"], reponse["statut_editorial"]) == (
        "nasa_power",
        {"debut": "2021-01-01", "fin": "2025-12-31"},
        "valide_auto",
    )


def test_poa_et_degres_jours_horaires_sur_une_commune(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Le POA et les degrés-jours en intégration horaire se calculent à Fô."""
    commun = {"periode_debut": "2024-01-01", "periode_fin": "2024-01-31"}
    poa = client.get(
        "/v1/grandeurs/poa_parametrable",
        params={
            "code_serie_source": "nasa_power_ghi_horaire_bfa_dep_fo",
            "inclinaison_deg": 15,
            "orientation_deg": 180,
            "methode": "integration_horaire",
            **commun,
        },
        headers=headers_auth,
    )
    assert poa.status_code == 200, poa.text
    jours = poa.json()["resultats"]
    assert len(jours) == 31
    assert all(4.0 < j["valeur"] < 8.0 for j in jours)
    assert {j["niveau_confiance"] for j in jours} == {"B"}
    djc = client.get(
        "/v1/grandeurs/degre_jour_climatisation",
        params={
            "code_serie_source": "nasa_power_t2m_horaire_bfa_dep_fo",
            "base_temperature_degc": 26,
            "methode": "integration_horaire",
            **commun,
        },
        headers=headers_auth,
    )
    assert djc.status_code == 200, djc.text
    assert [m["instant"] for m in djc.json()["resultats"]] == ["2024-01"]
