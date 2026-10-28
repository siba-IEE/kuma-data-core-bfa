"""Tests d'intégration du rayonnement journalier SARAH-3 (migration 0021).

Vérifie les 1 194 séries denses des 398 localités (ADR-0022), les jours sans
valeur, l'accord avec les séries mensuelles PVGIS, la fermeture du direct, les
notes publiques et la fiche de la source.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : porteuses (les localités d'un même pixel partagent leur série).
_PORTEUSES = {"ghi": 393, "dni": 395, "dhi": 393}
# Jours où SARAH-3 laisse d'affilée plus de la moitié du ciel clair sans valeur : les
# mêmes à toutes les localités.
_SANS_VALEUR = {
    "2005-04-18",
    "2008-01-22",
    "2008-01-23",
    "2008-03-01",
    "2008-03-06",
    "2008-05-17",
    "2008-05-18",
    "2009-04-18",
    "2009-04-19",
    "2009-08-15",
    "2009-08-16",
    "2014-12-02",
    "2016-10-16",
    "2016-10-17",
}
# Mois que les heures non servies abaissent de 4 % au moins dans le mensuel PVGIS.
_MOIS_SOUS_ESTIMES = (
    "((2008, 1), (2008, 3), (2008, 5), (2009, 1), (2009, 4), (2009, 8), (2014, 12), (2016, 10))"
)


def test_series_des_398_localites(db_session: Session) -> None:
    """398 séries par grandeur, denses, sur 2005-2023, source ``sarah3_monthly``."""
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
            WHERE s.source_id = 11 AND s.granularite = 'journalier'
            GROUP BY 1, 2, 3, 4
            """
        )
    ).all()
    assert {r.grandeur_code: r.porteuses for r in lignes} == _PORTEUSES
    for r in lignes:
        assert (r.debut, r.fin, r.methode_collecte, r.provinces, r.communes, r.denses) == (
            "2005-01-01",
            "2023-12-31",
            "modele_satellitaire",
            47,
            351,
            True,
        ), r.grandeur_code


def test_jours_sans_valeur_et_bornes(db_session: Session) -> None:
    """Les jours sans valeur sont les mêmes à toutes les localités ; bornes tenues."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code,
                   array_agg(DISTINCT (make_date(d.annee, 1, 1) + (u.rang - 1)::int)::text)
                       FILTER (WHERE u.e4 IS NULL) AS absents,
                   count(*) FILTER (WHERE u.e4 IS NULL) AS nb_absents,
                   count(DISTINCT s.id) AS porteuses,
                   count(u.e4) AS valeurs, min(u.e4) / 10000.0 AS vmin,
                   max(u.e4) / 10000.0 AS vmax
            FROM series_metadonnees s
            JOIN mesures_journalieres_denses d ON d.serie_id = s.id
            CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
            WHERE s.source_id = 11 AND s.granularite = 'journalier'
              AND s.serie_porteuse_id IS NULL
            GROUP BY 1
            """
        )
    ).all()
    assert sum(r.valeurs for r in lignes) == 8_178_425
    for r in lignes:
        assert set(r.absents) == _SANS_VALEUR, r.grandeur_code
        # Aucune date n'est sans valeur à une partie seulement des localités.
        assert r.nb_absents == len(_SANS_VALEUR) * r.porteuses, r.grandeur_code
        assert r.vmin >= 0.0 and r.vmax <= {"ghi": 9.0, "dni": 11.0, "dhi": 6.5}[r.grandeur_code]
        if r.grandeur_code != "dni":
            assert r.vmin > 0.0, r.grandeur_code


def test_accord_avec_le_mensuel(db_session: Session) -> None:
    """La moyenne des jours redonne le mensuel PVGIS, complétée des heures non servies.

    Un mois sans heure manquante redonne le mensuel à 1e-4 près : aux trois localités,
    638 mois y restent, les 636 sans heure manquante et deux à la perte négligeable. PVGIS
    compte nulles les heures que SARAH-3 ne sert pas : aux trois localités, la moyenne
    des jours ne passe pas sous le mensuel de plus de 1e-4, le dépasse de moins de 3,5 %
    hors des mois sous-estimés et de 4 % au moins dans ces mois.
    """
    rapports = db_session.execute(
        text(
            f"""
            WITH jours AS (
                SELECT l.code AS localite, s.grandeur_code, d.annee,
                       extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int) AS mois,
                       u.e4
                FROM series_metadonnees s
                JOIN localites l ON l.id = s.localite_id
                JOIN mesures_journalieres_denses d
                     ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
                CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
                WHERE s.source_id = 11 AND s.granularite = 'journalier'
                  AND s.grandeur_code IN ('ghi', 'dni')
                  AND l.code IN ('bfa_com_ouagadougou', 'bfa_dep_dori', 'bfa_dep_gaoua')
            ),
            moyennes AS (
                SELECT localite, grandeur_code, annee, mois, avg(e4) / 10000.0 AS moyenne
                FROM jours GROUP BY 1, 2, 3, 4
            )
            SELECT (m.annee, m.mois) IN {_MOIS_SOUS_ESTIMES} AS sous_estime,
                   count(*) AS mois,
                   count(*) FILTER (WHERE abs(m.moyenne / r.valeur - 1) <= 1e-4) AS egaux,
                   min(m.moyenne / r.valeur) AS rmin,
                   avg(m.moyenne / r.valeur) AS rmoy, max(m.moyenne / r.valeur) AS rmax
            FROM moyennes m
            JOIN series_metadonnees sm
                 ON sm.code = 'sarah3_' || m.grandeur_code || '_mensuel_' || m.localite
            JOIN mesures_ressource_mensuelles r
                 ON r.serie_id = sm.id AND r.annee = m.annee AND r.mois = m.mois
                AND r.valide_au IS NULL
            GROUP BY 1
            """
        )
    ).all()
    par_cas = {r.sous_estime: r for r in rapports}
    assert par_cas[False].mois + par_cas[True].mois == 3 * 2 * 228
    assert par_cas[False].egaux == 638
    assert par_cas[False].rmin > 0.9999 and par_cas[False].rmoy < 1.005
    assert par_cas[False].rmax < 1.035
    assert par_cas[True].rmin > 1.04


def test_direct_horizontal_sous_le_dni(db_session: Session) -> None:
    """Chaque jour, le direct horizontal (GHI moins DHI) reste sous le DNI."""
    resultat = db_session.execute(
        text(
            """
            WITH annees AS (
                SELECT s.localite_id, d.annee,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'ghi') AS ghi,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'dni') AS dni,
                       max(d.valeurs_e4) FILTER (WHERE s.grandeur_code = 'dhi') AS dhi
                FROM series_metadonnees s
                JOIN mesures_journalieres_denses d
                     ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
                WHERE s.source_id = 11 AND s.granularite = 'journalier'
                GROUP BY 1, 2
            )
            SELECT count(u.ghi) AS jours,
                   count(*) FILTER (WHERE u.ghi - u.dhi > u.dni + 1) AS depassements
            FROM annees a
            CROSS JOIN LATERAL unnest(a.ghi, a.dni, a.dhi) AS u(ghi, dni, dhi)
            """
        )
    ).one()
    assert (resultat.jours, resultat.depassements) == (398 * (6_939 - len(_SANS_VALEUR)), 0)


def test_notes_publiques(db_session: Session) -> None:
    """Notes journalières, mensuelles et d'écarts : heures complétées, jours sans valeur."""
    journalieres = db_session.execute(
        text(
            """
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE note_publique LIKE '%valeur instantanée datée de hh:07%'
                                      AND note_publique LIKE '%au prorata du ciel clair%'
                                      AND note_publique LIKE '%une heure sur deux%'
                                      AND note_publique LIKE '%climatologie d''aérosols (MACC)%'
                                      AND note_publique LIKE '%Jour compté en temps universel%'
                                      AND note_publique LIKE '%stockage dense (ADR-0017)%'
                                      AND note_publique LIKE '%Sans valeur (heures non servies%'
                                      AND note_publique LIKE '%: 18 avril 2005, 22 janvier 2008%'
                                      AND note_publique LIKE '%18 mai 2008, 18 avril 2009%'
                                      AND note_publique LIKE '%, 16 octobre 2016, 17 octobre 2016.')
                       AS completes
            FROM series_metadonnees
            WHERE source_id = 11 AND granularite = 'journalier'
            """
        )
    ).one()
    # Les jours du 2 au 11 janvier 2009, servis une heure sur deux, ont une valeur.
    assert (journalieres.n, journalieres.completes) == (1_194, 1_194)
    mensuelles = db_session.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE note_publique LIKE '%août 2009 et janvier 2008%'
                                      AND note_publique LIKE '%décembre 2014 (4 %)%'
                                      AND note_publique LIKE '%ADR-0022%') AS a_jour,
                   count(*) FILTER (WHERE note_publique LIKE '%ou partielles dans la source%')
                       AS anciennes
            FROM series_metadonnees
            WHERE source_id = 11 AND granularite = 'mensuel'
            """
        )
    ).one()
    assert (mensuelles.a_jour, mensuelles.anciennes) == (796, 0)
    ecarts = db_session.execute(
        text(
            r"""
            SELECT count(*) FILTER (WHERE note_publique LIKE '%Huit mois SARAH-3%'
                                      AND note_publique LIKE '%décembre 2014%') AS a_jour,
                   count(*) FILTER (WHERE note_publique LIKE '%Six mois SARAH-3%') AS anciennes
            FROM series_metadonnees
            WHERE source_id = 10 AND code LIKE 'ecart\_%\_sarah3\_nasa\_bfa\_%'
            """
        )
    ).one()
    assert (ecarts.a_jour, ecarts.anciennes) == (796, 0)


def test_fiche_de_la_source(db_session: Session) -> None:
    """La fiche de ``sarah3_monthly`` est celle du Burkina Faso."""
    fiche = db_session.execute(
        text(
            "SELECT date_consultation::text AS consultation, url, titre, organisation, notes "
            "FROM sources WHERE id = 11"
        )
    ).one()
    assert fiche.consultation == "2026-10-27"
    assert fiche.url == "https://re.jrc.ec.europa.eu/api/v5_3/"
    assert fiche.titre.startswith("SARAH-3 : Surface Solar Radiation Data Set")
    assert "Commission européenne" in fiche.organisation
    assert "Au Burkina Faso" in fiche.notes and "ADR-0022" in fiche.notes
    assert "climatologie d'aérosols (MACC)" in fiche.notes
