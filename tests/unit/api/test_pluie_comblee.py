"""Tests unitaires du comblement de la pluie pour le modèle de salissure (ADR-0017)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from kuma_data_core.api.v1.grandeurs import (
    PLUIE_COMBLEE_MAX_JOURS,
    _combler_pluie,
    _mention_pluie_comblee,
)

pytestmark = pytest.mark.unit

_DEBUT = date(2025, 11, 25)


def _pluie(absents: set[int], n: int = 30) -> dict[date, float]:
    return {_DEBUT + timedelta(days=i): 1.0 for i in range(n) if i not in absents}


def test_jour_sans_valeur_compte_zero() -> None:
    """Un jour sans valeur à l'intérieur de la série vaut 0 mm ; les bords ne bougent pas."""
    pluie, combles = _combler_pluie(_pluie({7}))
    assert combles == [date(2025, 12, 2)]
    assert pluie[date(2025, 12, 2)] == 0.0
    assert min(pluie) == _DEBUT and len(pluie) == 30


def test_serie_complete_ou_vide() -> None:
    """Rien à combler dans une série sans trou ni dans une série vide."""
    assert _combler_pluie(_pluie(set())) == (_pluie(set()), [])
    assert _combler_pluie({}) == ({}, [])


def test_serie_trop_lacunaire_laissee_en_l_etat() -> None:
    """Au-delà du plafond, rien n'est comblé : le contrôle de contiguïté refusera la série."""
    absents = set(range(1, PLUIE_COMBLEE_MAX_JOURS + 2))
    pluie, combles = _combler_pluie(_pluie(absents))
    assert combles == [] and len(pluie) == 30 - len(absents)


def test_mention_limitee_a_la_fenetre_et_abregee() -> None:
    """La mention ne cite que les jours de la fenêtre, cinq au plus, puis leur nombre."""
    dates = [_DEBUT + timedelta(days=i) for i in range(30)]
    assert _mention_pluie_comblee([], dates) == ""
    assert _mention_pluie_comblee([date(2024, 1, 1)], dates) == ""
    assert _mention_pluie_comblee([date(2025, 12, 2)], dates) == (
        " Pluie sans valeur comptée 0 mm, aucun nettoyage ce jour-là : 2025-12-02."
    )
    sept = [_DEBUT + timedelta(days=i) for i in range(1, 8)]
    assert _mention_pluie_comblee(sept, dates).endswith("2025-11-30 et 2 autres jours.")
