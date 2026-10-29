"""Tests d'intégration du rayonnement horaire CAMS Radiation (migration 0022).

Vérifie les 20 séries horaires des cinq points pilotes sur 2021-2025
(ADR-0023), la convention de début d'heure, l'accord avec les séries
journalières CAMS, le ciel clair, le contrôle qualité et la fiche de la source.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.api.v1.horaire import _chercher_serie_horaire_stockee
from kuma_data_core.services.capsule.acquisition import SourceCore

pytestmark = pytest.mark.integration

_PILOTES = {
    "bfa_com_ouagadougou",
    "bfa_dep_dedougou",
    "bfa_dep_dori",
    "bfa_dep_kaya",
    "bfa_dep_koupela",
}
# Grandeur : borne haute (W/m²).
_BORNES = {"ghi": 1400.0, "dni": 1400.0, "dhi": 900.0, "ghi_ciel_clair": 1400.0}
_HEURES = 43_824  # 2021-2025 : 1 826 jours
_CAMS = "s.source_id = (SELECT id FROM sources WHERE code = 'cams_radiation')"


def test_series_horaires(db_session: Session) -> None:
    """Une série par pilote et par grandeur, CAMS Radiation, granularité horaire, 2021-2025."""
    lignes = db_session.execute(
        text(
            f"""
            SELECT s.code, s.grandeur_code, l.code AS localite, s.methode_collecte,
                   s.periode_debut::text AS debut, s.periode_fin::text AS fin, s.note_publique
            FROM series_metadonnees s
            JOIN localites l ON l.id = s.localite_id
            WHERE s.granularite = 'horaire' AND {_CAMS}
            """
        )
    ).all()
    assert len(lignes) == 20
    assert {(r.localite, r.grandeur_code) for r in lignes} == {
        (p, g) for p in _PILOTES for g in _BORNES
    }
    for r in lignes:
        assert r.code == f"cams_{r.grandeur_code}_horaire_{r.localite}"
        assert (r.methode_collecte, r.debut, r.fin) == (
            "modele_satellitaire",
            "2021-01-01",
            "2025-12-31",
        ), r.code
        assert "ADR-0023" in r.note_publique, r.code


def test_mesures_completes_et_bornees(db_session: Session) -> None:
    """43 824 heures par série, alignées sur l'heure UTC, confiance B, dans les bornes."""
    lignes = db_session.execute(
        text(
            f"""
            SELECT s.code, s.grandeur_code, count(*) AS n,
                   count(DISTINCT m.instant_mesure) AS heures,
                   min(m.instant_mesure AT TIME ZONE 'UTC')::text AS premier,
                   max(m.instant_mesure AT TIME ZONE 'UTC')::text AS dernier,
                   min(m.valeur) AS vmin, max(m.valeur) AS vmax,
                   bool_and(date_trunc('hour', m.instant_mesure) = m.instant_mesure
                            AND m.niveau_confiance_derive = 'B') AS invariants
            FROM series_metadonnees s
            JOIN mesures_ressource_horaires m ON m.serie_id = s.id
            WHERE s.granularite = 'horaire' AND {_CAMS}
            GROUP BY 1, 2
            """
        )
    ).all()
    assert len(lignes) == 20
    for r in lignes:
        assert r.n == r.heures == _HEURES, r.code
        assert (r.premier, r.dernier) == ("2021-01-01 00:00:00", "2025-12-31 23:00:00")
        assert r.vmin >= 0.0 and r.vmax <= _BORNES[r.grandeur_code], r.code
        assert r.invariants, r.code


def test_convention_debut_d_heure(db_session: Session) -> None:
    """Le centroïde du GHI tombe une demi-heure avant le midi solaire moyen (ADR-0014)."""
    lignes = db_session.execute(
        text(
            f"""
            SELECT l.code,
                   sum(extract(hour FROM m.instant_mesure AT TIME ZONE 'UTC') * m.valeur)
                   / sum(m.valeur) - (12 - l.longitude / 15) AS centroide
            FROM mesures_ressource_horaires m
            JOIN series_metadonnees s ON s.id = m.serie_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.grandeur_code = 'ghi' AND s.granularite = 'horaire' AND {_CAMS}
            GROUP BY l.code, l.longitude
            """
        )
    ).all()
    assert {r.code for r in lignes} == _PILOTES
    for r in lignes:
        assert -0.6 < r.centroide < -0.4, r.code


def test_sommes_horaires_et_journalier(db_session: Session) -> None:
    """Cumulées par jour UTC, les heures redonnent la série journalière CAMS (ADR-0020).

    Le ciel clair se retrouve à l'arrondi près. Tous temps, l'écart moyen reste sous
    0,04 kWh/m²/jour ; il tient aux jours nuageux.
    """
    lignes = db_session.execute(
        text(
            f"""
            WITH jours AS (
                SELECT s.localite_id, s.grandeur_code,
                       (m.instant_mesure AT TIME ZONE 'UTC')::date AS jour,
                       sum(m.valeur) / 1000.0 AS total
                FROM mesures_ressource_horaires m
                JOIN series_metadonnees s ON s.id = m.serie_id
                WHERE s.granularite = 'horaire' AND {_CAMS}
                GROUP BY 1, 2, 3
            ),
            -- Séries journalières denses des seuls points pilotes, lues sans la vue.
            journalier AS (
                SELECT s.localite_id, s.grandeur_code,
                       make_date(d.annee, 1, 1) + (u.rang - 1)::int AS jour,
                       u.e4 / 10000.0 AS valeur
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d
                     ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
                CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
                WHERE s.granularite = 'journalier' AND s.stockage = 'dense' AND {_CAMS}
                  AND s.localite_id IN (SELECT localite_id FROM jours)
                  AND d.annee BETWEEN 2021 AND 2025 AND u.e4 IS NOT NULL
            )
            SELECT j.grandeur_code, count(*) AS jours, avg(abs(j.total - v.valeur)) AS moyen,
                   max(abs(j.total - v.valeur)) AS maximal
            FROM jours j
            JOIN journalier v USING (localite_id, grandeur_code, jour)
            GROUP BY 1
            """
        )
    ).all()
    assert {r.grandeur_code: r.jours for r in lignes} == dict.fromkeys(_BORNES, 5 * 1_826)
    for r in lignes:
        if r.grandeur_code == "ghi_ciel_clair":
            assert r.maximal < 1e-4
        else:
            assert r.moyen < 0.04 and r.maximal < 0.3, r.grandeur_code


def test_ciel_clair_au_dessus_du_tous_temps(db_session: Session) -> None:
    """À chaque heure, le GHI tous temps reste sous le GHI par ciel clair."""
    resultat = db_session.execute(
        text(
            f"""
            SELECT count(h.ghi) AS ghi, count(h.ciel_clair) AS ciel_clair,
                   count(*) FILTER (WHERE h.ghi > h.ciel_clair + 1e-6) AS depassements
            FROM (
                SELECT s.localite_id, m.instant_mesure,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'ghi') AS ghi,
                       max(m.valeur) FILTER (WHERE s.grandeur_code = 'ghi_ciel_clair')
                           AS ciel_clair
                FROM mesures_ressource_horaires m
                JOIN series_metadonnees s ON s.id = m.serie_id
                WHERE s.grandeur_code IN ('ghi', 'ghi_ciel_clair')
                  AND s.granularite = 'horaire' AND {_CAMS}
                GROUP BY 1, 2
            ) h
            """
        )
    ).one()
    assert (resultat.ghi, resultat.ciel_clair, resultat.depassements) == (
        5 * _HEURES,
        5 * _HEURES,
        0,
    )


def test_controle_qualite(db_session: Session) -> None:
    """Toutes les lignes passent le QC v1 ; les drapeaux tiennent au lever et au coucher.

    Les composantes de CAMS se referment : moins de 0,5 % des heures de jour portent un
    drapeau de fermeture. Les DNI « extrêmement rares » tombent tous aux heures où le
    soleil, levé une partie de l'heure, est encore bas en son milieu.
    """
    lignes = db_session.execute(
        text(
            f"""
            SELECT s.grandeur_code,
                   bool_and(m.statut = 'valide_auto'
                            AND m.commentaire_editorial LIKE '[QC v1] valide\\_auto%')
                       AS valides,
                   count(*) FILTER (WHERE m.commentaire_editorial LIKE '%fermeture%')
                       AS fermeture,
                   count(*) FILTER (WHERE m.commentaire_editorial LIKE '%rare%') AS rares,
                   count(*) FILTER (
                       WHERE m.commentaire_editorial LIKE '%rare%'
                         AND extract(hour FROM m.instant_mesure AT TIME ZONE 'UTC')
                             NOT IN (5, 6, 17, 18)
                   ) AS rares_hors_bords,
                   count(*) FILTER (WHERE m.valeur > 0) AS positives
            FROM mesures_ressource_horaires m
            JOIN series_metadonnees s ON s.id = m.serie_id
            WHERE s.granularite = 'horaire' AND {_CAMS}
            GROUP BY 1
            """
        )
    ).all()
    par_grandeur = {r.grandeur_code: r for r in lignes}
    assert all(r.valides for r in lignes)
    assert par_grandeur["ghi_ciel_clair"].fermeture == par_grandeur["ghi_ciel_clair"].rares == 0
    assert par_grandeur["ghi"].fermeture < 0.005 * par_grandeur["ghi"].positives
    assert par_grandeur["dni"].rares > 0
    assert sum(r.rares_hors_bords for r in lignes) == 0


def test_fiche_de_la_source(db_session: Session) -> None:
    """La fiche de ``cams_radiation`` ajoute l'horaire aux points pilotes."""
    fiche = db_session.execute(
        text(
            "SELECT date_consultation::text AS consultation, notes, "
            "metadonnees ->> 'pas_temporel_ingere' AS pas FROM sources "
            "WHERE code = 'cams_radiation'"
        )
    ).one()
    assert fiche.consultation == "2026-10-28"
    assert "ADR-0023" in fiche.notes and "cinq points pilotes" in fiche.notes
    assert "1hour (ADR-0023)" in fiche.pas


def test_capsule_retient_nasa_power(db_session: Session) -> None:
    """À période égale, la séquence horaire de la capsule vient de la source du relais.

    La capsule demande aussi une climatologie mensuelle 1991-2020, que le Burkina Faso
    n'a pas : seule la sélection de la séquence horaire est vérifiée ici.
    """
    localite_id = db_session.execute(
        text("SELECT id FROM localites WHERE code = 'bfa_com_ouagadougou'")
    ).scalar_one()
    source = SourceCore(session=db_session, annee_min=2024, annee_max=2024)
    _, periode, provenance = source._sequence_horaire(localite_id)
    assert provenance["code"] == "nasa_power_ghi_horaire_bfa_com_ouagadougou"
    assert (provenance["source"], periode) == ("nasa_power", {"debut": "2024-01", "fin": "2024-12"})


def test_defaut_source_du_relais(db_session: Session) -> None:
    """Sans source, la série de NASA POWER l'emporte, quel que soit l'ordre d'insertion.

    Les sources des deux séries GHI de Dori sont échangées dans la transaction du test :
    la série étiquetée NASA POWER porte alors l'id le plus grand, et reste servie. La
    série NASA POWER de Dori porte sa maille (ADR-0026) : les séries qui la lisent en
    sont d'abord détachées, une porteuse lue ne changeant pas de famille.
    """
    ids = {
        row.source: row.id
        for row in db_session.execute(
            text(
                "SELECT so.code AS source, s.id FROM series_metadonnees s "
                "JOIN sources so ON so.id = s.source_id "
                "JOIN localites l ON l.id = s.localite_id "
                "WHERE l.code = 'bfa_dep_dori' AND s.grandeur_code = 'ghi' "
                "AND s.granularite = 'horaire'"
            )
        ).all()
    }
    assert ids["nasa_power"] < ids["cams_radiation"]
    db_session.execute(
        text(
            "UPDATE series_metadonnees SET serie_porteuse_id = NULL WHERE serie_porteuse_id = :id"
        ),
        {"id": ids["nasa_power"]},
    )
    # Échange en trois temps, par une source de passage, sous la contrainte d'unicité.
    for serie_id, source_id in (
        (ids["nasa_power"], 10),
        (ids["cams_radiation"], 1),
        (ids["nasa_power"], 13),
    ):
        db_session.execute(
            text("UPDATE series_metadonnees SET source_id = :source WHERE id = :id"),
            {"source": source_id, "id": serie_id},
        )
    serie = _chercher_serie_horaire_stockee(db_session, "bfa_dep_dori", "ghi")
    assert serie is not None
    assert (serie[0], serie[3]) == (ids["cams_radiation"], "nasa_power")
