"""Tests d'intégration du service horaire aux points pilotes (ADR-0014).

Ouagadougou, 2021-2025 : l'endpoint horaire sert la série stockée et validée
par le QC (migrations 0011 et 0012), sans relais amont, et les grandeurs
calculables en intégration horaire trouvent leurs compagnes horaires.
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

GHI = "nasa_power_ghi_horaire_bfa_com_ouagadougou"
T2M = "nasa_power_t2m_horaire_bfa_com_ouagadougou"
HORAIRE_2024 = {
    "periode_debut": "2024-01-01",
    "periode_fin": "2024-12-31",
    "methode": "integration_horaire",
}


def _resultats(
    client: TestClient, headers: dict[str, str], chemin: str, **params: Any
) -> list[float]:
    response = client.get(f"/v1/grandeurs/{chemin}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [r["valeur"] for r in response.json()["resultats"]]


def _ghi_par_jour(client: TestClient, headers: dict[str, str]) -> list[float]:
    """GHI 2024 de l'endpoint horaire, cumulé par jour UTC (kWh/m²/jour)."""
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/ghi",
        params={"periode_debut": "2024-01-01", "periode_fin": "2024-12-31"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    jours: dict[str, float] = {}
    for r in response.json()["resultats"]:
        jours[r["instant"][:10]] = jours.get(r["instant"][:10], 0.0) + r["valeur"] / 1000.0
    return list(jours.values())


def test_horaire_sert_la_serie_validee(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Deux jours de GHI : 48 heures stockées, statut valide_auto, instants UTC à l'heure pile."""
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/ghi",
        params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-02"},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    resultats = response.json()["resultats"]
    assert len(resultats) == 48
    assert resultats[0]["instant"] == "2024-06-01T00:00:00"
    assert resultats[-1]["instant"] == "2024-06-02T23:00:00"
    assert {r["statut_editorial"] for r in resultats} == {"valide_auto"}
    assert {r["unite"] for r in resultats} == {"Wh/m²"}  # énergie de l'heure
    assert max(r["valeur"] for r in resultats) > 500.0
    assert resultats[0]["valeur"] == 0.0  # minuit UTC, nuit à Ouagadougou


def test_horaire_csv(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le format CSV sert les mêmes 24 heures de température."""
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/t2m",
        params={"periode_debut": "2023-03-15", "periode_fin": "2023-03-15", "format": "csv"},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    lignes = response.text.strip().splitlines()
    assert lignes[0] == "instant,valeur,unite,statut_editorial"
    assert len(lignes) == 25
    assert all(ligne.endswith(",valide_auto") for ligne in lignes[1:])


def test_poa_horaire_plan_horizontal(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Direct reconstruit sur GHI et DHI : le plan horizontal retrouve le GHI.

    L'ancien calcul, avec le DNI de la source, en perdait 8 %. L'écart restant
    vient des heures où le DHI de la source dépasse le GHI, ou où le soleil se
    lève après le milieu de l'heure : moins de 1 % sur un jour, 0,02 % sur l'année.
    """
    poa = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        inclinaison_deg=0,
        orientation_deg=180,
        albedo_sol=0.2,
        **HORAIRE_2024,
    )
    ghi = _ghi_par_jour(client, headers_auth)
    assert len(poa) == len(ghi) == 366
    assert max(abs(p - g) / g for p, g in zip(poa, ghi, strict=True)) < 0.01
    assert abs(sum(poa) - sum(ghi)) < 2e-4 * sum(ghi)


def test_poa_horaire_plan_incline(client: TestClient, headers_auth: dict[str, str]) -> None:
    """À 15° plein sud, le plan gagne de 2 à 5 % sur le GHI (3,5 % en 2024, ADR-0014)."""
    poa = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        inclinaison_deg=15,
        orientation_deg=180,
        albedo_sol=0.2,
        **HORAIRE_2024,
    )
    ghi = _ghi_par_jour(client, headers_auth)
    assert 1.02 < statistics.mean(poa) / statistics.mean(ghi) < 1.05


def test_poa_bifacial_horaire(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le POA bifacial horaire se calcule sans compagne DNI et dépasse le monofacial.

    Sans le biais du midi solaire, la réponse ne porte pas de ``limite`` (ADR-0020).
    """
    commun = {"code_serie_source": GHI, "inclinaison_deg": 15, "orientation_deg": 180}
    bifacial = _resultats(
        client,
        headers_auth,
        "poa_bifacial",
        gcr=0.4,
        hauteur_m=1.5,
        pitch_m=5.0,
        bifacialite=0.7,
        albedo_sol=0.25,
        **commun,
        **HORAIRE_2024,
    )
    monofacial = _resultats(
        client, headers_auth, "poa_parametrable", albedo_sol=0.25, **commun, **HORAIRE_2024
    )
    assert len(bifacial) == len(monofacial) == 366
    assert statistics.mean(bifacial) > statistics.mean(monofacial)
    for chemin, extra in (
        ("poa_parametrable", {}),
        ("poa_bifacial", {"gcr": 0.4, "hauteur_m": 1.5, "pitch_m": 5.0}),
    ):
        response = client.get(
            f"/v1/grandeurs/{chemin}",
            params={**commun, **HORAIRE_2024, "periode_fin": "2024-01-31", **extra},
            headers=headers_auth,
        )
        assert response.status_code == 200, response.text
        assert response.json()["limite"] is None, chemin


def test_productible_thermique_horaire(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Compagne T2M horaire trouvée ; la température coûte de 5 à 15 % du productible."""
    productible = _resultats(
        client,
        headers_auth,
        "productible_correction_thermique",
        code_serie_source=GHI,
        noct_degc=45,
        coeff_temp_pourcent_par_degc=-0.35,
        puissance_stc_wc=1000,
        **HORAIRE_2024,
    )
    ghi = _ghi_par_jour(client, headers_auth)
    assert len(productible) == 366
    assert 0.85 < sum(productible) / sum(ghi) < 0.95


def test_degres_jours_horaires(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Degrés-jours de climatisation sur la température horaire, en cumuls mensuels."""
    djc = _resultats(
        client,
        headers_auth,
        "degre_jour_climatisation",
        code_serie_source=T2M,
        base_temperature_degc=26,
        **HORAIRE_2024,
    )
    assert len(djc) == 12
    assert all(v > 0.0 for v in djc)


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


def _desactiver(session: Session, grandeur: str) -> None:
    session.execute(
        text(
            "UPDATE series_metadonnees SET actif = FALSE, desactive_le = now() WHERE code = :code"
        ),
        {"code": f"nasa_power_{grandeur}_horaire_bfa_com_ouagadougou"},
    )
    session.flush()


def test_poa_horaire_sans_dni_puis_sans_dhi(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Sans série DNI, le POA horaire est inchangé ; sans série DHI, il est refusé (400)."""
    params: dict[str, Any] = {
        "code_serie_source": GHI,
        "inclinaison_deg": 15,
        "orientation_deg": 180,
        **HORAIRE_2024,
        "periode_fin": "2024-01-31",
    }
    bifacial = {"gcr": 0.4, "hauteur_m": 1.5, "pitch_m": 5.0, "bifacialite": 0.7}
    avant = _resultats(client, headers_auth, "poa_parametrable", **params)
    avant_bifacial = _resultats(client, headers_auth, "poa_bifacial", **params, **bifacial)

    _desactiver(session_annulee, "dni")
    assert _resultats(client, headers_auth, "poa_parametrable", **params) == avant
    assert _resultats(client, headers_auth, "poa_bifacial", **params, **bifacial) == avant_bifacial

    _desactiver(session_annulee, "dhi")
    for chemin, extra in (("poa_parametrable", {}), ("poa_bifacial", bifacial)):
        response = client.get(
            f"/v1/grandeurs/{chemin}", params={**params, **extra}, headers=headers_auth
        )
        assert response.status_code == 400, chemin
        assert "DHI horaire" in response.json()["erreur"]["message"], chemin


def test_jour_incomplet_ecarte(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Une heure rejetée par le QC retire son jour du POA horaire au lieu de l'amputer.

    Le DHI du 10 mars 2024 à 12 h UTC repasse en ``brut`` : sans cette heure, le
    cumul du jour perdrait 15 %.
    """
    params: dict[str, Any] = {
        "code_serie_source": GHI,
        "inclinaison_deg": 15,
        "orientation_deg": 180,
        **HORAIRE_2024,
        "periode_debut": "2024-03-01",
        "periode_fin": "2024-03-31",
    }
    avant = client.get("/v1/grandeurs/poa_parametrable", params=params, headers=headers_auth)
    session_annulee.execute(
        text(
            "UPDATE mesures_ressource_horaires SET statut = 'brut' "
            "WHERE instant_mesure = '2024-03-10 12:00+00' AND serie_id = "
            "(SELECT id FROM series_metadonnees WHERE code = :code)"
        ),
        {"code": "nasa_power_dhi_horaire_bfa_com_ouagadougou"},
    )
    session_annulee.flush()
    apres = client.get("/v1/grandeurs/poa_parametrable", params=params, headers=headers_auth)
    assert avant.status_code == apres.status_code == 200
    jours_avant = {r["instant"]: r["valeur"] for r in avant.json()["resultats"]}
    jours_apres = {r["instant"]: r["valeur"] for r in apres.json()["resultats"]}
    assert len(jours_avant) == 31
    assert set(jours_avant) - set(jours_apres) == {"2024-03-10"}
    assert all(jours_apres[j] == jours_avant[j] for j in jours_apres)
