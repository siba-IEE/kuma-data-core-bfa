"""Tests d'intégration du rayonnement journalier CAMS Radiation (migration 0019, ADR-0020).

Vérifie les deux grandeurs du référentiel, les 1 990 séries denses des
398 localités, leurs valeurs, leur accord avec les séries mensuelles CAMS et
leurs notes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : (borne basse incluse ou None, borne haute).
_GRANDEURS = {
    "ghi": (None, 9.0),
    "dni": (0.0, 11.0),
    "dhi": (None, 6.5),
    "ghi_ciel_clair": (None, 9.0),
    "dni_ciel_clair": (None, 11.0),
}


def test_grandeurs_du_referentiel(db_session: Session) -> None:
    """Deux grandeurs de ciel clair, stockées, en kWh/m²/jour."""
    lignes = db_session.execute(
        text(
            """
            SELECT g.code, u.code AS unite, g.strategie_calcul
            FROM grandeurs_referentiel g JOIN unites u ON u.id = g.unite_id
            WHERE g.code LIKE '%ciel_clair'
            """
        )
    ).all()
    assert {(r.code, r.unite, r.strategie_calcul) for r in lignes} == {
        ("ghi_ciel_clair", "kwh_par_m2_jour", "stockee"),
        ("dni_ciel_clair", "kwh_par_m2_jour", "stockee"),
    }


def test_series_des_398_localites(db_session: Session) -> None:
    """398 séries par grandeur, denses, 394 porteuses : quatre provinces lisent leur chef-lieu."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, count(*) AS n,
                   count(*) FILTER (WHERE s.serie_porteuse_id IS NULL) AS porteuses,
                   array_agg(l.code ORDER BY l.code) FILTER (WHERE s.serie_porteuse_id IS NOT NULL)
                       AS lectrices
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.source_id = 13 AND s.granularite = 'journalier' AND s.stockage = 'dense'
            GROUP BY 1, 2, 3, 4
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_GRANDEURS)
    for r in lignes:
        assert (r.debut, r.fin, r.methode_collecte) == (
            "2005-01-01",
            "2025-12-31",
            "modele_satellitaire",
        )
        assert (r.n, r.porteuses) == (398, 394)
        assert r.lectrices == [
            "bfa_prov_boulkiemde",
            "bfa_prov_comoe",
            "bfa_prov_loroum",
            "bfa_prov_passore",
        ]


def test_valeurs_bornees_et_jours_non_servis(db_session: Session) -> None:
    """Bornes tenues ; les jours non servis tombent en 2005-2006 et jamais par ciel clair."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, min(u.e4) / 10000.0 AS vmin, max(u.e4) / 10000.0 AS vmax,
                   count(*) - count(u.e4) AS absents,
                   count(*) FILTER (WHERE u.e4 IS NULL AND d.annee > 2006) AS absents_apres_2006
            FROM series_metadonnees s
            JOIN mesures_journalieres_denses d ON d.serie_id = s.id
            CROSS JOIN LATERAL unnest(d.valeurs_e4) AS u(e4)
            WHERE s.source_id = 13 AND s.stockage = 'dense'
            GROUP BY 1
            """
        )
    ).all()
    for r in lignes:
        basse, haute = _GRANDEURS[r.grandeur_code]
        assert (r.vmin > 0.0 if basse is None else r.vmin >= basse) and r.vmax <= haute
        assert r.absents_apres_2006 == 0, r.grandeur_code
        assert r.absents == (0 if "ciel_clair" in r.grandeur_code else 1_958), r.grandeur_code


def test_ghi_sous_le_ciel_clair(db_session: Session) -> None:
    """Le GHI tous temps ne dépasse pas le GHI par ciel clair, à 1 Wh/m² près."""
    depassements = db_session.execute(
        text(
            """
            WITH annees AS (
                SELECT s.localite_id, s.grandeur_code, d.annee, d.valeurs_e4
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d ON d.serie_id = s.id
                WHERE s.source_id = 13 AND s.grandeur_code IN ('ghi', 'ghi_ciel_clair')
            )
            SELECT count(*) AS jours, count(*) FILTER (WHERE u.g > u.c + 10) AS depassements
            FROM annees g
            JOIN annees c ON (c.localite_id, c.annee) = (g.localite_id, g.annee)
                         AND c.grandeur_code = 'ghi_ciel_clair'
            CROSS JOIN LATERAL unnest(g.valeurs_e4, c.valeurs_e4) AS u(g, c)
            WHERE g.grandeur_code = 'ghi' AND u.g IS NOT NULL
            """
        )
    ).one()
    assert depassements.jours == 394 * 7_670 - 1_958
    assert depassements.depassements == 0


@pytest.mark.parametrize("grandeur", ["ghi", "dni", "dhi"])
def test_accord_avec_le_mensuel(db_session: Session, grandeur: str) -> None:
    """Sur les mois complets, la moyenne des jours redonne la série mensuelle CAMS."""
    ecart = db_session.execute(
        text(
            """
            WITH jours AS (
                SELECT p.localite_id, d.annee,
                       extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int)::int
                           AS mois,
                       avg(u.e4 / 10000.0) AS moyenne, count(*) - count(u.e4) AS absents
                FROM series_metadonnees p
                JOIN mesures_journalieres_denses d ON d.serie_id = p.id
                CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
                WHERE p.grandeur_code = :g AND p.source_id = 13 AND p.stockage = 'dense'
                GROUP BY 1, 2, 3
            )
            SELECT count(*) AS n, max(abs(jours.moyenne - mm.valeur)) AS ecart
            FROM jours
            JOIN series_metadonnees s
              ON s.localite_id = jours.localite_id AND s.grandeur_code = :g
             AND s.granularite = 'mensuel' AND s.source_id = 13
            JOIN mesures_ressource_mensuelles mm
              ON mm.serie_id = s.id AND mm.annee = jours.annee AND mm.mois = jours.mois
             AND mm.valide_au IS NULL
            WHERE jours.absents = 0
            """
        ),
        {"g": grandeur},
    ).one()
    # Mois complets : tous, sauf ceux de 2005-2006 qui comptent un jour non servi.
    assert ecart.n > 394 * 21 * 12 * 0.98
    assert ecart.ecart < 0.0005


def test_notes_publiques(db_session: Session) -> None:
    """Chaque note dit le service, le point, le jour UTC ; la fermeture pour le GHI."""
    sans_mention = db_session.execute(
        text(
            """
            SELECT count(*) FROM series_metadonnees
            WHERE source_id = 13 AND stockage = 'dense' AND NOT (
                note_publique LIKE '%CAMS Radiation Service v4.6%'
                AND note_publique LIKE '%interrogé au point de la localité%'
                AND note_publique LIKE '%temps universel%'
                AND (grandeur_code <> 'ghi' OR note_publique LIKE '%somme exacte%')
            )
            """
        )
    ).scalar_one()
    assert sans_mention == 0


def test_fiche_de_la_source(db_session: Session) -> None:
    """La fiche de ``cams_radiation`` décrit le Burkina Faso et non plus le dépôt d'origine."""
    fiche = db_session.execute(
        text("SELECT date_consultation::text AS consultation, notes FROM sources WHERE id = 13")
    ).one()
    assert fiche.consultation == "2026-10-27"
    assert "ADR-0020" in fiche.notes and "398 localités" in fiche.notes
    assert "Vague" not in fiche.notes and "2026 »" not in fiche.notes
