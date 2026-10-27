"""Tests d'intégration des séries mensuelles CAMS Radiation (migration 0008).

Vérifie les 1 194 séries brutes (398 localités, 3 grandeurs) et leurs mesures
(ADR-0011).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_BORNES = {"ghi": 8.5, "dni": 10.0, "dhi": 6.0}


def test_series_cams(db_session: Session) -> None:
    """398 séries par grandeur, période 2005-2025, provinces et communes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, s.granularite, l.type_localite, count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE so.code = 'cams_radiation' AND s.granularite = 'mensuel'
            GROUP BY 1, 2, 3, 4, 5, 6
            """
        )
    ).all()
    vues: dict[str, dict[str, int]] = {}
    for r in lignes:
        assert (r.debut, r.fin) == ("2005-01-01", "2025-12-31"), r.grandeur_code
        assert (r.methode_collecte, r.granularite) == ("modele_satellitaire", "mensuel")
        vues.setdefault(r.grandeur_code, {})[r.type_localite] = r.n
    assert vues == {g: {"prefecture": 47, "commune": 351} for g in _BORNES}


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """Chaque série a ses 252 mois, en brut, confiance B, valeurs dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.code, count(m.id) AS n,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(m.statut = 'brut') AS brut,
                   bool_and(m.niveau_confiance_derive = 'B') AS confiance_b
            FROM series_metadonnees s
            LEFT JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
            WHERE s.source_id = 13 AND s.granularite = 'mensuel'
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 1_194
    for r in lignes:
        assert r.n == 252, r.code
        assert r.vmin > 0.0 and r.vmax <= _BORNES[r.grandeur_code], r.code
        assert r.brut and r.confiance_b, r.code
    total = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees s ON s.id = m.serie_id
            WHERE s.source_id = 13 AND s.granularite = 'mensuel'
            """
        )
    ).scalar_one()
    assert total == 300_888


def test_fermeture(db_session: Session) -> None:
    """GHI, DNI et DHI CAMS ferment : DHI ≤ GHI et GHI - DHI ≤ DNI chaque mois."""
    mois = db_session.execute(
        text(
            """
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE dhi > ghi) AS diffus,
                   count(*) FILTER (WHERE ghi - dhi > dni + 0.0002) AS direct
            FROM (
                SELECT s.localite_id, m.annee, m.mois,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'ghi') AS ghi,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'dni') AS dni,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'dhi') AS dhi
                FROM series_metadonnees s
                JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
                WHERE s.source_id = 13 AND s.granularite = 'mensuel'
                GROUP BY 1, 2, 3
            ) par_mois
            """
        )
    ).one()
    assert (mois.n, mois.diffus, mois.direct) == (398 * 252, 0, 0)


def test_note_publique(db_session: Session) -> None:
    """La mise en garde Meteosat figure sur les séries GHI et DNI, pas sur le DHI."""
    lignes = db_session.execute(
        text(
            """
            SELECT grandeur_code, bool_and(note_publique LIKE '%Meteosat%') AS meteosat,
                   bool_or(note_publique LIKE '%Meteosat%') AS une
            FROM series_metadonnees
            WHERE source_id = 13 AND granularite = 'mensuel'
            GROUP BY 1
            """
        )
    ).all()
    vues = {r.grandeur_code: (r.meteosat, r.une) for r in lignes}
    assert vues == {"ghi": (True, True), "dni": (True, True), "dhi": (False, False)}
