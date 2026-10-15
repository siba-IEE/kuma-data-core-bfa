"""Tests unitaires de ``services.grandeurs.poa_parametrable``.

Couvre les cas standards Perez (DNI+DHI disponibles) et fallback
Liu-Jordan (GHI seul) sur la localite pilote Conakry-Kaloum.

Fonctions pures sans mock DB.

Convention fixtures : les valeurs GHI/DNI/DHI utilisees dans les tests
respectent la relation physique fondamentale ``GHI = DNI x cos(zenith) +
DHI`` (ou ``zenith`` est l'angle zenithal solaire calcule par pvlib pour
la localite et l'instant donnes). Cela garantit que pvlib reconstitue
une POA coherente avec le GHI declare lorsque le plan est horizontal,
sans avoir a elargir les tolerances de test pour absorber des
incoherences de fixture.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pandas as pd
import pvlib
import pytest

from kuma_data_core.api.v1.schemas.grandeurs import ParametresPOA
from kuma_data_core.services.grandeurs.poa_parametrable import (
    NIVEAU_CONFIANCE_DERIVE_F2_V1,
    UNITE_POA,
    MesureHeurePOA,
    MesureJourPOA,
    _decomposer_jour,
    _fraction_diffuse_erbs_journaliere,
    _irradiation_extraterrestre_jour,
    calculer_poa_parametrable,
    calculer_poa_parametrable_horaire,
    geometrie_et_direct_horaires,
)

pytestmark = pytest.mark.unit


# Coordonnees Conakry-Kaloum (localite pilote).
_CONAKRY_LAT = 9.5092
_CONAKRY_LON = -13.7122


def _zenith_solaire_midi_local(jour: date) -> float:
    """Renvoie l'angle zenithal solaire (degres) a midi solaire Conakry.

    Reproduit la convention de ``poa_parametrable._midi_solaire_utc`` :
    midi solaire local UTC = 12:00 UTC - longitude/15. Permet de
    construire des fixtures DNI/DHI/GHI physiquement coherentes.
    """
    decalage_heures = -_CONAKRY_LON / 15.0
    instant_utc = datetime(jour.year, jour.month, jour.day, 12, 0, 0, tzinfo=UTC)
    instant_midi = pd.DatetimeIndex([instant_utc + pd.Timedelta(hours=decalage_heures)])
    solpos = pvlib.solarposition.get_solarposition(instant_midi, _CONAKRY_LAT, _CONAKRY_LON)
    return float(solpos["zenith"].iloc[0])


def _ghi_coherent(dni: float, dhi: float, zenith_deg: float) -> float:
    """Calcule le GHI coherent physiquement avec DNI, DHI et zenith.

    Formule fondamentale : ``GHI = DNI x cos(zenith) + DHI``. Cette
    relation est exacte (decomposition de l'irradiance globale en
    composantes directe horizontale et diffuse horizontale).
    """
    return dni * math.cos(math.radians(zenith_deg)) + dhi


def _parametres_poa_standard() -> ParametresPOA:
    """Parametres POA typiques pour Conakry : plein sud (180°), inclinaison 10°."""
    return ParametresPOA(
        code_serie_source="gin_conakry_ghi_nasa_power_2021_2025",
        periode_debut=date(2024, 6, 15),
        periode_fin=date(2024, 6, 15),
        inclinaison_deg=10,
        orientation_deg=180,
        albedo_sol=0.2,
    )


def test_t_poa_1_cas_standard_perez() -> None:
    """T-POA-1 : cas standard journalier avec GHI+DNI+DHI disponibles.

    Verifie que le calcul Perez retourne un POA positif coherent avec
    l'irradiance GHI d'entree, niveau de confiance 'B', unite attendue.
    """
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": date(2024, 6, 15),
            "ghi": 600.0,  # W/m² instantane midi solaire
            "dni": 700.0,
            "dhi": 150.0,
        }
    ]
    resultats = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=_parametres_poa_standard(),
    )
    assert len(resultats) == 1
    r = resultats[0]
    assert r.granularite == "journalier"
    assert r.instant == date(2024, 6, 15)
    assert r.unite == UNITE_POA
    assert r.niveau_confiance == NIVEAU_CONFIANCE_DERIVE_F2_V1
    # POA Conakry plein sud 10° autour de juin doit etre proche de la GHI
    # (Conakry quasi-equatorial, inclinaison faible -> POA ~ GHI).
    assert 400.0 < r.valeur < 800.0


def test_t_poa_2_fallback_liu_jordan() -> None:
    """T-POA-2 : DNI/DHI absents -> fallback Liu-Jordan, Erbs journalier.

    Sur un total journalier (kWh/m²/jour), la décomposition garde le GHI en
    plan horizontal et donne un POA du même ordre que le GHI pour un plan
    peu incliné.
    """
    ghi_jour = 6.0
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": date(2024, 6, 15),
            "ghi": ghi_jour,
            "dni": None,
            "dhi": None,
        }
    ]
    resultats = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=_parametres_poa_standard(),
    )
    assert len(resultats) == 1
    assert 0.85 * ghi_jour < resultats[0].valeur < 1.05 * ghi_jour


def test_t_poa_2b_decomposition_journaliere_erbs() -> None:
    """T-POA-2b : Erbs journalier, KT et fraction diffuse plausibles, GHI conservé."""
    jour = date(2024, 4, 15)
    h0, omega_s = _irradiation_extraterrestre_jour(12.37, jour)
    assert 9.5 < h0 < 11.0  # Ouagadougou, avril
    assert 89.0 < omega_s < 95.0
    dni, dhi = _decomposer_jour(6.5, 12.37, jour, zenith_midi_deg=3.0)
    assert 0.25 < dhi / 6.5 < 0.5
    assert abs(dni * math.cos(math.radians(3.0)) + dhi - 6.5) < 1e-9
    assert _fraction_diffuse_erbs_journaliere(0.9, 85.0) == 0.175
    assert _fraction_diffuse_erbs_journaliere(0.9, 75.0) == 0.143


def test_t_poa_3_liste_vide() -> None:
    """T-POA-3 : mesures vide -> liste resultats vide."""
    resultats = calculer_poa_parametrable(
        mesures=[],
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=_parametres_poa_standard(),
    )
    assert resultats == []


def test_t_poa_4_serie_pluri_jours() -> None:
    """T-POA-4 : serie de plusieurs jours -> ordre preserve, niveau 'B' uniforme."""
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": date(2024, 1, d),
            "ghi": 500.0,
            "dni": 600.0,
            "dhi": 130.0,
        }
        for d in (1, 2, 3, 4, 5)
    ]
    resultats = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=_parametres_poa_standard(),
    )
    assert len(resultats) == 5
    assert [r.instant for r in resultats] == [date(2024, 1, d) for d in (1, 2, 3, 4, 5)]
    assert all(r.niveau_confiance == NIVEAU_CONFIANCE_DERIVE_F2_V1 for r in resultats)


def test_t_poa_5_idempotence() -> None:
    """T-POA-5 : deux appels avec memes parametres -> meme reponse."""
    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": date(2024, 6, 15),
            "ghi": 600.0,
            "dni": 700.0,
            "dhi": 150.0,
        }
    ]
    params = _parametres_poa_standard()
    r1 = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=params,
    )
    r2 = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=params,
    )
    assert r1[0].valeur == r2[0].valeur


def test_t_poa_6_inclinaison_zero_proche_ghi() -> None:
    """T-POA-6 : inclinaison=0 (plan horizontal) -> POA ~ GHI.

    Fixture physiquement coherente : DNI et DHI sont choisis arbitrairement
    en plage tropicale realiste, puis GHI est derive via la relation
    fondamentale GHI = DNI x cos(zenith) + DHI ou zenith est l'angle
    zenithal solaire reel pour Conakry-Kaloum a midi solaire local le
    15 juin 2024. Sous cette contrainte, pvlib doit retourner une POA
    horizontale identique au GHI a la precision numerique pres
    (tolerance 1% pour absorber d'eventuels arrondis pvlib internes).
    """
    jour = date(2024, 6, 15)
    zenith_deg = _zenith_solaire_midi_local(jour)
    dni = 700.0
    dhi = 130.0
    ghi = _ghi_coherent(dni, dhi, zenith_deg)

    mesures: list[MesureJourPOA] = [
        {
            "instant_mesure": jour,
            "ghi": ghi,
            "dni": dni,
            "dhi": dhi,
        }
    ]
    params = ParametresPOA(
        code_serie_source="x",
        periode_debut=jour,
        periode_fin=jour,
        inclinaison_deg=0,
        orientation_deg=180,
    )
    resultats = calculer_poa_parametrable(
        mesures=mesures,
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=params,
    )
    # Plan horizontal : POA doit etre numeriquement egal a GHI a 1% pres
    # (DNI/DHI/GHI respectent la relation physique fondamentale).
    assert abs(resultats[0].valeur - ghi) / ghi < 0.01


def test_t_poa_7_inclinaison_optimale_sud() -> None:
    """T-POA-7 : inclinaison ~latitude, orientation sud -> POA superieur a plan horizontal.

    En equateur boreal (Guinee 9°N) sur l'annee, plan horizontal capte
    plus en juin que plan incline ; mais en decembre, plan incline
    sud-orient capte plus. Le test verifie que pvlib retourne des POA
    differencies.
    """
    mesure_decembre: MesureJourPOA = {
        "instant_mesure": date(2024, 12, 15),
        "ghi": 500.0,
        "dni": 700.0,
        "dhi": 100.0,
    }
    params_horizontal = ParametresPOA(
        code_serie_source="x",
        periode_debut=date(2024, 12, 15),
        periode_fin=date(2024, 12, 15),
        inclinaison_deg=0,
        orientation_deg=180,
    )
    params_incline = ParametresPOA(
        code_serie_source="x",
        periode_debut=date(2024, 12, 15),
        periode_fin=date(2024, 12, 15),
        inclinaison_deg=20,
        orientation_deg=180,
    )
    r_horizontal = calculer_poa_parametrable(
        mesures=[mesure_decembre],
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=params_horizontal,
    )
    r_incline = calculer_poa_parametrable(
        mesures=[mesure_decembre],
        latitude_deg=_CONAKRY_LAT,
        longitude_deg=_CONAKRY_LON,
        parametres=params_incline,
    )
    # En decembre, plan incline plein sud capte plus que plan horizontal.
    assert r_incline[0].valeur > r_horizontal[0].valeur


# === Methode integration horaire (Perez par heure) ===========


def _mesures_horaires_journee(
    jour: date, heures_utc: range, dni: float = 800.0, dhi: float = 120.0
) -> list[MesureHeurePOA]:
    """Mesures horaires closure-consistantes (GHI = DNI·cos z + DHI, z au milieu
    de l'heure) pour des heures diurnes Conakry (zenith modere, Perez sans NaN)."""
    instants = [datetime(jour.year, jour.month, jour.day, h, tzinfo=UTC) for h in heures_utc]
    zeniths = pvlib.solarposition.get_solarposition(
        pd.DatetimeIndex(instants) + pd.Timedelta(minutes=30), _CONAKRY_LAT, _CONAKRY_LON
    )["zenith"]
    mesures: list[MesureHeurePOA] = []
    for instant, z in zip(instants, zeniths, strict=True):
        cosz = max(0.0, math.cos(math.radians(float(z))))
        mesures.append({"instant_mesure": instant, "ghi": dni * cosz + dhi, "dhi": dhi})
    return mesures


def _params_horaire(inclinaison: float, orientation: float = 180.0) -> ParametresPOA:
    return ParametresPOA(
        code_serie_source="gin_conakry_ghi_nasa_power_2001_2025",
        periode_debut=date(2024, 6, 1),
        periode_fin=date(2024, 6, 30),
        inclinaison_deg=inclinaison,
        orientation_deg=orientation,
        albedo_sol=0.2,
        methode="integration_horaire",
    )


def test_poa_h1_vide() -> None:
    """POA horaire sur mesures vides -> liste vide."""
    r = calculer_poa_parametrable_horaire([], _CONAKRY_LAT, _CONAKRY_LON, _params_horaire(20))
    assert r == []


def test_poa_h2_structure_un_jour() -> None:
    """Un jour d'heures diurnes -> 1 ResultatJournalier (structure + valeur > 0)."""
    mesures = _mesures_horaires_journee(date(2024, 6, 15), range(10, 16))
    r = calculer_poa_parametrable_horaire(mesures, _CONAKRY_LAT, _CONAKRY_LON, _params_horaire(20))
    assert len(r) == 1
    assert r[0].instant == date(2024, 6, 15)
    assert r[0].granularite == "journalier"
    assert r[0].unite == UNITE_POA
    assert r[0].niveau_confiance == NIVEAU_CONFIANCE_DERIVE_F2_V1
    assert r[0].valeur > 0.0


def test_poa_h3_tilt_zero_egale_ghi() -> None:
    """Invariant physique : a tilt=0, le POA journalier = GHI total du jour.

    Plan horizontal -> transposition identite (POA = GHI). Valide
    l'integration horaire + l'agregation + les unites independamment du
    detail du modele Perez.
    """
    mesures = _mesures_horaires_journee(date(2024, 6, 15), range(10, 16))
    r = calculer_poa_parametrable_horaire(mesures, _CONAKRY_LAT, _CONAKRY_LON, _params_horaire(0))
    ghi_jour_kwh = sum(m["ghi"] for m in mesures) / 1000.0
    assert abs(r[0].valeur - ghi_jour_kwh) < 1e-2


def test_poa_h4_multi_jours() -> None:
    """Heures sur 2 jours -> 2 ResultatJournalier ordonnes."""
    mesures = _mesures_horaires_journee(
        date(2024, 6, 15), range(10, 16)
    ) + _mesures_horaires_journee(date(2024, 6, 16), range(10, 16))
    r = calculer_poa_parametrable_horaire(mesures, _CONAKRY_LAT, _CONAKRY_LON, _params_horaire(20))
    assert len(r) == 2
    assert r[0].instant == date(2024, 6, 15)
    assert r[1].instant == date(2024, 6, 16)


def _journee_ciel_clair(jour: date) -> list[MesureHeurePOA]:
    """24 heures de ciel clair (Haurwitz au milieu de l'heure), DHI = 30 % du GHI."""
    index = pd.date_range(
        datetime(jour.year, jour.month, jour.day, tzinfo=UTC), periods=24, freq="h"
    )
    zenith = pvlib.solarposition.get_solarposition(
        index + pd.Timedelta(minutes=30), _CONAKRY_LAT, _CONAKRY_LON
    )["apparent_zenith"]
    ghi = pvlib.clearsky.haurwitz(zenith)["ghi"].to_numpy()
    return [
        {"instant_mesure": instant.to_pydatetime(), "ghi": float(g), "dhi": 0.3 * float(g)}
        for instant, g in zip(index, ghi, strict=True)
    ]


def test_poa_h5_journee_complete_horizontal_egale_ghi() -> None:
    """Sur 24 heures, lever et coucher compris, le plan horizontal retrouve le GHI du jour.

    Le direct est reconstruit sur GHI et DHI : tant que le DHI reste sous le GHI
    et que le soleil est levé au milieu de l'heure, chaque heure garde son
    énergie, quel que soit le DNI de la source (ADR-0014).
    """
    mesures = _journee_ciel_clair(date(2024, 6, 15))
    r = calculer_poa_parametrable_horaire(mesures, _CONAKRY_LAT, _CONAKRY_LON, _params_horaire(0))
    ghi_jour_kwh = sum(m["ghi"] for m in mesures) / 1000.0
    assert abs(r[0].valeur - ghi_jour_kwh) < 1e-3 * ghi_jour_kwh


def test_poa_h6_geometrie_au_milieu_de_l_heure() -> None:
    """La position solaire d'un instant HH:00 est celle de HH:30 (NASA POWER, ADR-0014)."""
    index = pd.DatetimeIndex([datetime(2024, 6, 15, h, tzinfo=UTC) for h in (7, 12, 18)])
    nul = pd.Series(0.0, index=index)
    solpos, _ = geometrie_et_direct_horaires(index, nul, nul, _CONAKRY_LAT, _CONAKRY_LON)
    attendu = pvlib.solarposition.get_solarposition(
        index + pd.Timedelta(minutes=30), _CONAKRY_LAT, _CONAKRY_LON
    )["zenith"].to_numpy()
    assert list(solpos.index) == list(index)
    assert solpos["zenith"].to_numpy() == pytest.approx(attendu)


def test_poa_h7_direct_reconstruit() -> None:
    """DNI = (GHI - DHI) / cos z ; nul sous l'horizon ou si DHI > GHI, borné à l'extraterrestre."""
    index = pd.DatetimeIndex([datetime(2024, 6, 15, h, tzinfo=UTC) for h in (2, 12, 13, 7)])
    ghi = pd.Series([0.0, 900.0, 300.0, 1000.0], index=index)
    dhi = pd.Series([0.0, 200.0, 350.0, 0.0], index=index)
    solpos, dni = geometrie_et_direct_horaires(index, ghi, dhi, _CONAKRY_LAT, _CONAKRY_LON)
    cosz = math.cos(math.radians(float(solpos["zenith"].iloc[1])))
    assert dni.iloc[0] == 0.0
    assert dni.iloc[1] == pytest.approx(700.0 / cosz)
    assert dni.iloc[2] == 0.0
    # 7 h 30 UTC, soleil bas : 1 000 W/m² de direct horizontal donneraient un DNI impossible.
    assert dni.iloc[3] == pytest.approx(pvlib.irradiance.get_extra_radiation(index[3:]).iloc[0])
