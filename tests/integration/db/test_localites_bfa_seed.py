"""Tests d'intégration du référentiel de localités Burkina Faso (migration 0003).

Vérifie le pays, les 17 régions et les 47 provinces du découpage de 2025, leur
hiérarchie, leurs coordonnées (ADR-0008), leurs populations RGPH 2019 et les
provinces renommées, créées ou réduites. Le décompte par niveau et le contrôle
de co-localisation portent sur toutes les localités, communes comprises
(migration 0004).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Total national officiel du 5e RGPH (INSD, résultats définitifs, juin 2022).
_POPULATION_NATIONALE_2019 = 20_505_155

# Enveloppe géographique du Burkina Faso (bornes larges).
_BFA_LAT_MIN, _BFA_LAT_MAX = 9.3, 15.1
_BFA_LON_MIN, _BFA_LON_MAX = -5.6, 2.5

# Composition 2025 des régions (annexe II du décret n°2025-1012).
_COMPOSITION = {
    "bfa_bankui": {"bale", "banwa", "mouhoun"},
    "bfa_djoro": {"bougouriba", "ioba", "noumbiel", "poni"},
    "bfa_goulmou": {"gourma", "kompienga"},
    "bfa_guiriko": {"houet", "kenedougou", "tuy"},
    "bfa_kadiogo": {"kadiogo"},
    "bfa_koulse": {"bam", "namentenga", "sandbondtenga"},
    "bfa_liptako": {"oudalan", "seno", "yagha"},
    "bfa_nakambe": {"boulgou", "koulpelogo", "kouritenga"},
    "bfa_nando": {"boulkiemde", "sanguie", "sissili", "ziro"},
    "bfa_nazinon": {"bazega", "nahouri", "zoundweogo"},
    "bfa_oubri": {"bassitenga", "ganzourgou", "kourweogo"},
    "bfa_sirba": {"gnagna", "komondjari"},
    "bfa_soum": {"djelgodji", "karo_peli"},
    "bfa_sourou": {"koosin", "nayala", "sourou"},
    "bfa_tannounyan": {"comoe", "leraba"},
    "bfa_tapoa": {"dyamongou", "gobnangou"},
    "bfa_yaadga": {"loroum", "passore", "yatenga", "zondoma"},
}

# Provinces sans code ISO 3166-2 : créées (Dyamongou, Karo-Peli) ou réduites
# en 2025 (Djelgodji, Gobnangou).
_PROVINCES_SANS_CODE_ISO = {
    "bfa_prov_djelgodji",
    "bfa_prov_dyamongou",
    "bfa_prov_gobnangou",
    "bfa_prov_karo_peli",
}

# Localités dont la coordonnée est celle du chef-lieu (ADR-0008).
_REPLI_CHEF_LIEU = {
    "bfa_bankui",
    "bfa_goulmou",
    "bfa_liptako",
    "bfa_sirba",
    "bfa_soum",
    "bfa_sourou",
    "bfa_prov_djelgodji",
    "bfa_prov_dyamongou",
    "bfa_prov_gobnangou",
    "bfa_prov_gourma",
    "bfa_prov_karo_peli",
    "bfa_prov_nayala",
}


def test_nombre_total_localites(db_session: Session) -> None:
    """1 continent, 1 pays, 17 régions, 47 provinces et 351 communes."""
    lignes = db_session.execute(
        text("SELECT type_localite, count(*) AS n FROM localites GROUP BY type_localite")
    ).all()
    assert {r.type_localite: r.n for r in lignes} == {
        "continent": 1,
        "pays": 1,
        "region_administrative": 17,
        "prefecture": 47,
        "commune": 351,
    }


def test_pays_burkina_faso(db_session: Session) -> None:
    """Le pays ``bfa`` est enfant de l'Afrique et porte la population RGPH 2019."""
    pays = db_session.execute(
        text(
            """
            SELECT l.nom, l.pays_iso3, l.fuseau_horaire, l.population_estimee,
                   l.annee_population, p.code AS parent
            FROM localites l JOIN localites p ON p.id = l.parent_id
            WHERE l.code = 'bfa'
            """
        )
    ).one()
    assert pays.nom == "Burkina Faso"
    assert pays.pays_iso3 == "BFA"
    assert pays.fuseau_horaire == "Africa/Ouagadougou"
    assert pays.parent == "afrique"
    assert pays.population_estimee == _POPULATION_NATIONALE_2019
    assert pays.annee_population == 2019


def test_hierarchie_et_invariants(db_session: Session) -> None:
    """Régions sous ``bfa``, provinces sous une région ; ISO3, fuseau et codes."""
    lignes = db_session.execute(
        text(
            """
            SELECT l.code, l.type_localite, l.pays_iso3, l.fuseau_horaire,
                   p.code AS parent, p.type_localite AS parent_type
            FROM localites l JOIN localites p ON p.id = l.parent_id
            WHERE l.type_localite IN ('region_administrative', 'prefecture')
            """
        )
    ).all()
    assert len(lignes) == 64
    for row in lignes:
        assert row.pays_iso3 == "BFA", row.code
        assert row.fuseau_horaire == "Africa/Ouagadougou", row.code
        if row.type_localite == "region_administrative":
            assert row.parent == "bfa", row.code
            assert row.code.startswith("bfa_") and not row.code.startswith("bfa_prov_"), row.code
        else:
            assert row.parent_type == "region_administrative", row.code
            assert row.code.startswith("bfa_prov_"), row.code


def test_composition_des_regions(db_session: Session) -> None:
    """Chaque région porte exactement les provinces de l'annexe II du décret 2025-1012."""
    lignes = db_session.execute(
        text(
            """
            SELECT p.code AS region, l.code AS province
            FROM localites l JOIN localites p ON p.id = l.parent_id
            WHERE l.type_localite = 'prefecture'
            """
        )
    ).all()
    composition: dict[str, set[str]] = {}
    for row in lignes:
        composition.setdefault(row.region, set()).add(row.province.removeprefix("bfa_prov_"))
    assert composition == _COMPOSITION


def test_coordonnees_dans_enveloppe(db_session: Session) -> None:
    """Pays, régions et provinces ont une coordonnée dans l'enveloppe du Burkina."""
    lignes = db_session.execute(
        text(
            "SELECT code, latitude, longitude FROM localites "
            "WHERE type_localite IN ('pays', 'region_administrative', 'prefecture')"
        )
    ).all()
    assert len(lignes) == 65
    for row in lignes:
        assert row.latitude is not None and row.longitude is not None, row.code
        assert _BFA_LAT_MIN <= float(row.latitude) <= _BFA_LAT_MAX, row.code
        assert _BFA_LON_MIN <= float(row.longitude) <= _BFA_LON_MAX, row.code


def test_replis_sur_chef_lieu_documentes(db_session: Session) -> None:
    """Les coordonnées prises au chef-lieu sont celles attendues, avec QID et motif."""
    lignes = db_session.execute(
        text(
            "SELECT code, notes FROM localites "
            "WHERE type_localite IN ('region_administrative', 'prefecture') "
            "AND notes LIKE '%P625 du chef-lieu%'"
        )
    ).all()
    assert {r.code for r in lignes} == _REPLI_CHEF_LIEU
    for row in lignes:
        assert re.search(r"P625 du chef-lieu \(Wikidata Q\d+\), .+ \(ADR-0008\)\.", row.notes), (
            row.code
        )


def test_pas_de_colocalisation_au_meme_niveau(db_session: Session) -> None:
    """Deux localités de même niveau ne partagent pas un point (ADR-0008)."""
    doublons = db_session.execute(
        text(
            """
            SELECT type_localite, latitude, longitude, array_agg(code) AS codes
            FROM localites
            WHERE latitude IS NOT NULL
            GROUP BY type_localite, latitude, longitude
            HAVING count(*) > 1
            """
        )
    ).all()
    assert doublons == []


def test_populations_coherentes(db_session: Session) -> None:
    """Somme des provinces = région ; somme des régions = total national RGPH 2019."""
    lignes = db_session.execute(
        text(
            """
            SELECT r.code, r.population_estimee AS pop_region,
                   sum(p.population_estimee) AS somme_provinces
            FROM localites r JOIN localites p ON p.parent_id = r.id
            WHERE r.type_localite = 'region_administrative'
            GROUP BY r.code, r.population_estimee
            """
        )
    ).all()
    assert len(lignes) == 17
    for row in lignes:
        assert int(row.somme_provinces) == row.pop_region, row.code
    total = db_session.execute(
        text(
            "SELECT sum(population_estimee) FROM localites "
            "WHERE type_localite = 'region_administrative'"
        )
    ).scalar_one()
    assert int(total) == _POPULATION_NATIONALE_2019
    annees = db_session.execute(
        text(
            "SELECT DISTINCT annee_population FROM localites "
            "WHERE type_localite IN ('pays', 'region_administrative', 'prefecture')"
        )
    ).scalars()
    assert set(annees) == {2019}


def test_codes_iso_des_provinces(db_session: Session) -> None:
    """43 provinces portent leur sous-code ISO 3166-2:BF ; les régions et les autres non."""
    lignes = db_session.execute(
        text(
            "SELECT code, type_localite, code_administratif_national AS cad FROM localites "
            "WHERE type_localite IN ('region_administrative', 'prefecture')"
        )
    ).all()
    for row in lignes:
        if row.type_localite == "region_administrative" or row.code in _PROVINCES_SANS_CODE_ISO:
            assert row.cad is None, row.code
        else:
            assert row.cad is not None and len(row.cad) == 3 and row.cad.isupper(), row.code
    assert sum(1 for r in lignes if r.cad is not None) == 43
    kadiogo = db_session.execute(
        text("SELECT code_administratif_national FROM localites WHERE code = 'bfa_prov_kadiogo'")
    ).scalar_one()
    assert kadiogo == "KAD"


def test_code_iso_concorde_avec_la_note(db_session: Session) -> None:
    """Le code porté en colonne est celui que cite la note."""
    lignes = db_session.execute(
        text(
            "SELECT code, code_administratif_national AS cad, notes FROM localites "
            "WHERE code_administratif_national IS NOT NULL"
        )
    ).all()
    assert len(lignes) == 43
    for row in lignes:
        assert f"ISO 3166-2 BF-{row.cad}." in row.notes, row.code


def test_reforme_provinces_renommees(db_session: Session) -> None:
    """Les cinq provinces renommées portent leur nouveau nom ; l'ancien n'est pas un code."""
    attendus = {
        "bfa_prov_koosin": ("Koosin", "Kossi"),
        "bfa_prov_bassitenga": ("Bassitenga", "Oubritenga"),
        "bfa_prov_sandbondtenga": ("Sandbondtenga", "Sanmatenga"),
        "bfa_prov_djelgodji": ("Djelgodji", "Soum"),
        "bfa_prov_gobnangou": ("Gobnangou", "Tapoa"),
    }
    for code, (nom, ancien) in attendus.items():
        row = db_session.execute(
            text("SELECT nom, notes FROM localites WHERE code = :c"), {"c": code}
        ).one()
        assert row.nom == nom, code
        assert f"Ex-province {ancien}" in row.notes, code
    anciens = db_session.execute(
        text(
            "SELECT count(*) FROM localites WHERE code IN "
            "('bfa_prov_kossi', 'bfa_prov_oubritenga', 'bfa_prov_sanmatenga', "
            "'bfa_prov_soum', 'bfa_prov_tapoa')"
        )
    ).scalar_one()
    assert anciens == 0


def test_reforme_provinces_creees_et_reduites(db_session: Session) -> None:
    """Dyamongou et Karo-Peli sont créées ; Gobnangou et Djelgodji réduits d'autant."""
    pops = {
        r.code: r.population_estimee
        for r in db_session.execute(
            text(
                "SELECT code, population_estimee FROM localites WHERE code IN "
                "('bfa_prov_dyamongou', 'bfa_prov_gobnangou', 'bfa_prov_karo_peli', "
                "'bfa_prov_djelgodji', 'bfa_tapoa', 'bfa_soum')"
            )
        ).all()
    }
    # Botou + Kantchari ; Arbinda + Koutougou (INSD, tableau 60).
    assert pops["bfa_prov_dyamongou"] == 190_628
    assert pops["bfa_prov_karo_peli"] == 125_160
    # Les régions Tapoa et Soum reprennent l'emprise des ex-provinces Tapoa et Soum.
    assert pops["bfa_tapoa"] == 605_733
    assert pops["bfa_soum"] == 363_661
    assert pops["bfa_prov_gobnangou"] == pops["bfa_tapoa"] - pops["bfa_prov_dyamongou"]
    assert pops["bfa_prov_djelgodji"] == pops["bfa_soum"] - pops["bfa_prov_karo_peli"]


def test_graphie_koulse(db_session: Session) -> None:
    """La région de Kaya suit la graphie des décrets ; la variante est en note."""
    row = db_session.execute(
        text("SELECT nom, notes FROM localites WHERE code = 'bfa_koulse'")
    ).one()
    assert row.nom == "Koulsé"
    assert "Kuilsé" in row.notes
