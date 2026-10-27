"""Tests d'intégration des séries journalières de particules fines CAMS EAC4 (migration 0013).

Vérifie les 94 séries brutes (47 provinces, PM2.5 et PM10), leurs mesures
2005-2025 et leur alignement sur la pluie journalière NASA POWER, compagne du
proxy de salissure (ADR-0015).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_JOURS = 7_670  # 2005-2025
# Plafonds observés aux provinces (744 et 1 017 µg/m³), sous les bornes du contrat
# (2 000 et 3 000 µg/m³, ADR-0018).
_BORNES = {"pm2_5": 1000.0, "pm10": 1500.0}


def test_series_pm(db_session: Session) -> None:
    """47 séries par grandeur, CAMS EAC4 réanalyse, journalier, 2005-2025, provinces."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, s.granularite, l.type_localite, so.code AS source,
                   count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code IN ('pm2_5', 'pm10') AND s.stockage = 'versionne'
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == {"pm2_5", "pm10"}
    for r in lignes:
        assert (r.debut, r.fin, r.n) == ("2005-01-01", "2025-12-31", 47), r.grandeur_code
        assert (r.methode_collecte, r.granularite) == ("reanalyse", "journalier")
        assert (r.type_localite, r.source) == ("prefecture", "cams_eac4")


def test_mesures_completes(db_session: Session) -> None:
    """Chaque série a ses 7 670 jours, en brut, confiance B, valeurs dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, s.grandeur_code, count(m.id) AS n,
                   count(DISTINCT m.instant_mesure) AS jours,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(m.statut = 'brut' AND m.niveau_confiance_derive = 'B') AS invariants
            FROM series_metadonnees s
            JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.grandeur_code IN ('pm2_5', 'pm10')
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 94
    for r in lignes:
        assert r.n == r.jours == _JOURS, r.code
        assert r.vmin > 0.0 and r.vmax <= _BORNES[r.grandeur_code], r.code
        assert r.invariants, r.code


def test_niveaux(db_session: Session) -> None:
    """Moyennes des provinces et maximum du 13 novembre 2013 dans la Gobnangou, en µg/m³.

    Une erreur d'unité (facteur 1 000) ou de maille ferait échouer ce test.
    """
    moyennes = dict(
        db_session.execute(
            text(
                """
                SELECT s.grandeur_code, avg(m.valeur)
                FROM series_metadonnees s
                JOIN mesures_ressource m ON m.serie_id = s.id
                WHERE s.source_id = 15
                GROUP BY 1
                """
            )
        ).all()
    )
    assert moyennes["pm2_5"] == pytest.approx(39.62, rel=0.01)
    assert moyennes["pm10"] == pytest.approx(51.60, rel=0.01)
    pic = dict(
        db_session.execute(
            text(
                """
                SELECT s.grandeur_code, m.valeur
                FROM series_metadonnees s
                JOIN mesures_ressource m ON m.serie_id = s.id
                WHERE s.code IN ('cams_eac4_pm2_5_journalier_bfa_prov_gobnangou',
                                 'cams_eac4_pm10_journalier_bfa_prov_gobnangou')
                  AND m.instant_mesure = '2013-11-13'
                """
            )
        ).all()
    )
    assert pic == {"pm2_5": pytest.approx(743.9822), "pm10": pytest.approx(1016.8192)}


def test_pm2_5_sous_pm10(db_session: Session) -> None:
    """Chaque jour, le PM2.5 d'une province ne dépasse pas son PM10."""
    depassements = db_session.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE fines > grosses OR fines IS NULL OR grosses IS NULL)
            FROM (
                SELECT max(m.valeur) FILTER (WHERE s.grandeur_code = 'pm2_5') AS fines,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'pm10') AS grosses
                FROM series_metadonnees s
                JOIN mesures_ressource m ON m.serie_id = s.id
                WHERE s.source_id = 15
                GROUP BY s.localite_id, m.instant_mesure
            ) AS jours
            """
        )
    ).scalar_one()
    assert depassements == 0


def test_saison_seche(db_session: Session) -> None:
    """L'harmattan : le PM10 de décembre à mars dépasse au moins deux fois celui de l'hivernage."""
    seche, humide = db_session.execute(
        text(
            """
            SELECT avg(m.valeur) FILTER (
                       WHERE extract(month FROM m.instant_mesure) IN (12, 1, 2, 3)),
                   avg(m.valeur) FILTER (WHERE extract(month FROM m.instant_mesure) IN (7, 8, 9))
            FROM series_metadonnees s
            JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.grandeur_code = 'pm10' AND s.source_id = 15
            """
        )
    ).one()
    assert seche > 2 * humide


def test_compagne_pluie(db_session: Session) -> None:
    """Chaque province a une pluie journalière NASA POWER qui recouvre 2005-2025."""
    sans_pluie = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM series_metadonnees p
            WHERE p.grandeur_code = 'pm2_5' AND p.source_id = 15
              AND NOT EXISTS (
                  SELECT 1 FROM series_metadonnees c
                  JOIN sources so ON so.id = c.source_id
                  WHERE c.localite_id = p.localite_id AND so.code = 'nasa_power'
                    AND c.grandeur_code = 'precipitation' AND c.granularite = 'journalier'
                    AND c.periode_debut <= p.periode_debut AND c.periode_fin >= p.periode_fin
              )
            """
        )
    ).scalar_one()
    assert sans_pluie == 0


def test_note_publique(db_session: Session) -> None:
    """Chaque note signale la maille, les feux de brousse et les pas servis à zéro."""
    sans_mise_en_garde = db_session.execute(
        text(
            """
            SELECT count(*) FROM series_metadonnees
            WHERE source_id = 15 AND stockage = 'versionne' AND NOT (
                note_publique LIKE '%34 mailles pour 47 provinces%'
                AND note_publique LIKE '%feux de brousse%'
                AND note_publique LIKE '%servis à zéro%'
            )
            """
        )
    ).scalar_one()
    assert sans_mise_en_garde == 0


def test_fiche_source(db_session: Session) -> None:
    """La fiche de la source ``cams_eac4`` décrit le Burkina Faso, plus la Guinée."""
    fiche = db_session.execute(
        text(
            "SELECT doi, notes, metadonnees->>'periode_reelle' AS periode "
            "FROM sources WHERE code = 'cams_eac4'"
        )
    ).one()
    assert (fiche.doi, fiche.periode) == ("10.24381/d58bbf47", "2005-01-01 a 2025-12-31")
    assert "2005-01-01 à 2025-12-31" in fiche.notes
    assert "2021" not in fiche.notes
