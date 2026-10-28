"""Tests d'intégration des textes publics du référentiel (migration 0024).

Vérifie que les fiches de sources, les descriptions de grandeurs, les notes
d'unités, les notes publiques des séries et les commentaires du schéma ne portent
plus le contexte guinéen ni le vocabulaire des chantiers du dépôt d'origine, que
la fiche ``esmap_wapp`` décrit le jeu burkinabè, et que les notes ERA5 de PVGIS
attribuent la hausse du GHI de 2021-2023 à ERA5 (ADR-0024). Vérifie aussi que les
textes des grandeurs calculées suivent la règle de propagation P (migration 0025,
ADR-0025).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Mentions de la Guinée et de ses localités, accentuées ou non, hors « Guinée-Bissau »
# et « Guinée Équatoriale » (pays de l'UEMOA et de la CEMAC cités par les unités).
_GUINEE: str = (
    "(guin[ée]e(?![- ]([Bb]issau|[ÉéEe]quatoriale))|guin[ée]en|conakry|kankan|tarambaly"
    "|kindia|mamou|lab[ée]\\M|nz[ée]r[ée]kor[ée]|\\mgin_|bcrg_)"
)
_JARGON: str = (
    "(\\mphase [0-9]|\\mvague [0-9]|\\mD-[0-9]{2}\\M|PR #|\\mCdC\\M|\\mGF-[0-9]|\\mDT-[0-9X]"
    "|β2|terrain-lite|\\mL-[A-Z]+-[0-9]|\\mLot [A-Z]\\M|cadrage|\\mQ[0-9]+\\M|villes? pilotes?"
    "|[ée]tape [0-9]|STRAT[ÉE]GIE [AB])"
)
_RACINE: Path = Path(__file__).resolve().parents[3]


def test_sources_sans_guinee_ni_jargon(db_session: Session) -> None:
    """Aucune fiche de source ne parle de la Guinée ni des chantiers d'origine."""
    codes = db_session.execute(
        text(
            "SELECT code FROM sources "
            "WHERE concat_ws(' ', titre, organisation, url, notes, metadonnees::text) ~* :g "
            "OR concat_ws(' ', notes, metadonnees::text) ~* :j ORDER BY code"
        ),
        {"g": _GUINEE, "j": _JARGON},
    ).scalars()
    assert list(codes) == []


def test_grandeurs_et_unites(db_session: Session) -> None:
    """Descriptions de grandeurs sans Guinée ni jargon ; seules les unités GNF nomment la Guinée."""
    grandeurs = db_session.execute(
        text(
            "SELECT code FROM grandeurs_referentiel "
            "WHERE concat_ws(' ', libelle, description) ~* :g OR description ~* :j"
        ),
        {"g": _GUINEE, "j": _JARGON},
    ).scalars()
    assert list(grandeurs) == []
    unites = db_session.execute(
        text(
            "SELECT code FROM unites WHERE concat_ws(' ', libelle, note_methodologique) ~* :g "
            "ORDER BY code"
        ),
        {"g": _GUINEE},
    ).scalars()
    assert list(unites) == ["gnf_par_kw", "gnf_par_kwc", "gnf_par_kwh", "gnf_par_mwh", "gnf_par_wc"]
    jargon = db_session.execute(
        text("SELECT code FROM unites WHERE note_methodologique ~* :j"), {"j": _JARGON}
    ).scalars()
    assert list(jargon) == []
    notes = dict(
        db_session.execute(
            text(
                "SELECT code, note_methodologique FROM unites "
                "WHERE code IN ('gnf_par_kwh', 'xof_par_kwh')"
            )
        ).all()
    )
    assert "franc CFA UEMOA (xof_par_kwh)" in notes["gnf_par_kwh"]
    assert "Devise de référence au Burkina Faso" in notes["xof_par_kwh"]


def test_series_sans_guinee_ni_jargon(db_session: Session) -> None:
    """Aucune note publique ni aucun libellé de série ne parle de la Guinée ou des chantiers."""
    n = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees "
            "WHERE concat_ws(' ', libelle, note_publique) ~* :g "
            "OR concat_ws(' ', libelle, note_publique) ~* :j"
        ),
        {"g": _GUINEE, "j": _JARGON},
    ).scalar_one()
    assert n == 0


def test_fiche_esmap_wapp(db_session: Session) -> None:
    """La fiche de la campagne ESMAP/WAPP décrit les quatre stations du Burkina Faso."""
    fiche = db_session.execute(
        text(
            "SELECT url, date_consultation::text AS consultation, annee_publication AS annee, "
            "notes, metadonnees -> 'stations_burkina_faso' AS stations FROM sources "
            "WHERE code = 'esmap_wapp'"
        )
    ).one()
    assert fiche.url.endswith("/burkina-faso-solar-radiation-measurement-data")
    assert fiche.annee == 2024
    assert fiche.consultation == "2026-10-28"
    assert fiche.stations == ["Dédougou", "Dori", "Kaya", "Koupéla"]
    assert "Aucune série au Burkina Faso" in fiche.notes
    assert "« World Bank / ESMAP / WAPP - Solar resource measurement campaign" in fiche.notes
    series = db_session.execute(
        text(
            "SELECT count(*) FROM series_metadonnees s JOIN sources so ON so.id = s.source_id "
            "WHERE so.code = 'esmap_wapp'"
        )
    ).scalar_one()
    assert series == 0


def test_notes_era5_de_pvgis(db_session: Session) -> None:
    """Les notes ERA5 de PVGIS et des écarts ERA5 renvoient la hausse du GHI à ERA5.

    Celles du DNI disent que la hausse du DNI n'est pas vérifiée, ERA5-Land ne servant
    pas de DNI.
    """
    lignes = db_session.execute(
        text(
            """
            SELECT code LIKE 'ecart%' AS ecart, grandeur_code LIKE '%dni%' AS dni,
                   count(*) FILTER (WHERE note_publique LIKE
                       '%vient d''ERA5 lui-même, non du traitement de PVGIS (ADR-0024).%')
                       AS corrigees,
                   count(*) FILTER (WHERE note_publique LIKE
                       '%Celle du DNI n''est pas vérifiée : ERA5-Land ne sert pas de DNI.%')
                       AS reserve_dni,
                   count(*) FILTER (WHERE note_publique LIKE '%changement probable%')
                       AS anciennes
            FROM series_metadonnees
            WHERE code LIKE 'era5\\_%\\_mensuel\\_bfa\\_%'
               OR code LIKE 'ecart\\_%\\_era5\\_nasa\\_bfa\\_%'
            GROUP BY 1, 2 ORDER BY 1, 2
            """
        )
    ).all()
    assert [(r.ecart, r.dni, r.corrigees, r.reserve_dni, r.anciennes) for r in lignes] == [
        (False, False, 398, 0, 0),
        (False, True, 398, 398, 0),
        (True, False, 398, 0, 0),
        (True, True, 398, 398, 0),
    ]


def test_commentaires_du_schema(db_session: Session) -> None:
    """Aucun commentaire de table, de colonne ou de vue ne garde la Guinée ni le jargon."""
    objets = db_session.execute(
        text(
            """
            SELECT c.relname || coalesce('.' || a.attname, '') AS objet
            FROM pg_description d
            JOIN pg_class c ON c.oid = d.objoid
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
            LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
            WHERE d.description ~* :g OR d.description ~* :j
               OR d.description ~* 'spec [0-9a-z-]+ sec\\.'
            ORDER BY 1
            """
        ),
        {"g": _GUINEE, "j": _JARGON},
    ).scalars()
    assert list(objets) == []


def test_renvois_aux_documents(db_session: Session) -> None:
    """Les documents cités par les textes publics et les commentaires existent dans le dépôt."""
    textes = db_session.execute(
        text(
            """
            SELECT d.description FROM pg_description d
            JOIN pg_class c ON c.oid = d.objoid
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
            UNION ALL SELECT notes FROM sources
            UNION ALL SELECT description FROM grandeurs_referentiel
            UNION ALL SELECT note_methodologique FROM unites
            """
        )
    ).scalars()
    renvois = {r for t in textes if t for r in re.findall(r"docs/[\w./-]+\.md", t)}
    assert renvois, "au moins un renvoi attendu"
    assert sorted(r for r in renvois if not (_RACINE / r).is_file()) == []


def test_confiance_des_grandeurs_calculees(db_session: Session) -> None:
    """Les grandeurs calculées à la volée sont au plus B, et la colonne cite la règle P."""
    descriptions = list(
        db_session.execute(
            text(
                "SELECT description FROM grandeurs_referentiel "
                "WHERE code IN ('pr_realiste', 'taux_salissure_proxy')"
            )
        ).scalars()
    )
    assert len(descriptions) == 2
    assert all("confiance au plus B" in d and "confiance B." not in d for d in descriptions)
    commentaire = db_session.execute(
        text(
            "SELECT col_description(attrelid, attnum) FROM pg_attribute "
            "WHERE attrelid = 'grandeurs_metier'::regclass AND attname = 'niveau_confiance_derive'"
        )
    ).scalar_one()
    assert "règle de propagation P" in commentaire
