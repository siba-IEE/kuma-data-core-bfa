"""Tests d'intégration des séries journalières NASA POWER (migration 0007).

Vérifie les 141 séries brutes (47 provinces, 3 grandeurs), leurs mesures et leur
accord avec les séries mensuelles NASA POWER (ADR-0010).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : (période, nombre de jours par série, borne haute).
_GRANDEURS = {
    "ghi": ("1991-01-01", "2025-12-31", 12_784, 9.0),
    "dni": ("2001-01-01", "2025-12-31", 9_131, 11.0),
    "dhi": ("2001-01-01", "2025-12-31", 9_131, 6.5),
}


def test_series_journalieres(db_session: Session) -> None:
    """47 séries par grandeur, aux provinces, NASA POWER, période du contrat."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   so.code AS source, s.methode_collecte, l.type_localite, count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.granularite = 'journalier' AND s.grandeur_code IN ('ghi', 'dni', 'dhi')
              AND s.stockage = 'versionne'
            GROUP BY 1, 2, 3, 4, 5, 6
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_GRANDEURS)
    for r in lignes:
        debut, fin, _, _ = _GRANDEURS[r.grandeur_code]
        assert (r.debut, r.fin) == (debut, fin), r.grandeur_code
        assert (r.source, r.methode_collecte) == ("nasa_power", "modele_satellitaire")
        assert (r.type_localite, r.n) == ("prefecture", 47)


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """Chaque série a tous ses jours, en brut, confiance B, valeurs dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.code, count(m.id) AS n,
                   count(DISTINCT m.instant_mesure) AS jours,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(m.statut = 'brut') AS brut,
                   bool_and(m.niveau_confiance_derive = 'B') AS confiance_b,
                   bool_and(m.instant_mesure BETWEEN s.periode_debut AND s.periode_fin) AS dedans
            FROM series_metadonnees s
            LEFT JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.granularite = 'journalier' AND s.grandeur_code IN ('ghi', 'dni', 'dhi')
              AND s.stockage = 'versionne'
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 141
    for r in lignes:
        _, _, nb_jours, borne = _GRANDEURS[r.grandeur_code]
        assert r.n == r.jours == nb_jours, r.code
        assert r.vmin > 0.0 and r.vmax <= borne, r.code
        assert r.brut and r.confiance_b and r.dedans, r.code
    total = db_session.execute(
        text(
            """
            SELECT count(*) FROM mesures_ressource m
            JOIN series_metadonnees s ON s.id = m.serie_id
            WHERE s.grandeur_code IN ('ghi', 'dni', 'dhi')
            """
        )
    ).scalar_one()
    assert total == 1_459_162


def test_accord_avec_le_mensuel(db_session: Session) -> None:
    """La moyenne des jours d'un mois redonne la série mensuelle NASA POWER (arrondi)."""
    ecart = db_session.execute(
        text(
            """
            WITH jours AS (
                SELECT s.localite_id, s.grandeur_code,
                       extract(year FROM m.instant_mesure)::int AS annee,
                       extract(month FROM m.instant_mesure)::int AS mois,
                       avg(m.valeur) AS moyenne
                FROM series_metadonnees s
                JOIN mesures_ressource m ON m.serie_id = s.id
                WHERE s.granularite = 'journalier' AND s.grandeur_code IN ('ghi', 'dni', 'dhi')
              AND s.stockage = 'versionne'
                GROUP BY 1, 2, 3, 4
            )
            SELECT count(*) AS n, max(abs(j.moyenne - mm.valeur)) AS ecart
            FROM jours j
            JOIN series_metadonnees s
              ON s.localite_id = j.localite_id AND s.grandeur_code = j.grandeur_code
             AND s.granularite = 'mensuel' AND s.source_id = 1
            JOIN mesures_ressource_mensuelles mm
              ON mm.serie_id = s.id AND mm.annee = j.annee AND mm.mois = j.mois
            """
        )
    ).one()
    assert ecart.n == 47 * (420 + 300 + 300)
    assert ecart.ecart < 0.0005


def test_diffus_inferieur_au_global(db_session: Session) -> None:
    """Aucun jour où le DHI dépasse le GHI au même point."""
    violations = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM (
                SELECT s.localite_id, m.instant_mesure,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'dhi') AS dhi,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'ghi') AS ghi
                FROM series_metadonnees s
                JOIN mesures_ressource m ON m.serie_id = s.id
                WHERE s.granularite = 'journalier' AND s.grandeur_code IN ('ghi', 'dhi')
                GROUP BY 1, 2
            ) jours
            WHERE dhi > ghi
            """
        )
    ).scalar_one()
    assert violations == 0
