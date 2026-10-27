"""Tests d'intégration de la fiche d'incertitude inter-source (ADR-0016).

Écarts mensuels à NASA POWER de l'ADR-0012 (migration 0009), fenêtre commune
2005-2023, et dégénérescence de pixel (migration 0014). La fiche se recalcule
à partir des séries d'écart servies par ``/v1/series``.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.main import app
from kuma_data_core.db.session import get_engine, obtenir_session

pytestmark = pytest.mark.integration

PAIRES = [
    ("ghi", "SARAH-3 vs NASA POWER", "ecart_ghi_sarah3_nasa"),
    ("ghi", "ERA5 vs NASA POWER", "ecart_ghi_era5_nasa"),
    ("ghi", "CAMS vs NASA POWER", "ecart_ghi_cams_nasa"),
    ("dni", "SARAH-3 vs NASA POWER", "ecart_dni_sarah3_nasa"),
    ("dni", "ERA5 vs NASA POWER", "ecart_dni_era5_nasa"),
    ("dni", "CAMS vs NASA POWER", "ecart_dni_cams_nasa"),
    ("dhi", "CAMS vs NASA POWER", "ecart_dhi_cams_nasa"),
]


def _fiche(client: TestClient, headers: dict[str, str], localite: str) -> dict[str, Any]:
    response = client.get(f"/v1/grandeurs/incertitude_inter_source/{localite}", headers=headers)
    assert response.status_code == 200, response.text
    fiche: dict[str, Any] = response.json()
    return fiche


def test_fiche_kadiogo(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Sept paires sur 228 mois, DNI très au-dessus de NASA POWER, 32 jumeaux de maille."""
    fiche = _fiche(client, headers_auth, "bfa_prov_kadiogo")
    assert (fiche["fenetre"], fiche["niveau_confiance"]) == ("2005-2023", "B")
    ecarts = fiche["ecarts"]
    assert [(e["grandeur"], e["paire"]) for e in ecarts] == [(g, p) for g, p, _ in PAIRES]
    assert {e["n_mois"] for e in ecarts} == {228}
    par_paire = {(e["grandeur"], e["paire"]): e for e in ecarts}
    sarah3 = par_paire[("ghi", "SARAH-3 vs NASA POWER")]
    era5 = par_paire[("dni", "ERA5 vs NASA POWER")]
    cams = par_paire[("dhi", "CAMS vs NASA POWER")]
    assert sarah3["ecart_abs_pct"] == pytest.approx(7.23, abs=0.01)
    assert era5["ecart_abs_pct"] == pytest.approx(63.83, abs=0.01)
    assert cams["ecart_signe_pct"] == pytest.approx(-0.92, abs=0.01)
    assert all(e["ecart_signe_pct"] > 20 for e in ecarts if e["grandeur"] == "dni")
    degenerescence = fiche["degenerescence"]
    assert degenerescence["n_jumeaux"] == 32
    assert "bfa_com_ouagadougou" in degenerescence["note"]


def test_fiche_recalculee_depuis_les_series(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """Médiane des |écarts| et moyenne signée redonnent la fiche, paire par paire."""
    fiche = _fiche(client, headers_auth, "bfa_dep_dori")
    for (_, _, prefixe), ecart in zip(PAIRES, fiche["ecarts"], strict=True):
        response = client.get(
            f"/v1/series/{prefixe}_bfa_dep_dori",
            params={"from": "2005-01-01", "to": "2023-12-31", "limit": 1000},
            headers=headers_auth,
        )
        assert response.status_code == 200, response.text
        valeurs = [m["valeur"] for m in response.json()["mesures"]]
        assert len(valeurs) == ecart["n_mois"] == 228
        assert ecart["ecart_abs_pct"] == pytest.approx(
            statistics.median(abs(v) for v in valeurs), abs=1e-4
        )
        assert ecart["ecart_signe_pct"] == pytest.approx(statistics.mean(valeurs), abs=1e-4)


def test_collection(client: TestClient, headers_auth: dict[str, str]) -> None:
    """398 localités ; chaque fiche de la collection est celle de l'endpoint par localité."""
    response = client.get(
        "/v1/grandeurs/incertitude_inter_source",
        params={"limit": 1000},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == len(payload["items"]) == 398
    assert all(len(item["ecarts"]) == 7 for item in payload["items"])
    kadiogo = next(i for i in payload["items"] if i["code_localite"] == "bfa_prov_kadiogo")
    fiche = _fiche(client, headers_auth, "bfa_prov_kadiogo")
    assert kadiogo["ecarts"] == fiche["ecarts"]
    assert kadiogo["degenerescence"] == fiche["degenerescence"]
    assert 9.0 < kadiogo["latitude_deg"] < 15.0


def test_localite_inconnue(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Une localité hors de l'atlas renvoie 404."""
    response = client.get(
        "/v1/grandeurs/incertitude_inter_source/bfa_prov_inconnue", headers=headers_auth
    )
    assert response.status_code == 404


def test_pagination(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Des pages de 37 fiches, mises bout à bout, redonnent la collection entière."""

    def _page(limit: int, offset: int) -> dict[str, Any]:
        response = client.get(
            "/v1/grandeurs/incertitude_inter_source",
            params={"limit": limit, "offset": offset},
            headers=headers_auth,
        )
        assert response.status_code == 200, response.text
        page: dict[str, Any] = response.json()
        return page

    complete = _page(1000, 0)["items"]
    concatenee: list[dict[str, Any]] = []
    for offset in range(0, 398, 37):
        page = _page(37, offset)
        assert (page["total"], page["limit"], page["offset"]) == (398, 37, offset)
        concatenee += page["items"]
    assert [i["code_localite"] for i in concatenee] == [i["code_localite"] for i in complete]
    assert _page(37, 396)["items"] == complete[396:]


@pytest.fixture
def session_annulee() -> Iterator[Session]:
    """Session servie à l'API dans une transaction annulée en fin de test."""
    connexion = get_engine().connect()
    transaction = connexion.begin()
    session = Session(bind=connexion, join_transaction_mode="create_savepoint")
    app.dependency_overrides[obtenir_session] = lambda: session
    try:
        yield session
    finally:
        app.dependency_overrides.pop(obtenir_session, None)
        session.close()
        transaction.rollback()
        connexion.close()


def test_garde_de_confiance(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Un écart passé en confiance A fait échouer la fiche : elle n'affiche jamais que B."""
    session_annulee.execute(
        text(
            """
            UPDATE grandeurs_metier SET niveau_confiance_override = 'A'
            WHERE id = (
                SELECT gm.id FROM grandeurs_metier gm
                JOIN localites l ON l.id = gm.localite_id
                WHERE l.code = 'bfa_prov_kadiogo'
                  AND gm.grandeur_code = 'ecart_relatif_ghi_era5_nasa'
                  AND gm.annee_debut = 2010 AND gm.mois = 6
            )
            """
        )
    )
    session_annulee.flush()
    response = client.get(
        "/v1/grandeurs/incertitude_inter_source/bfa_prov_kadiogo", headers=headers_auth
    )
    assert response.status_code == 500
    assert "confiance" in response.json()["erreur"]["message"]
