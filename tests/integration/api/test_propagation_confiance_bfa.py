"""Tests d'intégration de la règle de propagation P sur ``/v1/grandeurs`` (ADR-0025).

Les entrées servies au Burkina Faso sont satellitaires ou de réanalyse, toutes
en confiance B : les grandeurs calculées restent B. Un override éditorial C posé
sur une entrée, dans une transaction annulée en fin de test, ne fait descendre
en C que les valeurs calculées de sa période : son jour, son mois, ou toute la
fenêtre pour un modèle cumulatif.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.main import app
from kuma_data_core.db.session import get_engine, obtenir_session

pytestmark = pytest.mark.integration

GHI = "nasa_power_ghi_journalier_bfa_prov_kadiogo"
DHI = "nasa_power_dhi_journalier_bfa_prov_kadiogo"
T2M = "nasa_power_t2m_journalier_bfa_prov_kadiogo"
PM2_5 = "cams_eac4_pm2_5_journalier_bfa_prov_kadiogo"
PLUIE = "nasa_power_precipitation_journalier_bfa_prov_kadiogo"
GHI_MENSUEL = "nasa_power_ghi_mensuel_bfa_prov_kadiogo"
GHI_HORAIRE = "nasa_power_ghi_horaire_bfa_com_ouagadougou"
JANVIER_2024 = {"periode_debut": "2024-01-01", "periode_fin": "2024-01-31"}
POA = {"code_serie_source": GHI, "inclinaison_deg": 15, "orientation_deg": 180, **JANVIER_2024}


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


def _mettre_en_c(session: Session, table: str, code_serie: str, condition: str) -> None:
    """Override éditorial C sur une mesure courante, désignée par ``condition``."""
    resultat = session.execute(
        text(
            f"UPDATE {table} SET niveau_confiance_override = 'C', "
            "commentaire_editorial = 'test de propagation' "
            "WHERE serie_id = (SELECT id FROM series_metadonnees WHERE code = :code) "
            f"AND valide_au IS NULL AND {condition}"
        ),
        {"code": code_serie},
    )
    assert resultat.rowcount == 1  # type: ignore[attr-defined]
    session.flush()


def _jour_en_c(session: Session, code_serie: str, jour: str) -> None:
    _mettre_en_c(session, "mesures_ressource", code_serie, f"instant_mesure = '{jour}'")


def _niveaux(
    client: TestClient, headers: dict[str, str], chemin: str, cle: str = "resultats", **params: Any
) -> dict[str, str]:
    response = client.get(f"/v1/grandeurs/{chemin}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return {r["instant"]: r["niveau_confiance"] for r in response.json()[cle]}


def test_entrees_satellitaires_restent_b(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Sans override, POA, degrés-jours et P50/P90 restent B, comme leurs entrées."""
    poa = _niveaux(client, headers_auth, "poa_parametrable", **POA)
    djc = _niveaux(
        client,
        headers_auth,
        "degre_jour_climatisation",
        code_serie_source=T2M,
        base_temperature_degc=26,
        **JANVIER_2024,
    )
    response = client.get("/v1/grandeurs/ghi_exceedance/bfa_prov_kadiogo", headers=headers_auth)
    assert response.status_code == 200
    assert len(poa) == 31
    assert set(poa.values()) == set(djc.values()) == {"B"}
    assert response.json()["niveau_confiance"] == "B"


def test_poa_dhi_compagne_en_c(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """POA : un DHI compagne en C met son seul jour en C."""
    _jour_en_c(session_annulee, DHI, "2024-01-03")
    niveaux = _niveaux(client, headers_auth, "poa_parametrable", **POA)
    assert niveaux.pop("2024-01-03") == "C"
    assert set(niveaux.values()) == {"B"}


def test_thermique_t2m_compagne_en_c(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Productible thermique : une T2M compagne en C met son seul jour en C."""
    _jour_en_c(session_annulee, T2M, "2024-01-02")
    niveaux = _niveaux(
        client,
        headers_auth,
        "productible_correction_thermique",
        code_serie_source=GHI,
        noct_degc=45,
        coeff_temp_pourcent_par_degc=-0.35,
        puissance_stc_wc=1000,
        **JANVIER_2024,
    )
    assert niveaux.pop("2024-01-02") == "C"
    assert set(niveaux.values()) == {"B"}


def test_djc_mois_au_niveau_de_ses_jours(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Degrés-jours mensuels : un jour de T2M en C met son mois en C, pas le mois suivant."""
    _jour_en_c(session_annulee, T2M, "2024-01-15")
    niveaux = _niveaux(
        client,
        headers_auth,
        "degre_jour_climatisation",
        code_serie_source=T2M,
        base_temperature_degc=26,
        periode_debut="2024-01-01",
        periode_fin="2024-02-29",
    )
    assert niveaux == {"2024-01": "C", "2024-02": "B"}


def test_productible_mensuel_au_niveau_de_son_mois(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Productible sur la série mensuelle : un mois de GHI en C ne touche que ce mois."""
    _mettre_en_c(
        session_annulee, "mesures_ressource_mensuelles", GHI_MENSUEL, "annee = 2024 AND mois = 3"
    )
    niveaux = _niveaux(
        client,
        headers_auth,
        "productible_pr_fourni",
        code_serie_source=GHI_MENSUEL,
        pr_fourni=0.8,
        correction="aucune",
        puissance_stc_wc=1000,
        periode_debut="2024-01-01",
        periode_fin="2024-06-30",
    )
    assert len(niveaux) == 6
    assert niveaux.pop("2024-03") == "C"
    assert set(niveaux.values()) == {"B"}


def test_lecteur_horaire_par_jour_utc(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """Productible en intégration horaire : une heure en C met son jour UTC en C.

    La session PostgreSQL est en UTC+9 : l'heure de 20 h UTC du 12 janvier y
    tombe le 13, mais les calculs comme les niveaux se rangent par jour UTC.
    """
    session_annulee.execute(text("SET LOCAL TIME ZONE 'Asia/Tokyo'"))
    _mettre_en_c(
        session_annulee,
        "mesures_ressource_horaires",
        GHI_HORAIRE,
        "instant_mesure = '2024-01-12 20:00+00' "
        "AND statut IN ('valide_auto', 'valide_humain', 'publie')",
    )
    niveaux = _niveaux(
        client,
        headers_auth,
        "productible_pr_fourni",
        code_serie_source=GHI_HORAIRE,
        pr_fourni=0.8,
        correction="aucune",
        puissance_stc_wc=1000,
        methode="integration_horaire",
        periode_debut="2024-01-10",
        periode_fin="2024-01-16",
    )
    assert len(niveaux) == 7
    assert niveaux.pop("2024-01-12") == "C"
    assert set(niveaux.values()) == {"B"}


@pytest.mark.parametrize(("annee", "attendu"), [(2000, "C"), (2022, "B")])
def test_ghi_exceedance_sur_la_normale(
    client: TestClient,
    headers_auth: dict[str, str],
    session_annulee: Session,
    annee: int,
    attendu: str,
) -> None:
    """P50/P90 : un mois en C de la normale 1991-2020 met la fiche en C ; un mois de 2022, non."""
    _mettre_en_c(
        session_annulee,
        "mesures_ressource_mensuelles",
        GHI_MENSUEL,
        f"annee = {annee} AND mois = 6",
    )
    response = client.get("/v1/grandeurs/ghi_exceedance/bfa_prov_kadiogo", headers=headers_auth)
    assert response.status_code == 200
    assert response.json()["niveau_confiance"] == attendu


@pytest.mark.parametrize(("code_serie", "jour"), [(PM2_5, "2024-01-03"), (PLUIE, "2010-07-03")])
def test_salissure_cumulative(
    client: TestClient,
    headers_auth: dict[str, str],
    session_annulee: Session,
    code_serie: str,
    jour: str,
) -> None:
    """Salissure (modèle cumulatif) : un jour de PM2.5 ou de pluie en C met la fenêtre en C."""
    _jour_en_c(session_annulee, code_serie, jour)
    response = client.get(f"/v1/grandeurs/taux_salissure_proxy/{PM2_5}", headers=headers_auth)
    assert response.status_code == 200, response.text
    assert {m["niveau_confiance"] for m in response.json()["mesures"]} == {"C"}


def test_pr_realiste_par_jour_sans_salissure(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """PR réaliste sans salissure : un GHI en C ne touche que son jour et son mois."""
    _jour_en_c(session_annulee, GHI, "2024-01-03")
    response = client.get(
        f"/v1/grandeurs/pr_realiste/{GHI}",
        params={"pr_fourni": 0.8, "correction": "aucune"},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    jours = {m["instant"]: m["niveau_confiance"] for m in payload["mesures_journalier"]}
    mois = {m["instant"]: m["niveau_confiance"] for m in payload["mesures_mensuel"]}
    assert jours.pop("2024-01-03") == "C"
    assert set(jours.values()) == {"B"}
    assert mois.pop("2024-01") == "C"
    assert set(mois.values()) == {"B"}


def test_pr_realiste_avec_salissure_sur_la_fenetre(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """PR réaliste avec salissure, cumulative : un jour de PM2.5 en C met tous les jours en C."""
    _jour_en_c(session_annulee, PM2_5, "2024-01-03")
    response = client.get(
        f"/v1/grandeurs/pr_realiste/{GHI}",
        params={"pr_fourni": 0.8, "correction": "salissure"},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {m["niveau_confiance"] for m in payload["mesures_journalier"]} == {"C"}
    assert {m["niveau_confiance"] for m in payload["mesures_mensuel"]} == {"C"}


def _tout_en_a(session: Session, table: str, codes: list[str], condition: str) -> int:
    """Override éditorial A sur les mesures courantes désignées par ``condition``."""
    resultat = session.execute(
        text(
            f"UPDATE {table} SET niveau_confiance_override = 'A', "
            "commentaire_editorial = 'test de plafond' "
            "WHERE serie_id IN (SELECT id FROM series_metadonnees WHERE code = ANY(:codes)) "
            f"AND valide_au IS NULL AND {condition}"
        ),
        {"codes": codes},
    )
    session.flush()
    return int(resultat.rowcount)  # type: ignore[attr-defined]


def test_plafond_b_du_poa_sur_des_entrees_a(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """POA (modèle, plafond B) : des entrées toutes en A laissent leur jour en B."""
    codes = [GHI, DHI, "nasa_power_dni_journalier_bfa_prov_kadiogo"]
    assert (
        _tout_en_a(session_annulee, "mesures_ressource", codes, "instant_mesure = '2024-01-03'")
        == 3
    )
    assert _niveaux(client, headers_auth, "poa_parametrable", **POA)["2024-01-03"] == "B"


def test_plafond_a_de_ghi_exceedance_sur_des_entrees_a(
    client: TestClient, headers_auth: dict[str, str], session_annulee: Session
) -> None:
    """P50/P90 (calcul exact, plafond A) : une normale toute en A donne A."""
    assert (
        _tout_en_a(
            session_annulee,
            "mesures_ressource_mensuelles",
            [GHI_MENSUEL],
            "annee BETWEEN 1991 AND 2020",
        )
        == 360
    )
    response = client.get("/v1/grandeurs/ghi_exceedance/bfa_prov_kadiogo", headers=headers_auth)
    assert response.status_code == 200
    assert response.json()["niveau_confiance"] == "A"
