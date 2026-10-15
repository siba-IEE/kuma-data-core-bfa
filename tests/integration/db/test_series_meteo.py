"""Tests d'intégration des séries journalières de météo NASA POWER (migration 0010).

Vérifie les 141 séries brutes (47 provinces, 3 grandeurs), leurs mesures et
leur alignement sur le GHI journalier, dont elles sont les compagnes (ADR-0013).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : (borne basse, borne haute).
_BORNES = {"t2m": (0.0, 50.0), "rh2m": (0.0, 100.0), "precipitation": (0.0, 500.0)}


def test_series_meteo(db_session: Session) -> None:
    """47 séries par grandeur, NASA POWER réanalyse, 1991-2025, provinces."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, s.granularite, l.type_localite, so.code AS source,
                   count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code IN ('t2m', 'rh2m', 'precipitation')
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_BORNES)
    for r in lignes:
        assert (r.debut, r.fin, r.n) == ("1991-01-01", "2025-12-31", 47), r.grandeur_code
        assert (r.methode_collecte, r.granularite) == ("reanalyse", "journalier")
        assert (r.type_localite, r.source) == ("prefecture", "nasa_power")


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """Chaque série a ses 12 784 jours, en brut, confiance B, valeurs dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.code, count(m.id) AS n,
                   count(DISTINCT m.instant_mesure) AS jours,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(m.statut = 'brut' AND m.niveau_confiance_derive = 'B') AS invariants
            FROM series_metadonnees s
            LEFT JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.grandeur_code IN ('t2m', 'rh2m', 'precipitation')
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 141
    for r in lignes:
        borne_min, borne_max = _BORNES[r.grandeur_code]
        assert r.n == r.jours == 12_784, r.code
        assert borne_min <= r.vmin and r.vmax <= borne_max, r.code
        assert r.invariants, r.code


def test_compagnes_du_ghi_journalier(db_session: Session) -> None:
    """Chaque province a une série météo de même source, granularité et début que son GHI."""
    manquantes = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM series_metadonnees g
            CROSS JOIN (VALUES ('t2m'), ('rh2m'), ('precipitation')) AS m(grandeur)
            WHERE g.grandeur_code = 'ghi' AND g.granularite = 'journalier'
              AND NOT EXISTS (
                  SELECT 1 FROM series_metadonnees c
                  WHERE c.localite_id = g.localite_id AND c.source_id = g.source_id
                    AND c.grandeur_code = m.grandeur AND c.granularite = 'journalier'
                    AND c.periode_debut = g.periode_debut
              )
            """
        )
    ).scalar_one()
    assert manquantes == 0


def test_mises_en_garde_de_la_pluie(db_session: Session) -> None:
    """Toutes les séries de pluie signalent la rupture de 2015 ; la valeur suspecte, deux."""
    lignes = db_session.execute(
        text(
            """
            SELECT code, note_publique LIKE '%2 décembre 2025%' AS suspecte,
                   note_publique LIKE '%partir de 2015%' AS rupture
            FROM series_metadonnees
            WHERE grandeur_code = 'precipitation'
            """
        )
    ).all()
    assert len(lignes) == 47 and all(r.rupture for r in lignes)
    assert {r.code for r in lignes if r.suspecte} == {
        "nasa_power_precipitation_journalier_bfa_prov_comoe",
        "nasa_power_precipitation_journalier_bfa_prov_leraba",
    }


def test_valeur_de_pluie_suspecte_signalee(db_session: Session) -> None:
    """La pluie du 2 décembre 2025 (321,8 mm) est gravée telle quelle et signalée."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, m.valeur, s.note_publique LIKE '%2 décembre 2025%' AS signalee
            FROM series_metadonnees s
            JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.grandeur_code = 'precipitation' AND m.valeur > 300
            """
        )
    ).all()
    assert {r.code for r in lignes} == {
        "nasa_power_precipitation_journalier_bfa_prov_comoe",
        "nasa_power_precipitation_journalier_bfa_prov_leraba",
    }
    assert all(r.valeur == pytest.approx(321.83) and r.signalee for r in lignes)
