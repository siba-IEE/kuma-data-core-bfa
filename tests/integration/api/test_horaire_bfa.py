"""Tests d'intégration du service horaire aux points pilotes (ADR-0014).

Ouagadougou, 2021-2025 : l'endpoint horaire sert la série stockée et validée
par le QC (migrations 0011, 0012 et 0022), sans relais amont, et les grandeurs
calculables en intégration horaire trouvent leurs compagnes horaires. Les
séries CAMS (ADR-0023) se choisissent par le paramètre ``source``.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterator
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.main import app
from kuma_data_core.core.config import get_settings
from kuma_data_core.db.session import get_engine, obtenir_session

pytestmark = pytest.mark.integration

GHI = "nasa_power_ghi_horaire_bfa_com_ouagadougou"
GHI_CAMS = "cams_ghi_horaire_bfa_com_ouagadougou"
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


def _ghi_par_jour(
    client: TestClient, headers: dict[str, str], source: str = "nasa_power"
) -> list[float]:
    """GHI 2024 de l'endpoint horaire, cumulé par jour UTC (kWh/m²/jour)."""
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/ghi",
        params={"periode_debut": "2024-01-01", "periode_fin": "2024-12-31", "source": source},
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


def test_horaire_source_cams(client: TestClient, headers_auth: dict[str, str]) -> None:
    """``source`` choisit la série : sans lui, NASA POWER, source du relais (ADR-0023)."""
    maxima: dict[str | None, float] = {}
    attendue = {None: "nasa_power", "nasa_power": "nasa_power", "cams_radiation": "cams_radiation"}
    for source in (None, "nasa_power", "cams_radiation"):
        params = {"periode_debut": "2024-06-01", "periode_fin": "2024-06-02"}
        if source is not None:
            params["source"] = source
        response = client.get("/v1/horaire/bfa_dep_dori/ghi", params=params, headers=headers_auth)
        assert response.status_code == 200, response.text
        assert response.json()["source"] == attendue[source]
        resultats = response.json()["resultats"]
        assert len(resultats) == 48
        assert {r["statut_editorial"] for r in resultats} == {"valide_auto"}
        maxima[source] = max(r["valeur"] for r in resultats)
    assert maxima[None] == maxima["nasa_power"] != maxima["cams_radiation"]


def test_ghi_ciel_clair_sans_relais(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le GHI par ciel clair et la série CAMS ne se servent que stockés, sans relais amont."""
    response = client.get(
        "/v1/horaire/bfa_dep_dori/ghi_ciel_clair",
        params={"periode_debut": "2024-06-01", "periode_fin": "2024-06-01"},
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    resultats = response.json()["resultats"]
    assert len(resultats) == 24 and resultats[12]["valeur"] > 900.0
    refus = [
        ("bfa_dep_dori", "ghi_ciel_clair", "2020-06-01", None, "La plage demandee"),
        ("bfa_dep_dori", "ghi", "2020-06-01", "cams_radiation", "La plage demandee"),
        (
            "bfa_dep_fo",
            "ghi_ciel_clair",
            "2024-06-01",
            None,
            "Aucune serie horaire stockee pour cette localite et cette grandeur.",
        ),
        (
            "bfa_dep_fo",
            "ghi",
            "2024-06-01",
            "cams_radiation",
            "Aucune serie horaire stockee pour cette localite, grandeur et source.",
        ),
    ]
    for localite, grandeur, jour, source, message in refus:
        params = {"periode_debut": jour, "periode_fin": jour}
        if source is not None:
            params["source"] = source
        response = client.get(
            f"/v1/horaire/{localite}/{grandeur}", params=params, headers=headers_auth
        )
        assert response.status_code == 400, response.text
        erreur = response.json()["erreur"]
        assert erreur["code"] == "PLAGE_TEMPORELLE_NON_DISPONIBLE"
        assert erreur["message"].startswith(message)
        # La plage de la série stockée accompagne le refus quand la série existe.
        plage = erreur["details"].get("plage_disponible")
        assert plage == ("2021-01-01 / 2025-12-31" if localite == "bfa_dep_dori" else None)


def test_relais_reserve_a_nasa_power(
    client: TestClient, headers_auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hors du stocké, seule NASA POWER se relaie ; CAMS et le ciel clair ne sortent jamais."""
    appels: list[dict[str, Any]] = []

    def relais(**kwargs: Any) -> SimpleNamespace:
        appels.append(kwargs)
        heures = {f"20190601{h:02d}": float(h) for h in range(24)}
        return SimpleNamespace(
            properties=SimpleNamespace(parameter={kwargs["parameters"][0]: heures})
        )

    monkeypatch.setattr("kuma_data_core.api.v1.horaire.fetch_hourly", relais)
    plage = {"periode_debut": "2019-06-01", "periode_fin": "2019-06-01"}
    for grandeur, source in (("ghi", "cams_radiation"), ("ghi_ciel_clair", None)):
        params = dict(plage, **({"source": source} if source else {}))
        response = client.get(
            f"/v1/horaire/bfa_com_ouagadougou/{grandeur}", params=params, headers=headers_auth
        )
        assert response.status_code == 400, response.text
    assert appels == []
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/ghi",
        params=dict(plage, source="nasa_power"),
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    assert len(appels) == 1
    assert response.json()["source"] == "nasa_power"
    resultats = response.json()["resultats"]
    assert len(resultats) == 24
    assert {r["statut_editorial"] for r in resultats} == {"passe_plat_non_valide"}


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


def test_poa_horaire_sur_cams(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le POA horaire part aussi de la série CAMS, dont il trouve la compagne DHI (ADR-0023).

    Plan horizontal : le GHI de l'année à 0,1 % près ; à 15° plein sud, le plan gagne
    3,5 %, comme avec NASA POWER.
    """
    poa = {
        inclinaison: _resultats(
            client,
            headers_auth,
            "poa_parametrable",
            code_serie_source=GHI_CAMS,
            inclinaison_deg=inclinaison,
            orientation_deg=180,
            albedo_sol=0.2,
            **HORAIRE_2024,
        )
        for inclinaison in (0, 15)
    }
    ghi = _ghi_par_jour(client, headers_auth, "cams_radiation")
    assert len(poa[0]) == len(ghi) == 366
    assert abs(sum(poa[0]) - sum(ghi)) < 1e-3 * sum(ghi)
    assert max(abs(p - g) / g for p, g in zip(poa[0], ghi, strict=True)) < 0.01
    assert 1.03 < statistics.mean(poa[15]) / statistics.mean(ghi) < 1.04


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


def test_plage_horaire_trop_longue_en_422(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Plus de 366 jours par requête : 422 dans l'enveloppe Kuma."""
    response = client.get(
        "/v1/horaire/bfa_com_ouagadougou/ghi",
        params={"periode_debut": "2022-01-01", "periode_fin": "2024-12-31"},
        headers=headers_auth,
    )
    assert response.status_code == 422, response.text
    assert response.json()["erreur"]["code"] == "VALIDATION_VALEUR_INVALIDE"


def _disponibilite(
    client: TestClient, headers: dict[str, str], chemin: str, **params: Any
) -> dict[str, Any]:
    response = client.get(f"/v1/horaire/{chemin}/disponibilite", params=params, headers=headers)
    assert response.status_code == 200, response.text
    reponse: dict[str, Any] = response.json()
    return reponse


def test_disponibilite_selon_la_source(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Sans source, la plage du relais NASA POWER ; avec CAMS, celle de la série stockée."""
    relais = _disponibilite(client, headers_auth, "bfa_com_ouagadougou/ghi")
    fin_relais = (date.today() - timedelta(days=151)).isoformat()
    assert (relais["source"], relais["plage_disponible"], relais["statut_editorial"]) == (
        "nasa_power",
        {"debut": "2001-01-01", "fin": fin_relais},
        "passe_plat_non_valide",
    )
    cams = _disponibilite(client, headers_auth, "bfa_com_ouagadougou/ghi", source="cams_radiation")
    assert (cams["source"], cams["plage_disponible"], cams["statut_editorial"]) == (
        "cams_radiation",
        {"debut": "2021-01-01", "fin": "2025-12-31"},
        "valide_auto",
    )
    # Le GHI par ciel clair, que seul CAMS sert, ne se relaie pas.
    ciel_clair = _disponibilite(client, headers_auth, "bfa_com_ouagadougou/ghi_ciel_clair")
    assert (ciel_clair["source"], ciel_clair["plage_disponible"]["fin"]) == (
        "cams_radiation",
        "2025-12-31",
    )


def test_disponibilite_en_edition_figee(
    client: TestClient, headers_auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans relais, la plage est celle de la série stockée ; sans série, 404.

    Toutes les localités ont l'horaire NASA POWER (ADR-0026) ; le GHI par ciel
    clair n'existe, stocké, qu'aux points pilotes (CAMS Radiation).
    """
    figee = get_settings().model_copy(update={"edition_figee": True})
    monkeypatch.setattr("kuma_data_core.api.v1.horaire.get_settings", lambda: figee)
    stockee = _disponibilite(client, headers_auth, "bfa_dep_dori/ghi")
    assert (stockee["source"], stockee["plage_disponible"], stockee["statut_editorial"]) == (
        "nasa_power",
        {"debut": "2021-01-01", "fin": "2025-12-31"},
        "valide_auto",
    )
    response = client.get(
        "/v1/horaire/bfa_prov_kadiogo/ghi_ciel_clair/disponibilite", headers=headers_auth
    )
    assert response.status_code == 404, response.text
    assert response.json()["erreur"]["code"] == "RESSOURCE_SERIE_INCONNUE"


def test_code_court_inconnu(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Seul le code complet de la localité est reconnu : un code court répond 404."""
    response = client.get(
        "/v1/horaire/com_ouagadougou/ghi",
        params={"periode_debut": "2024-01-01", "periode_fin": "2024-01-01"},
        headers=headers_auth,
    )
    assert response.status_code == 404, response.text
    assert response.json()["erreur"]["code"] == "RESSOURCE_LOCALITE_INCONNUE"


def test_disponibilite_sans_serie_stockee(client: TestClient, headers_auth: dict[str, str]) -> None:
    """L'horaire CAMS n'existe qu'aux points pilotes : ailleurs, 404."""
    response = client.get(
        "/v1/horaire/bfa_prov_kadiogo/ghi/disponibilite",
        params={"source": "cams_radiation"},
        headers=headers_auth,
    )
    assert response.status_code == 404, response.text
    assert response.json()["erreur"]["code"] == "RESSOURCE_SERIE_INCONNUE"
