"""Tests unitaires du format Parquet des séries journalières denses (ADR-0017)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from kuma_data_core.db.seeds import series_denses
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    CLE_ECARTEES,
    CLE_LOCALITES,
    _lignes_annuelles,
    dans_les_bornes,
    ecrire_series_denses,
    lire_series_denses,
)

pytestmark = pytest.mark.unit

_GHI = ContratSerie(
    source_code="nasa_power",
    source_id=1,
    source_libelle="NASA POWER",
    prefixe_code="nasa_power_ghi_journalier",
    grandeur_code="ghi",
    methode_collecte="modele_satellitaire",
    fiabilite_source="haute",
    annee_debut=2019,
    annee_fin=2020,
    borne_max=9.0,
    granularite="journalier",
)
_PLUIE = ContratSerie(
    source_code="nasa_power",
    source_id=1,
    source_libelle="NASA POWER",
    prefixe_code="nasa_power_precipitation_journalier",
    grandeur_code="precipitation",
    methode_collecte="reanalyse",
    fiabilite_source="haute",
    annee_debut=2020,
    annee_fin=2020,
    borne_max=500.0,
    granularite="journalier",
    borne_min=0.0,
    ecarts_admis=frozenset({("bfa_dep_tiefora", "2020-12-02"), ("bfa_dep_fo", "2020-12-02")}),
)
_SOURCE = {"service": "POWER Daily API", "version": "v2.10.1", "consultation": "2026-10-27"}
_POINTS = {
    "bfa_dep_banfora": (10.633, -4.75),
    "bfa_dep_fo": (11.117, -4.4),
    "bfa_dep_tiefora": (10.633, -4.55),
}

Mesures = list[tuple[date, float | None]]


def _jours(contrat: ContratSerie, decalage: float = 0.0) -> Mesures:
    debut = date(contrat.annee_debut, 1, 1)
    return [
        (debut + timedelta(days=i), round(5.0 + i % 7 / 10 + decalage, 4))
        for i in range(contrat.nb_jours)
    ]


def _series(*entrees: tuple[str, Mesures]) -> list[tuple[str, float, float, Mesures]]:
    return [(code, *_POINTS[code], mesures) for code, mesures in entrees]


@pytest.fixture(autouse=True)
def _dossier_temporaire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(series_denses, "DOSSIER_DENSES", tmp_path)


def test_aller_retour_et_deduplication() -> None:
    """Deux localités de même série : une seule série écrite, relue pour les deux."""
    cible = ecrire_series_denses(
        _GHI,
        "test",
        _series(
            ("bfa_dep_tiefora", _jours(_GHI)),
            ("bfa_dep_banfora", _jours(_GHI)),
            ("bfa_dep_fo", _jours(_GHI, 0.5)),
        ),
        _SOURCE,
    )
    assert cible.name == "nasa_power_ghi_journalier_test.parquet"
    assert pq.read_table(cible).num_rows == 2 * 731
    denses = lire_series_denses(_GHI, "test")
    assert denses.codes == ["bfa_dep_banfora", "bfa_dep_fo", "bfa_dep_tiefora"]
    assert denses.representantes == {
        "bfa_dep_banfora": "bfa_dep_banfora",
        "bfa_dep_fo": "bfa_dep_fo",
        "bfa_dep_tiefora": "bfa_dep_banfora",
    }
    assert denses.points == _POINTS
    assert denses.source == _SOURCE
    assert denses.ecartees == []
    assert denses.debut == date(2019, 1, 1)
    attendu = [v for _, v in _jours(_GHI)]
    assert denses.valeurs_de("bfa_dep_tiefora").tolist() == attendu
    assert denses.valeurs_de("bfa_dep_fo").tolist() == [v + 0.5 for v in attendu]  # type: ignore[operator]
    assert denses.nb_mesures == 3 * 731
    assert denses.jours_absents("bfa_dep_fo") == []


def test_valeurs_exactes_a_quatre_decimales() -> None:
    """Le stockage en dix-millièmes entiers rend la valeur arrondie à 4 décimales."""
    jours: Mesures = [
        (j, (1.23456789 + i / 3) % 8.0 + 0.5) for i, (j, _) in enumerate(_jours(_GHI))
    ]
    ecrire_series_denses(_GHI, "test", _series(("bfa_dep_fo", jours)), _SOURCE)
    relues = lire_series_denses(_GHI, "test").valeurs_de("bfa_dep_fo")
    assert relues.tolist() == [round(v, 4) for _, v in jours if v is not None]


def test_ecriture_deterministe() -> None:
    """Mêmes données, ordre d'entrée différent : mêmes octets."""
    series = _series(("bfa_dep_fo", _jours(_GHI)), ("bfa_dep_banfora", _jours(_GHI, 1.0)))
    cible = ecrire_series_denses(_GHI, "test", series, _SOURCE)
    premier = cible.read_bytes()
    inverse = [(c, la, lo, list(reversed(m))) for c, la, lo, m in reversed(series)]
    ecrire_series_denses(_GHI, "test", inverse, _SOURCE)
    assert cible.read_bytes() == premier


def test_valeurs_absentes_et_ecartees() -> None:
    """``None`` : jour non servi ; valeur hors bornes admise : écartée, tracée avec sa valeur."""
    jours: Mesures = [(j, 0.0) for j, _ in _jours(_PLUIE)]
    jours[336] = (jours[336][0], 514.64)  # 2020-12-02
    jours[10] = (jours[10][0], None)
    ecrire_series_denses(
        _PLUIE, "test", _series(("bfa_dep_tiefora", jours), ("bfa_dep_fo", jours)), _SOURCE
    )
    denses = lire_series_denses(_PLUIE, "test")
    assert len(denses.valeurs) == 1
    assert denses.jours_absents("bfa_dep_fo") == [date(2020, 1, 11), date(2020, 12, 2)]
    assert denses.ecartees == [
        ("bfa_dep_fo", date(2020, 12, 2), 514.64),
        ("bfa_dep_tiefora", date(2020, 12, 2), 514.64),
    ]
    assert denses.ecartees_de("bfa_dep_tiefora") == [(date(2020, 12, 2), 514.64)]
    assert denses.nb_mesures == 2 * 364
    assert np.isnan(denses.valeurs_de("bfa_dep_tiefora")[336])


def test_ecart_non_admis_ou_admis_sans_objet() -> None:
    """Valeur hors bornes non listée : écriture arrêtée ; un écart admis doit avoir lieu."""
    jours: Mesures = [(j, 0.0) for j, _ in _jours(_PLUIE)]
    jours[300] = (jours[300][0], 600.0)
    with pytest.raises(ValueError, match="écart non admis"):
        ecrire_series_denses(_PLUIE, "test", _series(("bfa_dep_fo", jours)), _SOURCE)
    sains: Mesures = [(j, 0.0) for j, _ in _jours(_PLUIE)]
    with pytest.raises(ValueError, match="valeurs écartées"):
        ecrire_series_denses(_PLUIE, "test", _series(("bfa_dep_fo", sains)), _SOURCE)


@pytest.mark.parametrize(
    ("series", "message"),
    [
        ([("bfa_dep_inconnue", 1.0, 1.0, _jours(_GHI))], "localités inconnues"),
        (_series(("bfa_dep_fo", _jours(_GHI)), ("bfa_dep_fo", _jours(_GHI))), "en double"),
        (_series(("bfa_dep_fo", _jours(_GHI)[:-1])), "jours manquants"),
        (_series(("bfa_dep_fo", [*_jours(_GHI)[:-1], _jours(_GHI)[0]])), "jours manquants"),
        (_series(("bfa_dep_fo", [(date(2019, 1, 1), 9.5), *_jours(_GHI)[1:]])), "hors bornes"),
        (_series(("bfa_dep_fo", [(date(2019, 1, 1), 0.0), *_jours(_GHI)[1:]])), "hors bornes"),
        (
            _series(("bfa_dep_fo", [(date(2019, 1, 1), float("nan")), *_jours(_GHI)[1:]])),
            "hors bornes",
        ),
        (_series(("bfa_dep_fo", [(j, None) for j, _ in _jours(_GHI)])), "sans aucune valeur"),
    ],
)
def test_rejets_a_l_ecriture(
    series: list[tuple[str, float, float, Mesures]], message: str, tmp_path: Path
) -> None:
    """Contrat violé : rien n'est écrit."""
    with pytest.raises(ValueError, match=message):
        ecrire_series_denses(_GHI, "test", series, _SOURCE)
    assert list(tmp_path.iterdir()) == []


def test_source_incomplete_refusee(tmp_path: Path) -> None:
    """Service, version et date de consultation sont exigés."""
    with pytest.raises(ValueError, match="source"):
        ecrire_series_denses(
            _GHI, "test", _series(("bfa_dep_fo", _jours(_GHI))), {"service": "POWER"}
        )
    assert list(tmp_path.iterdir()) == []


def _ecrire_fo_tiefora() -> tuple[Path, pa.Table]:
    cible = ecrire_series_denses(
        _GHI,
        "test",
        _series(("bfa_dep_fo", _jours(_GHI)), ("bfa_dep_tiefora", _jours(_GHI, 1.0))),
        _SOURCE,
    )
    return cible, pq.read_table(cible)


def test_rejet_de_metadonnees_incoherentes() -> None:
    """Représentantes mal associées, métadonnée absente ou mal formée : fichier refusé."""
    cible, table = _ecrire_fo_tiefora()
    meta = dict(table.schema.metadata)
    for cle, faux in (
        (CLE_LOCALITES, {"bfa_dep_fo": "bfa_dep_fo", "bfa_dep_tiefora": "bfa_dep_banfora"}),
        (CLE_LOCALITES, {"bfa_dep_fo": "bfa_dep_fo"}),
        (CLE_LOCALITES, ["bfa_dep_fo"]),
        (CLE_ECARTEES, [["bfa_dep_fo", "2019-03-01", 9.5]]),
    ):
        modifiee = meta | {cle: json.dumps(faux).encode()}
        pq.write_table(table.replace_schema_metadata(modifiee), cible)
        with pytest.raises(ValueError):
            lire_series_denses(_GHI, "test")
    sans_points = {k: v for k, v in meta.items() if k != b"kuma.points"}
    pq.write_table(table.replace_schema_metadata(sans_points), cible)
    with pytest.raises(ValueError, match=r"kuma\.points"):
        lire_series_denses(_GHI, "test")


def test_rejet_d_un_type_de_colonne_altere() -> None:
    """Une colonne de valeurs qui n'est plus en entiers 32 bits est refusée."""
    cible, table = _ecrire_fo_tiefora()
    flottante = table.set_column(
        2, "valeur_e4", table.column("valeur_e4").cast(pa.float64())
    ).replace_schema_metadata(table.schema.metadata)
    pq.write_table(flottante, cible)
    with pytest.raises(ValueError, match="schéma"):
        lire_series_denses(_GHI, "test")


def test_rejet_de_deux_series_identiques() -> None:
    """Deux représentantes de même série violent la déduplication."""
    cible = ecrire_series_denses(_GHI, "test", _series(("bfa_dep_fo", _jours(_GHI))), _SOURCE)
    table = pq.read_table(cible)
    double = pa.concat_tables(
        [
            table,
            table.set_column(
                0,
                "localite_code",
                pa.array(["bfa_dep_tiefora"] * table.num_rows)
                .dictionary_encode()
                .cast(table.schema.field("localite_code").type),
            ),
        ]
    )
    meta = dict(table.schema.metadata) | {
        CLE_LOCALITES: b'{"bfa_dep_fo":"bfa_dep_fo","bfa_dep_tiefora":"bfa_dep_tiefora"}',
        b"kuma.points": json.dumps(
            {c: list(p) for c, p in _POINTS.items() if c != "bfa_dep_banfora"}
        ).encode(),
    }
    pq.write_table(double.replace_schema_metadata(meta), cible)
    with pytest.raises(ValueError, match="séries identiques"):
        lire_series_denses(_GHI, "test")


def test_lignes_annuelles() -> None:
    """Une ligne par année, 365 ou 366 dix-millièmes, ``None`` pour un jour absent."""
    valeurs = np.array([round(1.0 + i / 10_000, 4) for i in range(731)])
    valeurs[400] = np.nan
    lignes = _lignes_annuelles(7, "B", date(2019, 1, 1), valeurs)
    assert [(s, a, n, len(v)) for s, a, n, v in lignes] == [
        (7, 2019, "B", 365),
        (7, 2020, "B", 366),
    ]
    assert lignes[0][3][:3] == [10_000, 10_001, 10_002]
    assert lignes[1][3][35] is None and lignes[1][3][36] == 10_401


def test_dans_les_bornes() -> None:
    """Borne basse incluse si le contrat en fixe une, sinon valeur strictement positive."""
    assert dans_les_bornes(_PLUIE, 0.0)
    assert dans_les_bornes(_PLUIE, 500.0)
    assert not dans_les_bornes(_PLUIE, 514.64)
    assert not dans_les_bornes(_GHI, 0.0)
    assert not dans_les_bornes(_GHI, float("nan"))
    assert not dans_les_bornes(replace(_GHI, borne_max=1.0), 1.5)
