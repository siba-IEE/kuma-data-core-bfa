"""Tests unitaires des plafonds de confiance des grandeurs calculées (ADR-0025).

Le plafond monte à A pour un calcul exact sans modèle ni hypothèse (P50/P90) ;
les grandeurs paramétrables et les proxys restent au plus B, même sur des
mesures au sol A.
"""

from __future__ import annotations

from types import ModuleType

import pytest

from kuma_data_core.services.grandeurs import (
    degre_jour_climatisation,
    energie_utile_ecs,
    ghi_exceedance,
    poa_bifacial,
    poa_parametrable,
    pr_realiste,
    productible_correction_thermique,
    productible_pr_fourni,
    soiling_hsu,
)

pytestmark = pytest.mark.unit


def test_plafond_a_pour_le_seul_calcul_exact() -> None:
    assert ghi_exceedance.PLAFOND_CONFIANCE == "A"


@pytest.mark.parametrize(
    "module",
    [
        degre_jour_climatisation,
        energie_utile_ecs,
        poa_bifacial,
        poa_parametrable,
        pr_realiste,
        productible_correction_thermique,
        productible_pr_fourni,
        soiling_hsu,
    ],
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_plafond_b_pour_les_modeles_et_les_proxys(module: ModuleType) -> None:
    assert module.PLAFOND_CONFIANCE == "B"
