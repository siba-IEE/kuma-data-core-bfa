"""Tests d'intégration de la météo complémentaire NASA POWER (migration 0020).

Vérifie les unités et les grandeurs du référentiel, les 3 582 séries denses des
398 localités (ADR-0021), leurs valeurs, leur cohérence entre grandeurs et
leurs saisons, et la fiche de la source.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_METEO_COMPLEMENTAIRE

pytestmark = pytest.mark.integration

# Grandeur : unité au référentiel.
_UNITES = {
    "t2m_min": "degree_celsius",
    "t2m_max": "degree_celsius",
    "point_rosee_2m": "degree_celsius",
    "vent_10m": "metre_par_seconde",
    "vent_10m_max": "metre_par_seconde",
    "direction_vent_10m": "degre",
    "vent_50m": "metre_par_seconde",
    "pression_surface": "kilopascal",
    "nebulosite": "pourcent",
}


def _valeurs_du_mois(grandeur: str, mois: int) -> str:
    """Requête des valeurs d'un mois, sur les porteuses d'une grandeur."""
    return f"""
        SELECT u.e4 / 10000.0 AS v
        FROM series_metadonnees s
        JOIN mesures_journalieres_denses d ON d.serie_id = s.id
        CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
        WHERE s.grandeur_code = '{grandeur}' AND s.source_id = 1
          AND s.serie_porteuse_id IS NULL AND s.stockage = 'dense'
          AND extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int) = {mois}
    """


def test_unites_et_grandeurs(db_session: Session) -> None:
    """Radian et degré ajoutés ; huit grandeurs stockées, ``vent_10m`` déjà présente."""
    unites = db_session.execute(
        text("SELECT code, grandeur, code_unite_si FROM unites WHERE grandeur = 'angle'")
    ).all()
    assert {(u.code, u.code_unite_si) for u in unites} == {
        ("radian", "radian"),
        ("degre", "radian"),
    }
    lignes = db_session.execute(
        text(
            """
            SELECT g.code, u.code AS unite, g.famille, g.strategie_calcul
            FROM grandeurs_referentiel g JOIN unites u ON u.id = g.unite_id
            WHERE g.code = ANY(:c)
            """
        ),
        {"c": list(_UNITES)},
    ).all()
    assert {r.code: r.unite for r in lignes} == _UNITES
    assert all((r.famille, r.strategie_calcul) == ("F1", "stockee") for r in lignes)


def test_series_des_398_localites(db_session: Session) -> None:
    """398 séries par grandeur, denses, 83 mailles MERRA-2 et 33 mailles CERES porteuses."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte,
                   count(*) FILTER (WHERE l.type_localite = 'prefecture') AS provinces,
                   count(*) FILTER (WHERE l.type_localite = 'commune') AS communes,
                   count(*) FILTER (WHERE s.serie_porteuse_id IS NULL) AS porteuses,
                   bool_and(s.stockage = 'dense') AS denses
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code = ANY(:c) AND s.source_id = 1 AND s.granularite = 'journalier'
            GROUP BY 1, 2, 3, 4
            """
        ),
        {"c": list(_UNITES)},
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_UNITES)
    for r in lignes:
        nebulosite = r.grandeur_code == "nebulosite"
        assert (r.debut, r.fin, r.provinces, r.communes, r.denses) == (
            "2005-01-01",
            "2025-12-31",
            47,
            351,
            True,
        ), r.grandeur_code
        assert r.methode_collecte == ("modele_satellitaire" if nebulosite else "reanalyse")
        assert r.porteuses == (33 if nebulosite else 83), r.grandeur_code


def test_valeurs_completes_et_bornees(db_session: Session) -> None:
    """7 670 jours par porteuse, aucune valeur absente, bornes des contrats tenues."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, min(v.n) AS n_min, max(v.n) AS n_max,
                   min(v.vmin) AS vmin, max(v.vmax) AS vmax
            FROM series_metadonnees s
            JOIN LATERAL (
                SELECT count(u.e4) AS n, min(u.e4) / 10000.0 AS vmin, max(u.e4) / 10000.0 AS vmax
                FROM mesures_journalieres_denses d CROSS JOIN LATERAL unnest(d.valeurs_e4) AS u(e4)
                WHERE d.serie_id = s.id
            ) v ON TRUE
            WHERE s.grandeur_code = ANY(:c) AND s.source_id = 1 AND s.serie_porteuse_id IS NULL
              AND s.stockage = 'dense' AND s.periode_debut = '2005-01-01'
              AND s.code LIKE '%journalier_bfa_%'
            GROUP BY 1
            """
        ),
        {"c": list(_UNITES)},
    ).all()
    assert len(lignes) == len(_UNITES)
    for r in lignes:
        contrat = CONTRATS_METEO_COMPLEMENTAIRE[r.grandeur_code]
        assert (r.n_min, r.n_max) == (7_670, 7_670), r.grandeur_code
        assert contrat.borne_min is not None
        assert contrat.borne_min <= r.vmin and r.vmax <= contrat.borne_max, r.grandeur_code


def test_coherence_entre_grandeurs(db_session: Session) -> None:
    """Minimum sous le maximum, rosée sous le maximum, vent moyen sous le maximum et sous 50 m."""
    resultat = db_session.execute(
        text(
            """
            WITH annees AS (
                SELECT s.localite_id, d.annee,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 't2m_min') AS tmin,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 't2m_max') AS tmax,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'point_rosee_2m') AS rosee,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'vent_10m') AS v10,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'vent_10m_max') AS v10max,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'vent_50m') AS v50
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d ON d.serie_id = s.id
                WHERE s.grandeur_code IN (
                    't2m_min', 't2m_max', 'point_rosee_2m', 'vent_10m', 'vent_10m_max', 'vent_50m'
                ) AND s.source_id = 1 AND s.serie_porteuse_id IS NULL AND s.stockage = 'dense'
                GROUP BY 1, 2
            )
            SELECT count(*) AS jours,
                   count(*) FILTER (WHERE u.tmin > u.tmax OR u.rosee > u.tmax) AS temperatures,
                   count(*) FILTER (WHERE u.v10 > u.v10max OR u.v10 > u.v50) AS vents
            FROM annees a
            CROSS JOIN LATERAL unnest(a.tmin, a.tmax, a.rosee, a.v10, a.v10max, a.v50)
                AS u(tmin, tmax, rosee, v10, v10max, v50)
            """
        )
    ).one()
    assert (resultat.jours, resultat.temperatures, resultat.vents) == (83 * 7_670, 0, 0)


def test_temperature_moyenne_aux_communes(db_session: Session) -> None:
    """Aux communes, la température moyenne est entre le minimum et le maximum, rosée sous elle."""
    resultat = db_session.execute(
        text(
            """
            WITH annees AS (
                SELECT s.localite_id, d.annee,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 't2m_min') AS tmin,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 't2m') AS tmoy,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 't2m_max') AS tmax,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'point_rosee_2m') AS rosee
                FROM series_metadonnees s
                JOIN localites l ON l.id = s.localite_id AND l.type_localite = 'commune'
                JOIN mesures_journalieres_denses d
                     ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
                WHERE s.grandeur_code IN ('t2m_min', 't2m', 't2m_max', 'point_rosee_2m')
                  AND s.source_id = 1 AND s.stockage = 'dense'
                GROUP BY 1, 2
            )
            SELECT count(*) AS jours,
                   count(*) FILTER (WHERE u.tmoy < u.tmin OR u.tmoy > u.tmax) AS hors_bornes,
                   count(*) FILTER (WHERE u.rosee > u.tmoy) AS rosee_haute
            FROM annees a
            CROSS JOIN LATERAL unnest(a.tmin, a.tmoy, a.tmax, a.rosee) AS u(tmin, tmoy, tmax, rosee)
            """
        )
    ).one()
    assert (resultat.jours, resultat.hors_bornes, resultat.rosee_haute) == (351 * 7_670, 0, 0)


def test_saisons(db_session: Session) -> None:
    """Harmattan de nord-est en janvier, mousson de sud-ouest en août ; air sec, ciel clair."""
    directions = {}
    for mois in (1, 8):
        directions[mois] = db_session.execute(
            text(
                f"""
                SELECT (degrees(atan2(avg(x.v * sind(x.dir / 10000.0)),
                                      avg(x.v * cosd(x.dir / 10000.0)))) + 360)::numeric % 360
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d ON d.serie_id = s.id
                JOIN series_metadonnees t ON t.localite_id = s.localite_id
                     AND t.grandeur_code = 'direction_vent_10m' AND t.source_id = 1
                     AND t.serie_porteuse_id IS NULL
                JOIN mesures_journalieres_denses e ON e.serie_id = t.id AND e.annee = d.annee
                CROSS JOIN LATERAL unnest(d.valeurs_e4, e.valeurs_e4)
                    WITH ORDINALITY AS x(v, dir, rang)
                WHERE s.grandeur_code = 'vent_10m' AND s.source_id = 1
                  AND s.serie_porteuse_id IS NULL AND s.stockage = 'dense'
                  AND extract(month FROM make_date(d.annee, 1, 1) + (x.rang - 1)::int) = {mois}
                """
            )
        ).scalar_one()
    assert 30 < directions[1] < 90 and 180 < directions[8] < 250, directions
    rosee = {
        m: db_session.execute(
            text(f"SELECT avg(v) FROM ({_valeurs_du_mois('point_rosee_2m', m)}) x")
        ).scalar_one()
        for m in (1, 8)
    }
    assert rosee[1] < 5 and rosee[8] > 20, rosee
    nebulosite = {
        m: db_session.execute(
            text(f"SELECT avg(v) FROM ({_valeurs_du_mois('nebulosite', m)}) x")
        ).scalar_one()
        for m in (12, 8)
    }
    assert nebulosite[8] > 2 * nebulosite[12], nebulosite


def test_notes_publiques(db_session: Session) -> None:
    """Chaque note dit le stockage dense, la maille et le jour solaire local."""
    notes = db_session.execute(
        text(
            """
            SELECT grandeur_code, note_publique FROM series_metadonnees
            WHERE grandeur_code = ANY(:c) AND source_id = 1 AND stockage = 'dense'
              AND code LIKE 'nasa_power_%_journalier_bfa_%' AND periode_debut = '2005-01-01'
              AND localite_id IN (SELECT id FROM localites WHERE type_localite = 'prefecture')
            """
        ),
        {"c": list(_UNITES)},
    ).all()
    assert len(notes) == 9 * 47
    for r in notes:
        assert "Lot des 398 localités" in r.note_publique, r.grandeur_code
        assert "stockage dense (ADR-0017)" in r.note_publique, r.grandeur_code
        assert "Jour de 0 h à 24 h UTC" in r.note_publique, r.grandeur_code
        assert ("maille de 1°" if r.grandeur_code == "nebulosite" else "MERRA-2") in r.note_publique


def test_fiche_de_la_source(db_session: Session) -> None:
    """La fiche de ``nasa_power`` est celle du Burkina Faso, avec sa consultation.

    La migration 0027 y ajoute l'horaire des localités et sa consultation (ADR-0026).
    """
    fiche = db_session.execute(
        text("SELECT date_consultation::text AS consultation, notes FROM sources WHERE id = 1")
    ).one()
    assert fiche.consultation == "2026-10-29"
    assert "Au Burkina Faso" in fiche.notes and "ADR-0021" in fiche.notes
    assert "DNI et DHI mensuels 2001-2025" in fiche.notes and "SRB" in fiche.notes
    assert "guinéen" not in fiche.notes
    description = db_session.execute(
        text("SELECT description FROM grandeurs_referentiel WHERE code = 'vent_10m'")
    ).scalar_one()
    assert "hors périmètre" not in description
