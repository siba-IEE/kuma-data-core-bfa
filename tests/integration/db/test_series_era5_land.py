"""Tests d'intégration de la météo et du rayonnement journaliers ERA5-Land (migration 0023).

Vérifie les 3 582 séries denses des 398 localités (ADR-0024), leurs valeurs,
leur cohérence entre grandeurs, l'écart de la pluie à NASA POWER, les notes
publiques et la fiche de la source.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_ERA5_LAND_JOURNALIERS
from kuma_data_core.services.capsule.acquisition import SourceCore

pytestmark = pytest.mark.integration

_ID_SOURCE = 12
_GRANDEURS = list(CONTRATS_ERA5_LAND_JOURNALIERS)


def test_series_des_398_localites(db_session: Session) -> None:
    """398 séries par grandeur, denses, réanalyse 2005-2025, 371 mailles porteuses."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte,
                   count(*) FILTER (WHERE l.type_localite = 'prefecture') AS provinces,
                   count(*) FILTER (WHERE l.type_localite = 'commune') AS communes,
                   count(*) FILTER (WHERE s.serie_porteuse_id IS NULL) AS porteuses,
                   bool_and(s.stockage = 'dense') AS denses,
                   bool_and(s.code LIKE 'era5\\_land\\_%\\_journalier\\_bfa\\_%') AS codes
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.source_id = :id AND s.granularite = 'journalier'
            GROUP BY 1, 2, 3, 4
            """
        ),
        {"id": _ID_SOURCE},
    ).all()
    assert sorted(r.grandeur_code for r in lignes) == sorted(_GRANDEURS)
    for r in lignes:
        assert (r.debut, r.fin, r.methode_collecte) == ("2005-01-01", "2025-12-31", "reanalyse")
        assert (r.provinces, r.communes, r.porteuses, r.denses, r.codes) == (
            47,
            351,
            371,
            True,
            True,
        ), r.grandeur_code


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
            WHERE s.source_id = :id AND s.serie_porteuse_id IS NULL AND s.stockage = 'dense'
            GROUP BY 1
            """
        ),
        {"id": _ID_SOURCE},
    ).all()
    assert len(lignes) == len(_GRANDEURS)
    for r in lignes:
        contrat = CONTRATS_ERA5_LAND_JOURNALIERS[r.grandeur_code]
        assert (r.n_min, r.n_max) == (7_670, 7_670), r.grandeur_code
        assert contrat.borne_min is not None
        assert contrat.borne_min <= r.vmin and r.vmax <= contrat.borne_max, r.grandeur_code
        if r.grandeur_code == "direction_vent_10m":
            assert r.vmax < 360.0


def test_coherence_entre_grandeurs(db_session: Session) -> None:
    """Chaque jour : minimum, moyenne et maximum ordonnés, rosée sous la moyenne."""
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
                JOIN mesures_journalieres_denses d ON d.serie_id = s.id
                WHERE s.grandeur_code IN ('t2m_min', 't2m', 't2m_max', 'point_rosee_2m')
                  AND s.source_id = :id AND s.serie_porteuse_id IS NULL
                GROUP BY 1, 2
            )
            SELECT count(*) AS jours,
                   count(*) FILTER (WHERE u.tmin > u.tmoy OR u.tmoy > u.tmax) AS temperatures,
                   count(*) FILTER (WHERE u.rosee > u.tmoy) AS rosee_haute
            FROM annees a
            CROSS JOIN LATERAL unnest(a.tmin, a.tmoy, a.tmax, a.rosee) AS u(tmin, tmoy, tmax, rosee)
            """
        ),
        {"id": _ID_SOURCE},
    ).one()
    assert (resultat.jours, resultat.temperatures, resultat.rosee_haute) == (371 * 7_670, 0, 0)


def test_pluie_sous_nasa_power(db_session: Session) -> None:
    """Aux communes, 2005-2025 : un tiers de pluie de moins que NASA POWER (ADR-0024)."""
    resultat = db_session.execute(
        text(
            """
            SELECT s.source_id, sum(u.e4) / 10000.0 / 351 / 21 AS annuel
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id AND l.type_localite = 'commune'
            JOIN mesures_journalieres_denses d
                 ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
            CROSS JOIN LATERAL unnest(d.valeurs_e4) AS u(e4)
            WHERE s.grandeur_code = 'precipitation' AND s.source_id IN (1, :id)
              AND s.stockage = 'dense' AND d.annee BETWEEN 2005 AND 2025
            GROUP BY 1
            """
        ),
        {"id": _ID_SOURCE},
    ).all()
    annuel = {r.source_id: float(r.annuel) for r in resultat}
    assert abs(annuel[_ID_SOURCE] - 611) < 1 and abs(annuel[1] - 912) < 1
    assert 0.66 < annuel[_ID_SOURCE] / annuel[1] < 0.68


def test_capsule_records_de_nasa_power(db_session: Session) -> None:
    """Les records de température de la capsule viennent de NASA POWER seul.

    ERA5-Land sert aussi ``t2m_min`` et ``t2m_max`` : les records et leur source
    doivent rester ceux de NASA POWER (``SOURCE_TEMPERATURES``).
    """
    localite_id, froid, chaud = db_session.execute(
        text(
            """
            SELECT s.localite_id,
                   min(u.e4) FILTER (WHERE s.grandeur_code = 't2m_min') / 10000.0 AS froid,
                   max(u.e4) FILTER (WHERE s.grandeur_code = 't2m_max') / 10000.0 AS chaud
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            JOIN mesures_journalieres_denses d
                 ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
            CROSS JOIN LATERAL unnest(d.valeurs_e4) AS u(e4)
            WHERE l.code = 'bfa_com_ouagadougou' AND s.source_id = 1
              AND s.grandeur_code IN ('t2m_min', 't2m_max')
            GROUP BY 1
            """
        )
    ).one()
    temperatures, provenance = SourceCore(session=db_session)._extremes_temperature(localite_id)
    assert temperatures is not None and provenance is not None
    assert provenance["source"] == "nasa_power"
    assert (temperatures["froidC"], temperatures["chaudC"]) == (
        round(float(froid), 2),
        round(float(chaud), 2),
    )


def test_notes_publiques(db_session: Session) -> None:
    """Notes : maille de 0,1°, jour UTC, mises en garde de la pluie et du rayonnement."""
    notes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code,
                   bool_and(s.note_publique LIKE '%réanalyse ERA5-Land du CEPMMT (maille de 0,1°)%'
                            AND s.note_publique LIKE '%Jour compté en temps universel%'
                            AND s.note_publique LIKE '%stockage dense (ADR-0017)%') AS communes,
                   count(*) FILTER (WHERE s.note_publique LIKE '%même maille%') AS partagees
            FROM series_metadonnees s
            WHERE s.source_id = :id AND s.granularite = 'journalier'
            GROUP BY 1
            """
        ),
        {"id": _ID_SOURCE},
    ).all()
    assert all(r.communes for r in notes)
    # 27 mailles portent deux localités chacune : 54 notes par grandeur le disent.
    assert {r.partagees for r in notes} == {54}
    mises_en_garde = db_session.execute(
        text(
            """
            SELECT grandeur_code, min(note_publique) AS note
            FROM series_metadonnees
            WHERE source_id = :id AND grandeur_code IN ('precipitation', 'ghi')
            GROUP BY 1
            """
        ),
        {"id": _ID_SOURCE},
    ).all()
    textes = {r.grandeur_code: r.note for r in mises_en_garde}
    assert "Un tiers de pluie de moins que NASA POWER" in textes["precipitation"]
    assert "Source de comparaison, pas de référence." in textes["ghi"]


def test_fiche_de_la_source(db_session: Session) -> None:
    """La fiche de ``ecmwf_era5_land`` décrit le jeu horaire et le Burkina Faso."""
    fiche = db_session.execute(
        text(
            "SELECT date_consultation::text AS consultation, url, doi, notes, "
            "metadonnees -> 'produits_utilises' AS produits FROM sources WHERE id = :id"
        ),
        {"id": _ID_SOURCE},
    ).one()
    assert fiche.consultation == "2026-10-28"
    assert fiche.url.endswith("/reanalysis-era5-land-timeseries")
    assert fiche.doi == "10.24381/ee82e357"
    assert "Au Burkina Faso" in fiche.notes and "ADR-0024" in fiche.notes
    assert "Vague 4" not in fiche.notes
    assert fiche.produits == ["hourly time-series (agrégé en journalier)"]
