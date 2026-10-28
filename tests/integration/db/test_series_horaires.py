"""Tests d'intégration des séries horaires des points pilotes (migrations 0011 et 0012).

Vérifie les 20 séries horaires NASA POWER (5 pilotes, 4 grandeurs) sur
2021-2025, leur accord avec la série mensuelle de la même localité et le
contrôle qualité horaire (ADR-0014).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

_PILOTES = {
    "bfa_com_ouagadougou",
    "bfa_dep_dedougou",
    "bfa_dep_dori",
    "bfa_dep_kaya",
    "bfa_dep_koupela",
}
# Grandeur : (méthode de collecte, borne basse, borne haute).
_GRANDEURS = {
    "ghi": ("modele_satellitaire", 0.0, 1400.0),
    "dni": ("modele_satellitaire", 0.0, 1400.0),
    "dhi": ("modele_satellitaire", 0.0, 900.0),
    "t2m": ("reanalyse", -5.0, 55.0),
}
_HEURES = 43_824  # 2021-2025 : 1 826 jours


def test_series_horaires(db_session: Session) -> None:
    """Une série par pilote et par grandeur, NASA POWER, granularité horaire, 2021-2025."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, s.grandeur_code, l.code AS localite, so.code AS source,
                   s.methode_collecte, s.periode_debut::text AS debut,
                   s.periode_fin::text AS fin
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.granularite = 'horaire'
              AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            """
        )
    ).all()
    assert len(lignes) == 20
    assert {(r.localite, r.grandeur_code) for r in lignes} == {
        (p, g) for p in _PILOTES for g in _GRANDEURS
    }
    for r in lignes:
        assert r.code == f"nasa_power_{r.grandeur_code}_horaire_{r.localite}"
        assert (r.source, r.methode_collecte) == ("nasa_power", _GRANDEURS[r.grandeur_code][0])
        assert (r.debut, r.fin) == ("2021-01-01", "2025-12-31"), r.code


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """43 824 heures par série, alignées sur l'heure UTC, confiance B, dans les bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, s.grandeur_code, count(*) AS n,
                   count(DISTINCT m.instant_mesure) AS heures,
                   min(m.instant_mesure AT TIME ZONE 'UTC')::text AS premier,
                   max(m.instant_mesure AT TIME ZONE 'UTC')::text AS dernier,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(date_trunc('hour', m.instant_mesure) = m.instant_mesure
                            AND m.niveau_confiance_derive = 'B') AS invariants
            FROM series_metadonnees s
            JOIN mesures_ressource_horaires m ON m.serie_id = s.id
            WHERE s.granularite = 'horaire'
              AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 20
    for r in lignes:
        _, borne_min, borne_max = _GRANDEURS[r.grandeur_code]
        assert r.n == r.heures == _HEURES, r.code
        assert (r.premier, r.dernier) == ("2021-01-01 00:00:00", "2025-12-31 23:00:00")
        assert borne_min <= r.vmin and r.vmax <= borne_max, r.code
        assert r.invariants, r.code


def test_convention_debut_d_heure(db_session: Session) -> None:
    """Chaque valeur est la moyenne de l'heure qui commence à son instant (ADR-0014).

    Le centroïde du GHI, pondéré par les heures UTC, tombe une demi-heure avant
    le midi solaire moyen (12 h - longitude / 15) : une moyenne datée de la fin
    de l'heure le placerait une demi-heure après, une valeur instantanée dessus.
    """
    lignes = db_session.execute(
        text(
            """
            SELECT l.code,
                   sum(extract(hour FROM m.instant_mesure AT TIME ZONE 'UTC') * m.valeur)
                   / sum(m.valeur) - (12 - l.longitude / 15) AS centroide
            FROM mesures_ressource_horaires m
            JOIN series_metadonnees s ON s.id = m.serie_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code = 'ghi' AND s.granularite = 'horaire'
              AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            GROUP BY l.code, l.longitude
            """
        )
    ).all()
    assert {r.code for r in lignes} == _PILOTES
    for r in lignes:
        assert -0.6 < r.centroide < -0.4, r.code


def test_sommes_horaires_egales_au_mensuel(db_session: Session) -> None:
    """Le GHI horaire cumulé par jour UTC redonne la série mensuelle de la localité.

    Les deux viennent du même produit NASA POWER : 60 mois par pilote, écart
    inférieur à 0,01 kWh/m²/jour. Ce test confirme l'unité et la complétude ;
    l'horodatage, la nuit couvrant minuit UTC, relève du test précédent.
    """
    lignes = db_session.execute(
        text(
            """
            WITH horaire AS (
                SELECT s.localite_id,
                       extract(year FROM m.instant_mesure AT TIME ZONE 'UTC')::int AS annee,
                       extract(month FROM m.instant_mesure AT TIME ZONE 'UTC')::int AS mois,
                       sum(m.valeur) / 1000.0
                       / count(DISTINCT (m.instant_mesure AT TIME ZONE 'UTC')::date) AS moyenne
                FROM mesures_ressource_horaires m
                JOIN series_metadonnees s ON s.id = m.serie_id
                WHERE s.grandeur_code = 'ghi' AND s.granularite = 'horaire'
                  AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
                GROUP BY 1, 2, 3
            )
            SELECT l.code, count(*) AS mois, max(abs(h.moyenne - mm.valeur)) AS ecart
            FROM horaire h
            JOIN localites l ON l.id = h.localite_id
            JOIN series_metadonnees s
              ON s.localite_id = h.localite_id AND s.grandeur_code = 'ghi'
             AND s.granularite = 'mensuel'
             AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            JOIN mesures_ressource_mensuelles mm
              ON mm.serie_id = s.id AND mm.annee = h.annee AND mm.mois = h.mois
            GROUP BY 1
            """
        )
    ).all()
    assert {r.code for r in lignes} == _PILOTES
    for r in lignes:
        assert r.mois == 60, r.code
        assert r.ecart < 0.01, r.code


def test_controle_qualite(db_session: Session) -> None:
    """Toutes les lignes passent le QC v1 ; le rayonnement porte ses drapeaux de fermeture.

    Aucune ligne rejetée. Les drapeaux de fermeture touchent de 25 à 35 % des
    heures de jour (GHI > 0) de chaque pilote ; la température n'en porte aucun.
    """
    lignes = db_session.execute(
        text(
            """
            SELECT l.code, s.grandeur_code,
                   bool_and(m.statut = 'valide_auto'
                            AND m.commentaire_editorial LIKE '[QC v1] valide\\_auto%')
                       AS valides,
                   count(*) FILTER (WHERE m.commentaire_editorial LIKE '%flags%') AS drapeaux,
                   count(*) FILTER (WHERE m.commentaire_editorial LIKE '%fermeture%')
                       AS fermeture,
                   count(*) FILTER (WHERE m.valeur > 0) AS positives
            FROM mesures_ressource_horaires m
            JOIN series_metadonnees s ON s.id = m.serie_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.granularite = 'horaire'
              AND s.source_id = (SELECT id FROM sources WHERE code = 'nasa_power')
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 20
    for r in lignes:
        assert r.valides, (r.code, r.grandeur_code)
        if r.grandeur_code == "t2m":
            assert r.drapeaux == 0, r.code
        elif r.grandeur_code == "ghi":
            assert 0.25 < r.fermeture / r.positives < 0.35, r.code


def test_qc_sans_journal_d_audit(db_session: Session) -> None:
    """La requalification de masse n'est pas journalisée et le trigger est réactivé."""
    journalisees = db_session.execute(
        text("SELECT count(*) FROM audit_log WHERE table_auditee = 'mesures_ressource_horaires'")
    ).scalar_one()
    actif = db_session.execute(
        text(
            "SELECT tgenabled FROM pg_trigger WHERE tgname = 'trg_audit_mesures_ressource_horaires'"
        )
    ).scalar_one()
    assert journalisees == 0
    assert actif == "O"
