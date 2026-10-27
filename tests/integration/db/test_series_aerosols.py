"""Tests d'intégration de l'épaisseur optique des aérosols CAMS EAC4 (migration 0018).

Vérifie les trois grandeurs du référentiel, les 1 194 séries denses des
398 localités (ADR-0019), leurs valeurs et leur cohérence entre elles et
d'une localité à l'autre.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : borne haute.
_GRANDEURS = {"aod550": 5.0, "aod550_poussiere": 5.0, "aod550_organique": 2.0}


def test_grandeurs_du_referentiel(db_session: Session) -> None:
    """Trois grandeurs stockées, sans unité."""
    lignes = db_session.execute(
        text(
            """
            SELECT g.code, u.code AS unite, g.famille, g.strategie_calcul
            FROM grandeurs_referentiel g JOIN unites u ON u.id = g.unite_id
            WHERE g.code LIKE 'aod550%'
            """
        )
    ).all()
    assert {r.code for r in lignes} == set(_GRANDEURS)
    assert all(
        (r.unite, r.famille, r.strategie_calcul) == ("sans_unite", "F1", "stockee") for r in lignes
    )


def test_series_des_398_localites(db_session: Session) -> None:
    """398 séries par grandeur (47 provinces, 351 communes), denses, 51 porteuses."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, so.code AS source,
                   count(*) FILTER (WHERE l.type_localite = 'prefecture') AS provinces,
                   count(*) FILTER (WHERE l.type_localite = 'commune') AS communes,
                   count(*) FILTER (WHERE s.serie_porteuse_id IS NULL) AS porteuses,
                   bool_and(s.stockage = 'dense') AS denses
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code LIKE 'aod550%'
            GROUP BY 1, 2, 3, 4, 5
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_GRANDEURS)
    for r in lignes:
        assert (r.debut, r.fin, r.methode_collecte, r.source) == (
            "2005-01-01",
            "2025-12-31",
            "reanalyse",
            "cams_eac4",
        )
        assert (r.provinces, r.communes, r.porteuses, r.denses) == (47, 351, 51, True)


def test_valeurs_completes_et_bornees(db_session: Session) -> None:
    """7 670 jours par porteuse, bornes tenues, poussières et matière organique sous le total."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, count(*) AS porteuses, min(n) AS n_min, max(n) AS n_max,
                   min(vmin) AS vmin, max(vmax) AS vmax
            FROM series_metadonnees s
            JOIN LATERAL (
                SELECT count(u.e4) AS n, min(u.e4) / 10000.0 AS vmin, max(u.e4) / 10000.0 AS vmax
                FROM mesures_journalieres_denses d CROSS JOIN LATERAL unnest(d.valeurs_e4) AS u(e4)
                WHERE d.serie_id = s.id
            ) v ON TRUE
            WHERE s.grandeur_code LIKE 'aod550%' AND s.serie_porteuse_id IS NULL
            GROUP BY 1
            """
        )
    ).all()
    for r in lignes:
        assert (r.porteuses, r.n_min, r.n_max) == (51, 7_670, 7_670), r.grandeur_code
        assert r.vmin >= 0.0 and r.vmax <= _GRANDEURS[r.grandeur_code], r.grandeur_code
    depassements = db_session.execute(
        text(
            """
            WITH annees AS (
                SELECT s.localite_id, s.grandeur_code, d.annee, d.valeurs_e4
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d ON d.serie_id = s.id
                WHERE s.grandeur_code LIKE 'aod550%' AND s.serie_porteuse_id IS NULL
            )
            SELECT count(*) AS jours, count(*) FILTER (WHERE u.p + u.o > u.t + 1) AS depassements
            FROM annees t
            JOIN annees p ON (p.localite_id, p.annee) = (t.localite_id, t.annee)
                         AND p.grandeur_code = 'aod550_poussiere'
            JOIN annees o ON (o.localite_id, o.annee) = (t.localite_id, t.annee)
                         AND o.grandeur_code = 'aod550_organique'
            CROSS JOIN LATERAL unnest(t.valeurs_e4, p.valeurs_e4, o.valeurs_e4) AS u(t, p, o)
            WHERE t.grandeur_code = 'aod550'
            """
        )
    ).one()
    assert (depassements.jours, depassements.depassements) == (51 * 7_670, 0)


def test_saisons_et_gradient(db_session: Session) -> None:
    """Poussières au nord, matière organique au sud ; AOD totale plus forte au printemps."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code,
                   avg(u.e4) FILTER (WHERE l.latitude > 13.5) / 10000.0 AS nord,
                   avg(u.e4) FILTER (WHERE l.latitude < 11) / 10000.0 AS sud,
                   avg(u.e4) FILTER (
                       WHERE extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int) = 3
                   ) / 10000.0 AS mars,
                   avg(u.e4) FILTER (
                       WHERE extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int) = 12
                   ) / 10000.0 AS decembre
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            JOIN mesures_journalieres_denses d ON d.serie_id = s.id
            CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
            WHERE s.grandeur_code LIKE 'aod550%' AND s.serie_porteuse_id IS NULL
            GROUP BY 1
            """
        )
    ).all()
    par_grandeur = {r.grandeur_code: r for r in lignes}
    assert par_grandeur["aod550_poussiere"].nord > par_grandeur["aod550_poussiere"].sud
    assert par_grandeur["aod550_organique"].sud > par_grandeur["aod550_organique"].nord
    assert par_grandeur["aod550"].mars > 2 * par_grandeur["aod550"].decembre


def test_province_et_commune_au_meme_point(db_session: Session) -> None:
    """Banfora et la province de la Comoé, mêmes coordonnées : même série porteuse."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, COALESCE(s.serie_porteuse_id, s.id) AS porteuse
            FROM series_metadonnees s
            WHERE s.code IN (
                'cams_eac4_aod550_journalier_bfa_prov_comoe',
                'cams_eac4_aod550_journalier_bfa_dep_banfora'
            )
            """
        )
    ).all()
    assert len(lignes) == 2 and lignes[0].porteuse == lignes[1].porteuse


def test_notes_publiques(db_session: Session) -> None:
    """Chaque note dit le stockage dense, le partage de maille et les saisons."""
    sans_mention = db_session.execute(
        text(
            """
            SELECT count(*) FROM series_metadonnees
            WHERE grandeur_code LIKE 'aod550%' AND NOT (
                note_publique LIKE '%stockage dense (ADR-0017)%'
                AND note_publique LIKE '%Maille de 0,75° la plus proche%'
                AND note_publique LIKE '%de mars à juin%'
            )
            """
        )
    ).scalar_one()
    assert sans_mention == 0
