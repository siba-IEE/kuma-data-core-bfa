"""Tests unitaires des définitions de grandeurs dérivées (ADR-0012)."""

from __future__ import annotations

import pytest

from kuma_data_core.db.seeds.grandeurs_derivees_bfa import ECARTS, code_serie_fraction_diffuse

pytestmark = pytest.mark.unit


def test_ecarts_identifiants_et_codes() -> None:
    """Ids 35 à 41 uniques, codes distincts et dans la limite du référentiel."""
    assert sorted(e.grandeur_id for e in ECARTS) == list(range(35, 42))
    assert len({e.grandeur_code for e in ECARTS}) == len(ECARTS)
    assert all(len(e.grandeur_code) <= 80 for e in ECARTS)
    assert ECARTS[0].code_serie("bfa_dep_fo") == "ecart_ghi_sarah3_nasa_bfa_dep_fo"
    assert code_serie_fraction_diffuse("bfa_dep_fo") == "fraction_diffuse_nasa_power_bfa_dep_fo"


def test_volume_attendu() -> None:
    """398 localités par écart : 663 864 lignes au total (migration 0009)."""
    assert sum(398 * e.nb_mois for e in ECARTS) == 663_864
