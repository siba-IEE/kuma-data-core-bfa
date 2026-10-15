"""Tests d'intégration du seed des communes Burkina Faso (migration 0004).

Vérifie les 350 départements de l'annexe II du décret n°2025-1012 et la
commune de Ouagadougou : rattachement aux provinces, codes, coordonnées
(ADR-0008) et populations RGPH 2019 rapportées aux provinces.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_POPULATION_NATIONALE_2019 = 20_505_155

_BFA_LAT_MIN, _BFA_LAT_MAX = 9.3, 15.1
_BFA_LON_MIN, _BFA_LON_MAX = -5.6, 2.5

# Nombre de communes par province : départements de l'annexe II, plus la
# commune de Ouagadougou dans le Kadiogo (6 départements + 1).
_COMMUNES_PAR_PROVINCE = {
    "bale": 10, "bam": 9, "banwa": 6, "bassitenga": 7, "bazega": 7, "bougouriba": 5,
    "boulgou": 13, "boulkiemde": 15, "comoe": 9, "djelgodji": 7, "dyamongou": 2,
    "ganzourgou": 8, "gnagna": 7, "gobnangou": 6, "gourma": 6, "houet": 13, "ioba": 8,
    "kadiogo": 7, "karo_peli": 2, "kenedougou": 13, "komondjari": 3, "kompienga": 3,
    "koosin": 10, "koulpelogo": 8, "kouritenga": 9, "kourweogo": 5, "leraba": 8,
    "loroum": 4, "mouhoun": 7, "nahouri": 5, "namentenga": 8, "nayala": 6,
    "noumbiel": 5, "oudalan": 5, "passore": 9, "poni": 10, "sandbondtenga": 11,
    "sanguie": 10, "seno": 6, "sissili": 7, "sourou": 8, "tuy": 7, "yagha": 6,
    "yatenga": 13, "ziro": 6, "zondoma": 5, "zoundweogo": 7,
}  # fmt: skip


def test_trois_cent_cinquante_et_une_communes(db_session: Session) -> None:
    """350 départements et la commune de Ouagadougou, au niveau ``commune``."""
    codes = set(
        db_session.execute(
            text("SELECT code FROM localites WHERE type_localite = 'commune'")
        ).scalars()
    )
    assert len(codes) == 351
    assert "bfa_com_ouagadougou" in codes
    assert sum(1 for c in codes if c.startswith("bfa_dep_")) == 350


def test_rattachement_aux_provinces(db_session: Session) -> None:
    """Chaque commune est enfant d'une province ; effectifs de l'annexe II."""
    lignes = db_session.execute(
        text(
            """
            SELECT p.code AS province, p.type_localite AS parent_type, count(*) AS n
            FROM localites c JOIN localites p ON p.id = c.parent_id
            WHERE c.type_localite = 'commune'
            GROUP BY p.code, p.type_localite
            """
        )
    ).all()
    assert {r.parent_type for r in lignes} == {"prefecture"}
    assert {r.province.removeprefix("bfa_prov_"): r.n for r in lignes} == _COMMUNES_PAR_PROVINCE


def test_invariants(db_session: Session) -> None:
    """ISO3, fuseau, année de population, pas de code ISO 3166-2."""
    lignes = db_session.execute(
        text(
            "SELECT code, pays_iso3, fuseau_horaire, annee_population, "
            "code_administratif_national AS cad FROM localites WHERE type_localite = 'commune'"
        )
    ).all()
    for row in lignes:
        assert row.pays_iso3 == "BFA", row.code
        assert row.fuseau_horaire == "Africa/Ouagadougou", row.code
        assert row.annee_population == 2019, row.code
        assert row.cad is None, row.code


def test_homonymes(db_session: Session) -> None:
    """Les noms portés par deux départements sont distingués par la province."""
    lignes = db_session.execute(
        text(
            """
            SELECT c.code, c.nom, p.code AS province
            FROM localites c JOIN localites p ON p.id = c.parent_id
            WHERE c.type_localite = 'commune' AND c.nom IN ('Boussouma', 'Namissiguima')
            """
        )
    ).all()
    assert {(r.code, r.province) for r in lignes} == {
        ("bfa_dep_boussouma_boulgou", "bfa_prov_boulgou"),
        ("bfa_dep_boussouma_sandbondtenga", "bfa_prov_sandbondtenga"),
        ("bfa_dep_namissiguima_sandbondtenga", "bfa_prov_sandbondtenga"),
        ("bfa_dep_namissiguima_yatenga", "bfa_prov_yatenga"),
    }


def test_coordonnees(db_session: Session) -> None:
    """Toute commune a un point dans l'enveloppe et une note sur son origine."""
    lignes = db_session.execute(
        text(
            "SELECT code, latitude, longitude, notes FROM localites WHERE type_localite = 'commune'"
        )
    ).all()
    for row in lignes:
        assert row.latitude is not None and row.longitude is not None, row.code
        assert _BFA_LAT_MIN <= float(row.latitude) <= _BFA_LAT_MAX, row.code
        assert _BFA_LON_MIN <= float(row.longitude) <= _BFA_LON_MAX, row.code
        assert re.search(
            r"Coordonnées : (P625 de l'entité\.|P625 de l'entité, deuxième statement, .+ "
            r"\(ADR-0008\)\.|P625 du chef-lieu \(Wikidata Q\d+\), .+ \(ADR-0008\)\.|"
            r"centroïde du contour COD-AB BF\d+ .+ \(ADR-0008\)\.)",
            row.notes,
        ), row.code


def test_repartition_des_coordonnees(db_session: Session) -> None:
    """Origine des points : répartition annoncée par l'ADR-0008."""
    notes = db_session.execute(
        text("SELECT notes FROM localites WHERE type_localite = 'commune'")
    ).scalars()
    origines = {"entite": 0, "deuxieme": 0, "chef_lieu": 0, "centroide": 0}
    for note in notes:
        if "Coordonnées : P625 de l'entité." in note:
            origines["entite"] += 1
        elif "deuxième statement" in note:
            origines["deuxieme"] += 1
        elif "P625 du chef-lieu" in note:
            origines["chef_lieu"] += 1
        elif "centroïde du contour COD-AB" in note:
            origines["centroide"] += 1
    assert origines == {"entite": 339, "deuxieme": 2, "chef_lieu": 8, "centroide": 2}


def test_populations(db_session: Session) -> None:
    """Somme des communes = province ; total national ; Ouagadougou et Bobo-Dioulasso."""
    lignes = db_session.execute(
        text(
            """
            SELECT p.code, p.population_estimee AS pop_province,
                   sum(c.population_estimee) AS somme_communes
            FROM localites p JOIN localites c ON c.parent_id = p.id
            WHERE p.type_localite = 'prefecture'
            GROUP BY p.code, p.population_estimee
            """
        )
    ).all()
    assert len(lignes) == 47
    for row in lignes:
        assert int(row.somme_communes) == row.pop_province, row.code
    total = db_session.execute(
        text("SELECT sum(population_estimee) FROM localites WHERE type_localite = 'commune'")
    ).scalar_one()
    assert int(total) == _POPULATION_NATIONALE_2019
    pops = dict(
        db_session.execute(
            text(
                "SELECT code, population_estimee FROM localites "
                "WHERE code IN ('bfa_com_ouagadougou', 'bfa_dep_bobo_dioulasso')"
            )
        ).all()
    )
    assert pops == {"bfa_com_ouagadougou": 2_415_266, "bfa_dep_bobo_dioulasso": 984_603}


def test_communes_estimees(db_session: Session) -> None:
    """Les 38 communes non ou partiellement dénombrées en 2019 le disent en note."""
    n = db_session.execute(
        text(
            "SELECT count(*) FROM localites WHERE type_localite = 'commune' "
            "AND notes LIKE '%dénombrée en 2019%'"
        )
    ).scalar_one()
    assert n == 38
