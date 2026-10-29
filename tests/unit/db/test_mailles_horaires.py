"""Tests unitaires des mailles des séries horaires NASA POWER (ADR-0026)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_data_core.db.seeds import mailles_horaires
from kuma_data_core.db.seeds.mailles_horaires import (
    MailleLocalite,
    ecrire_mailles,
    lire_mailles,
    porteuses_par_maille,
)

pytestmark = pytest.mark.unit

_FO = "bfa_dep_fo"
_OUAGA = "bfa_com_ouagadougou"
_KADIOGO = "bfa_prov_kadiogo"


@pytest.fixture(autouse=True)
def _fichier_temporaire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mailles_horaires, "FICHIER_MAILLES", tmp_path / "mailles.csv")


def test_porteuse_premiere_localite_ou_pilote() -> None:
    """La porteuse d'une maille est son pilote s'il y en a un, sinon sa première localité."""
    valeurs = {_KADIOGO: b"a", _OUAGA: b"a", _FO: b"b", "bfa_dep_dori": b"b"}

    assert porteuses_par_maille(valeurs) == {
        _KADIOGO: _OUAGA,
        _OUAGA: _OUAGA,
        "bfa_dep_dori": "bfa_dep_dori",
        _FO: "bfa_dep_dori",
    }
    assert porteuses_par_maille(valeurs, prioritaires=(_FO,))[_FO] == _FO
    assert porteuses_par_maille(valeurs, prioritaires=(_FO,))["bfa_dep_dori"] == _FO


def test_ecriture_relue() -> None:
    rayonnement = {_FO: _FO, _OUAGA: _OUAGA, _KADIOGO: _OUAGA}
    temperature = {_FO: _FO, _OUAGA: _FO, _KADIOGO: _KADIOGO}

    ecrire_mailles(rayonnement, temperature)

    mailles = lire_mailles()
    assert mailles == [
        MailleLocalite(_OUAGA, _OUAGA, _FO),
        MailleLocalite(_FO, _FO, _FO),
        MailleLocalite(_KADIOGO, _OUAGA, _KADIOGO),
    ]
    assert mailles[2].porteuse("dni") == _OUAGA
    assert mailles[2].porteuse("t2m") == _KADIOGO
    with pytest.raises(ValueError, match="sans maille"):
        mailles[2].porteuse("ghi_ciel_clair")


def test_porteuse_qui_lit_une_autre_refusee() -> None:
    """Un seul niveau : une localité ne lit qu'une porteuse qui porte elle-même sa série."""
    with pytest.raises(ValueError, match="ne porte pas"):
        ecrire_mailles(
            {_FO: _OUAGA, _OUAGA: _KADIOGO, _KADIOGO: _KADIOGO},
            dict.fromkeys((_FO, _OUAGA, _KADIOGO), _FO),
        )
    assert not mailles_horaires.FICHIER_MAILLES.exists()


def test_localites_differentes_refusees() -> None:
    with pytest.raises(ValueError, match="localités différentes"):
        ecrire_mailles({_FO: _FO}, {_OUAGA: _OUAGA})
