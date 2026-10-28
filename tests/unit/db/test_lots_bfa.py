"""Tests unitaires des contrats de séries du Burkina Faso."""

from __future__ import annotations

import pytest

from kuma_data_core.db.seeds import lots_bfa
from kuma_data_core.db.seeds.series_csv import ContratSerie

pytestmark = pytest.mark.unit


def contrats_bfa() -> list[ContratSerie]:
    """Tous les contrats du module, qu'ils soient isolés ou regroupés par grandeur."""
    contrats: list[ContratSerie] = []
    for valeur in vars(lots_bfa).values():
        if isinstance(valeur, ContratSerie):
            contrats.append(valeur)
        elif isinstance(valeur, dict | tuple):
            elements = valeur.values() if isinstance(valeur, dict) else valeur
            contrats += [c for c in elements if isinstance(c, ContratSerie)]
    # Un même contrat peut figurer dans plusieurs collections
    return list({id(c): c for c in contrats}.values())


def test_contrats_en_confiance_b() -> None:
    """Sources satellitaires et réanalyses de fiabilité haute : toutes les séries en B (R4)."""
    contrats = contrats_bfa()
    assert len(contrats) > 40
    assert {c.fiabilite_source for c in contrats} == {"haute"}
    assert {c.methode_collecte for c in contrats} == {"modele_satellitaire", "reanalyse"}
    assert {c.niveau_confiance for c in contrats} == {"B"}
