"""Tests d'intégration des grandeurs métier calculées à la volée (ADR-0013, ADR-0015).

Province du Kadiogo : GHI, DNI et DHI journaliers NASA POWER (0007), météo
journalière (0010), séries mensuelles (0006) et particules fines CAMS EAC4
(0013). Vérifie que chaque grandeur trouve ses compagnes et renvoie des valeurs
plausibles.
"""

from __future__ import annotations

import statistics
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

GHI = "nasa_power_ghi_journalier_bfa_prov_kadiogo"
T2M = "nasa_power_t2m_journalier_bfa_prov_kadiogo"
PM2_5 = "cams_eac4_pm2_5_journalier_bfa_prov_kadiogo"
ANNEE_2024 = {"periode_debut": "2024-01-01", "periode_fin": "2024-12-31"}


def _resultats(
    client: TestClient, headers: dict[str, str], chemin: str, **params: Any
) -> list[float]:
    response = client.get(f"/v1/grandeurs/{chemin}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [r["valeur"] for r in response.json()["resultats"]]


def _ghi(client: TestClient, headers: dict[str, str], debut: str, fin: str) -> list[float]:
    response = client.get(f"/v1/series/{GHI}?from={debut}&to={fin}&limit=400", headers=headers)
    assert response.status_code == 200
    return [m["valeur"] for m in response.json()["mesures"]]


def test_poa_avec_compagnes_dni_dhi(client: TestClient, headers_auth: dict[str, str]) -> None:
    """2024 : les compagnes DNI et DHI (servies depuis 2001) sont trouvées malgré un GHI de 1991.

    Perez au midi solaire avec le DNI et le DHI de NASA POWER ne redonne pas le GHI sur
    un plan horizontal (biais documenté, ADR-0013) ; le repli, lui, le redonnerait.
    """
    poa = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        inclinaison_deg=15,
        orientation_deg=180,
        albedo_sol=0.2,
        **ANNEE_2024,
    )
    ghi = _ghi(client, headers_auth, "2024-01-01", "2024-12-31")
    assert len(poa) == len(ghi) == 366
    assert statistics.mean(ghi) < statistics.mean(poa) < 1.2 * statistics.mean(ghi)
    horizontal = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        inclinaison_deg=0,
        orientation_deg=180,
        albedo_sol=0.2,
        **ANNEE_2024,
    )
    assert statistics.mean(horizontal) > 1.03 * statistics.mean(ghi)


def test_poa_repli_avant_2001_conserve_le_ghi(
    client: TestClient, headers_auth: dict[str, str]
) -> None:
    """1995 : sans DNI ni DHI, le repli (Erbs journalier) redonne le GHI sur un plan horizontal."""
    poa = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        periode_debut="1995-01-01",
        periode_fin="1995-12-31",
        inclinaison_deg=0,
        orientation_deg=180,
        albedo_sol=0.2,
    )
    ghi = _ghi(client, headers_auth, "1995-01-01", "1995-12-31")
    assert len(poa) == len(ghi) == 365
    assert max(abs(p - g) for p, g in zip(poa, ghi, strict=True)) < 1e-6


def test_poa_repli_gain_du_plan_incline(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Décembre 1995, 15° plein sud : le repli corrigé décompose le direct et le plan gagne.

    L'ancien repli traitait le total du jour comme un éclairement : tout devenait diffus
    et le plan incliné ne gagnait rien (rapport d'environ 0,99).
    """
    poa = _resultats(
        client,
        headers_auth,
        "poa_parametrable",
        code_serie_source=GHI,
        periode_debut="1995-12-01",
        periode_fin="1995-12-31",
        inclinaison_deg=15,
        orientation_deg=180,
        albedo_sol=0.2,
    )
    ghi = _ghi(client, headers_auth, "1995-12-01", "1995-12-31")
    assert statistics.mean(poa) > 1.05 * statistics.mean(ghi)


def test_poa_bifacial(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Le POA bifacial trouve ses compagnes et dépasse le POA monofacial."""
    commun = {"code_serie_source": GHI, "inclinaison_deg": 15, "orientation_deg": 180, **ANNEE_2024}
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
    )
    monofacial = _resultats(client, headers_auth, "poa_parametrable", albedo_sol=0.25, **commun)
    assert len(bifacial) == 366
    assert statistics.mean(bifacial) > statistics.mean(monofacial)


def test_productibles_avec_temperature(client: TestClient, headers_auth: dict[str, str]) -> None:
    """La compagne T2M rend le productible thermique et le PR corrigé calculables."""
    thermique = _resultats(
        client,
        headers_auth,
        "productible_correction_thermique",
        code_serie_source=GHI,
        noct_degc=45,
        coeff_temp_pourcent_par_degc=-0.35,
        puissance_stc_wc=1000,
        **ANNEE_2024,
    )
    corrige = _resultats(
        client,
        headers_auth,
        "productible_pr_fourni",
        code_serie_source=GHI,
        pr_fourni=0.8,
        correction="temperature",
        puissance_stc_wc=1000,
        noct_degc=45,
        coeff_temp_pourcent_par_degc=-0.35,
        **ANNEE_2024,
    )
    brut = _resultats(
        client,
        headers_auth,
        "productible_pr_fourni",
        code_serie_source=GHI,
        pr_fourni=0.8,
        correction="aucune",
        puissance_stc_wc=1000,
        **ANNEE_2024,
    )
    assert len(thermique) == len(corrige) == len(brut) == 366
    assert 4.0 < statistics.mean(thermique) < 7.0
    # Au Burkina, les cellules travaillent au-dessus de 25 °C : la correction réduit le productible.
    assert statistics.mean(corrige) < statistics.mean(brut)


def test_energie_utile_ecs(client: TestClient, headers_auth: dict[str, str]) -> None:
    """L'énergie utile d'un capteur thermique se calcule avec la compagne T2M."""
    ecs = _resultats(
        client,
        headers_auth,
        "energie_utile_ecs",
        code_serie_source=GHI,
        rendement_optique_eta0=0.75,
        pertes_lineaires_a1=3.5,
        pertes_quadratiques_a2=0.015,
        temperature_fluide_entree_degc=25,
        **ANNEE_2024,
    )
    assert len(ecs) == 366
    assert all(v >= 0.0 for v in ecs)


def test_degres_jours_de_climatisation(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Les degrés-jours de climatisation se calculent sur la série T2M (cumuls mensuels)."""
    djc = _resultats(
        client,
        headers_auth,
        "degre_jour_climatisation",
        code_serie_source=T2M,
        base_temperature_degc=26,
        **ANNEE_2024,
    )
    assert len(djc) == 12
    assert sum(djc) > 0.0


@pytest.mark.parametrize("localite", ["bfa_prov_kadiogo", "bfa_com_ouagadougou", "bfa_dep_fo"])
def test_ghi_exceedance(client: TestClient, headers_auth: dict[str, str], localite: str) -> None:
    """P50 et P90 sur la normale 1991-2020 de la série mensuelle, pour toute localité."""
    response = client.get(f"/v1/grandeurs/ghi_exceedance/{localite}", headers=headers_auth)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code_serie_source"] == f"nasa_power_ghi_mensuel_{localite}"
    assert (payload["periode"], payload["base_annees"]) == ("1991-2020", 30)
    assert 1_900 < payload["p90"] < payload["p50"] < 2_400


def test_pr_realiste_avec_temperature(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Corrigé de la température, le PR réaliste reste en moyenne sous le PR fourni."""
    response = client.get(
        f"/v1/grandeurs/pr_realiste/{GHI}",
        params={
            "pr_fourni": 0.8,
            "correction": "temperature",
            "noct_degc": 45,
            "coeff_temp_pourcent_par_degc": -0.35,
        },
        headers=headers_auth,
    )
    assert response.status_code == 200, response.text
    valeurs = [m["pr_realiste"] for m in response.json()["mesures_journalier"]]
    assert valeurs
    assert all(0.5 < v < 0.9 for v in valeurs)
    assert statistics.mean(valeurs) < 0.8


def _pertes(client: TestClient, headers: dict[str, str], province: str) -> dict[str, float]:
    serie = f"cams_eac4_pm2_5_journalier_bfa_prov_{province}"
    response = client.get(f"/v1/grandeurs/taux_salissure_proxy/{serie}", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["periode"] == "2005-01-01/2025-12-31"
    return {m["instant"]: m["perte_pct"] for m in payload["mesures"]}


def test_taux_salissure_proxy(client: TestClient, headers_auth: dict[str, str]) -> None:
    """Salissure HSU 2005-2025 au Kadiogo : 2,2 % en moyenne, 6,6 % en février, lavée l'été."""
    pertes = _pertes(client, headers_auth, "kadiogo")
    assert len(pertes) == 7_670
    assert all(0.0 <= p < 50.0 for p in pertes.values())
    assert statistics.mean(pertes.values()) == pytest.approx(2.24, abs=0.05)
    fevrier = [p for jour, p in pertes.items() if jour[5:7] == "02"]
    hivernage = [p for jour, p in pertes.items() if jour[5:7] in ("06", "07", "08", "09")]
    assert statistics.mean(fevrier) == pytest.approx(6.6, abs=0.1)
    assert statistics.mean(hivernage) < 0.1


def test_salissure_du_nord_au_sud(client: TestClient, headers_auth: dict[str, str]) -> None:
    """La salissure baisse du nord sahélien (Oudalan) au sud-ouest humide (Poni)."""
    moyennes = [
        statistics.mean(_pertes(client, headers_auth, p).values())
        for p in ("oudalan", "kadiogo", "poni")
    ]
    assert moyennes == sorted(moyennes, reverse=True)


def test_pr_realiste_avec_salissure(client: TestClient, headers_auth: dict[str, str]) -> None:
    """La salissure ne peut que baisser le PR corrigé de la température, jour par jour."""

    def _pr(correction: str) -> dict[str, float]:
        response = client.get(
            f"/v1/grandeurs/pr_realiste/{GHI}",
            params={
                "pr_fourni": 0.8,
                "correction": correction,
                "noct_degc": 45,
                "coeff_temp_pourcent_par_degc": -0.35,
            },
            headers=headers_auth,
        )
        assert response.status_code == 200, response.text
        return {m["instant"]: m["pr_realiste"] for m in response.json()["mesures_journalier"]}

    thermique = _pr("temperature")
    complet = _pr("temperature_salissure")
    assert min(complet) == "2005-01-01"
    assert set(complet) <= set(thermique)
    assert all(complet[j] <= thermique[j] + 1e-12 for j in complet)
    assert statistics.mean(complet.values()) < statistics.mean(thermique[j] for j in complet)
