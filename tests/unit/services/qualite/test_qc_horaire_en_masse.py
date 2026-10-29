"""Tests unitaires de la qualification horaire en masse (ADR-0026).

``qualifier_series_horaires`` doit donner, valeur par valeur, le statut et le
commentaire que :func:`evaluer_instant` donne à la même mesure, avec la même
géométrie solaire. Les valeurs tirées au hasard couvrent les rejets, les
drapeaux « extrêmement rare », de fermeture et de ratio diffus.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]
import pytest

from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import (
    S0_W_PAR_M2,
    MesureHoraire,
    evaluer_instant,
    qualifier_series_horaires,
)

pytestmark = pytest.mark.unit

_LATITUDE, _LONGITUDE = 12.37, -1.52
_INSTANTS = [datetime(2024, 3, 1, tzinfo=UTC) + timedelta(hours=h) for h in range(24 * 60)]
_BORNES: dict[str, tuple[float, float]] = {
    "ghi": (-10.0, 1500.0),
    "dni": (-10.0, 1500.0),
    "dhi": (-10.0, 1000.0),
    "t2m": (-100.0, 70.0),
}


def _valeurs(grandeurs: tuple[str, ...]) -> dict[str, list[float]]:
    rng = np.random.default_rng(2026)
    return {g: rng.uniform(*_BORNES[g], len(_INSTANTS)).round(2).tolist() for g in grandeurs}


def _reference(
    valeurs: dict[str, list[float]], instants: list[datetime] = _INSTANTS
) -> dict[str, list[tuple[str, str]]]:
    """Verdicts de :func:`evaluer_instant`, instant par instant, géométrie du runner."""
    temps = pd.DatetimeIndex(instants) + pd.Timedelta(DECALAGE_MILIEU_HEURE)
    zeniths = pvlib.solarposition.get_solarposition(temps, _LATITUDE, _LONGITUDE)["zenith"]
    sas = pvlib.irradiance.get_extra_radiation(temps, solar_constant=S0_W_PAR_M2)
    attendus: dict[str, list[tuple[str, str]]] = {g: [] for g in valeurs}
    for i, (zenith, sa) in enumerate(zip(zeniths.to_numpy(), sas.to_numpy(), strict=True)):
        sza = float(zenith)
        mu0 = max(0.0, math.cos(math.radians(sza)))
        mesures = [MesureHoraire(row_id=0, grandeur=g, valeur=v[i]) for g, v in valeurs.items()]
        verdicts = evaluer_instant(mesures, float(sa), mu0, sza)
        for mesure, verdict in zip(mesures, verdicts, strict=True):
            attendus[mesure.grandeur].append((verdict.statut_cible, verdict.commentaire()))
    return attendus


@pytest.mark.parametrize(
    "grandeurs", [("ghi", "dni", "dhi", "t2m"), ("ghi", "dni", "dhi"), ("ghi",), ("t2m",)]
)
def test_memes_verdicts_que_le_controle_par_instant(grandeurs: tuple[str, ...]) -> None:
    """Rejets et drapeaux identiques, avec ou sans tests croisés."""
    valeurs = _valeurs(grandeurs)

    verdicts = qualifier_series_horaires(
        _INSTANTS, valeurs, _LATITUDE, _LONGITUDE, DECALAGE_MILIEU_HEURE
    )

    attendus = _reference(valeurs)
    assert verdicts == attendus
    commentaires = " ".join(c for liste in attendus.values() for _, c in liste)
    assert "rejet" in commentaires
    if "dhi" in grandeurs:
        assert all(f in commentaires for f in ("extremement rare", "fermeture", "ratio diffus"))


def test_series_de_longueurs_differentes_refusees() -> None:
    with pytest.raises(ValueError, match="ghi"):
        qualifier_series_horaires(
            _INSTANTS, {"ghi": [1.0]}, _LATITUDE, _LONGITUDE, DECALAGE_MILIEU_HEURE
        )


def test_aucun_instant() -> None:
    assert qualifier_series_horaires([], {"t2m": []}, 0.0, 0.0, DECALAGE_MILIEU_HEURE) == {
        "t2m": []
    }


def test_seuils_exacts_et_valeurs_absentes() -> None:
    """Seuils de 50 W/m² tout juste et valeurs NaN : mêmes verdicts qu'instant par instant."""
    nan = float("nan")
    # (ghi, dni, dhi, t2m) à midi : tests croisés à la limite, puis valeurs absentes.
    cas = [
        (50.0, 0.0, 60.0, 30.0),
        (50.000001, 0.0, 60.0, 30.0),
        (100.0, 0.0, 105.0, 30.0),
        (200.0, 0.0, 50.0, 30.0),
        (200.0, 0.0, 50.000001, 30.0),
        (nan, 500.0, 100.0, 30.0),
        (600.0, nan, 100.0, 30.0),
        (600.0, 500.0, nan, 30.0),
        (600.0, 500.0, 100.0, nan),
    ]
    instants = [datetime(2024, 3, 1, 11, tzinfo=UTC)] * len(cas)
    valeurs = {g: [c[i] for c in cas] for i, g in enumerate(("ghi", "dni", "dhi", "t2m"))}

    verdicts = qualifier_series_horaires(
        instants, valeurs, _LATITUDE, _LONGITUDE, DECALAGE_MILIEU_HEURE
    )

    assert verdicts == _reference(valeurs, instants)


def test_instants_sans_fuseau_refuses() -> None:
    """Un instant sans fuseau est refusé : la géométrie solaire se calcule en UTC."""
    with pytest.raises(ValueError, match="sans fuseau"):
        qualifier_series_horaires(
            [datetime(2024, 3, 1, 11)], {"t2m": [30.0]}, 0.0, 0.0, DECALAGE_MILIEU_HEURE
        )
