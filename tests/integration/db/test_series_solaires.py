"""Tests d'intégration des séries solaires mensuelles (migrations 0005 et 0006).

Vérifie les 2 786 séries brutes (398 localités, 7 familles), leurs mesures, la
source ``era5_pvgis`` et la méthode ``reanalyse`` (ADR-0009). Le contrôle du
gradient nord-sud couvre aussi CAMS Radiation (migration 0008).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Famille (source, grandeur) : (période, nombre de mois par série, borne haute).
_FAMILLES = {
    ("nasa_power", "ghi"): ("1991-01-01", "2025-12-31", 420, 8.5),
    ("nasa_power", "dni"): ("2001-01-01", "2025-12-31", 300, 10.0),
    ("nasa_power", "dhi"): ("2001-01-01", "2025-12-31", 300, 6.0),
    ("sarah3_monthly", "ghi"): ("2005-01-01", "2023-12-31", 228, 8.5),
    ("sarah3_monthly", "dni"): ("2005-01-01", "2023-12-31", 228, 10.0),
    ("era5_pvgis", "ghi"): ("2005-01-01", "2023-12-31", 228, 8.5),
    ("era5_pvgis", "dni"): ("2005-01-01", "2023-12-31", 228, 10.0),
}


def test_source_era5_pvgis(db_session: Session) -> None:
    """La source ERA5 via PVGIS existe sous l'id 16."""
    code = db_session.execute(text("SELECT code FROM sources WHERE id = 16")).scalar_one()
    assert code == "era5_pvgis"


def test_series_par_famille(db_session: Session) -> None:
    """398 séries par famille, période, méthode et localités (provinces et communes)."""
    lignes = db_session.execute(
        text(
            """
            SELECT so.code AS source, s.grandeur_code, s.periode_debut::text AS debut,
                   s.periode_fin::text AS fin, s.methode_collecte, s.granularite,
                   l.type_localite, count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.granularite = 'mensuel' AND so.code <> 'cams_radiation'
            GROUP BY 1, 2, 3, 4, 5, 6, 7
            """
        )
    ).all()
    vues: dict[tuple[str, str], dict[str, int]] = {}
    for r in lignes:
        debut, fin, _, _ = _FAMILLES[(r.source, r.grandeur_code)]
        assert (r.debut, r.fin) == (debut, fin), (r.source, r.grandeur_code)
        assert r.granularite == "mensuel"
        attendu = "reanalyse" if r.source == "era5_pvgis" else "modele_satellitaire"
        assert r.methode_collecte == attendu, r.source
        vues.setdefault((r.source, r.grandeur_code), {})[r.type_localite] = r.n
    assert vues == {f: {"prefecture": 47, "commune": 351} for f in _FAMILLES}


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """Chaque série a tous ses mois, en brut, confiance B, valeurs dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT so.code AS source, s.grandeur_code, s.code,
                   count(m.id) AS n, min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(m.statut = 'brut') AS brut,
                   bool_and(m.niveau_confiance_derive = 'B') AS confiance_b
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            LEFT JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
            WHERE s.granularite = 'mensuel' AND so.code <> 'cams_radiation'
            GROUP BY 1, 2, 3
            """
        )
    ).all()
    assert len(lignes) == 2_786
    for r in lignes:
        _, _, nb_mois, borne = _FAMILLES[(r.source, r.grandeur_code)]
        assert r.n == nb_mois, r.code
        assert r.vmin > 0.0 and r.vmax <= borne, r.code
        assert r.brut and r.confiance_b, r.code
    total = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM mesures_ressource_mensuelles m
            JOIN series_metadonnees s ON s.id = m.serie_id
            WHERE s.source_id <> 13
            """
        )
    ).scalar_one()
    assert total == 768_936


def test_gradient_nord_sud_du_ghi(db_session: Session) -> None:
    """Le GHI moyen croît du sud vers le nord dans chaque source (contrôle de cohérence)."""
    lignes = db_session.execute(
        text(
            """
            SELECT so.code AS source, corr(l.latitude, moy.ghi) AS r
            FROM (
                SELECT s.id, s.localite_id, s.source_id, avg(m.valeur) AS ghi
                FROM series_metadonnees s
                JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
                WHERE s.grandeur_code = 'ghi' AND m.annee BETWEEN 2005 AND 2023
                GROUP BY s.id, s.localite_id, s.source_id
            ) moy
            JOIN localites l ON l.id = moy.localite_id
            JOIN sources so ON so.id = moy.source_id
            WHERE l.type_localite = 'commune'
            GROUP BY so.code
            """
        )
    ).all()
    assert {r.source for r in lignes} == {
        "nasa_power",
        "sarah3_monthly",
        "era5_pvgis",
        "cams_radiation",
    }
    for r in lignes:
        assert r.r > 0.5, r.source
