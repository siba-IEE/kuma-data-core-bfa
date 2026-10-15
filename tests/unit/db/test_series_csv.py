"""Tests unitaires du format de seeds CSV gzip des séries mensuelles (ADR-0009)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from kuma_data_core.db.seeds import series_csv
from kuma_data_core.db.seeds.series_csv import ContratSerie, ecrire_series, lire_series

pytestmark = pytest.mark.unit

_CONTRAT = ContratSerie(
    source_code="nasa_power",
    source_id=1,
    source_libelle="NASA POWER",
    prefixe_code="nasa_power_ghi_mensuel",
    grandeur_code="ghi",
    methode_collecte="modele_satellitaire",
    annee_debut=2019,
    annee_fin=2020,
    borne_max=8.5,
)
_POINT = ("bfa_dep_fo", 11.11666667, -4.4)


def _mesures(valeur: float = 5.0) -> list[tuple[int, int, float]]:
    return [(a, m, valeur + m / 100) for a in (2019, 2020) for m in range(1, 13)]


@pytest.fixture(autouse=True)
def _dossier_temporaire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(series_csv, "DOSSIER_DONNEES", tmp_path)


def test_aller_retour_et_format() -> None:
    """Relecture : code, libellé, localité, mesures triées."""
    ecrire_series(_CONTRAT, "test", [(*_POINT, _mesures())])
    (serie,) = lire_series(_CONTRAT, "test")
    assert serie["code"] == "nasa_power_ghi_mensuel_bfa_dep_fo"
    assert serie["libelle"] == "GHI mensuel NASA POWER, Fô (2019-2020)"
    assert serie["mesures"] == sorted(_mesures())
    assert (serie["latitude"], serie["longitude"]) == _POINT[1:]


def test_ecriture_deterministe() -> None:
    """Mêmes données, ordre d'entrée différent : mêmes octets."""
    cible = ecrire_series(_CONTRAT, "test", [(*_POINT, _mesures())])
    premier = cible.read_bytes()
    ecrire_series(_CONTRAT, "test", [(*_POINT, list(reversed(_mesures())))])
    assert cible.read_bytes() == premier


@pytest.mark.parametrize(
    ("mesures", "message"),
    [
        (_mesures()[:-1], "mois"),  # incomplet
        ([*_mesures()[:-1], (2020, 12, 9.9)], "bornes"),  # hors bornes
        ([*_mesures()[:-1], (2020, 12, 0.0)], "bornes"),  # valeur nulle
        ([*_mesures()[:-1], (2021, 1, 5.0)], "période"),  # hors période
    ],
)
def test_rejets_a_l_ecriture(mesures: list[tuple[int, int, float]], message: str) -> None:
    """Un fichier invalide n'est jamais écrit ni ne remplace le fichier existant."""
    cible = ecrire_series(_CONTRAT, "test", [(*_POINT, _mesures())])
    valide = cible.read_bytes()
    with pytest.raises(ValueError, match=message):
        ecrire_series(_CONTRAT, "test", [(*_POINT, mesures)])
    assert cible.read_bytes() == valide
    assert list(series_csv.DOSSIER_DONNEES.iterdir()) == [cible]


def test_rejet_doublon_et_localite_inconnue(tmp_path: Path) -> None:
    """Doublons, coordonnées incohérentes et localités inconnues sont refusés."""
    lignes = ["localite_code,latitude,longitude,annee,mois,valeur"]
    lignes += [f"bfa_dep_fo,11.1,-4.4,{a},{m},5.0" for a, m, _ in _mesures()]
    chemin = tmp_path / _CONTRAT.nom_fichier("test")
    chemin.write_bytes(gzip.compress(("\n".join([*lignes, lignes[1]]) + "\n").encode()))
    with pytest.raises(ValueError, match="doublon"):
        lire_series(_CONTRAT, "test")
    deplacee = [*lignes[:-1], lignes[-1].replace("11.1,", "11.2,")]
    chemin.write_bytes(gzip.compress(("\n".join(deplacee) + "\n").encode()))
    with pytest.raises(ValueError, match="coordonnées"):
        lire_series(_CONTRAT, "test")
    inconnue = [lignes[0]]
    inconnue += [ligne.replace("bfa_dep_fo", "bfa_dep_inconnu") for ligne in lignes[1:]]
    chemin.write_bytes(gzip.compress(("\n".join(inconnue) + "\n").encode()))
    with pytest.raises(ValueError, match="inconnue"):
        lire_series(_CONTRAT, "test")
