"""Tests d'intégration des grandeurs dérivées stockées (migration 0009, ADR-0012).

Vérifie le référentiel, les séries ``kuma_calculs``, les comptes et la fidélité
des valeurs aux séries mensuelles brutes : écarts relatifs inter-sources et
fraction diffuse NASA POWER.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.grandeurs_derivees_bfa import ECARTS, EcartInterSource

pytestmark = pytest.mark.integration


def test_referentiel(db_session: Session) -> None:
    """Sept écarts F1 stockés en pourcent (ids 35 à 41), fraction diffuse inchangée."""
    lignes = db_session.execute(
        text(
            """
            SELECT g.id, g.code, g.famille, g.strategie_calcul, u.code AS unite
            FROM grandeurs_referentiel g JOIN unites u ON u.id = g.unite_id
            WHERE g.id BETWEEN 35 AND 41 OR g.code = 'fraction_diffuse'
            """
        )
    ).all()
    vues = {r.id: (r.code, r.famille, r.strategie_calcul, r.unite) for r in lignes}
    attendu = {e.grandeur_id: (e.grandeur_code, "F1", "stockee", "pourcent") for e in ECARTS}
    attendu[3] = ("fraction_diffuse", "F1", "stockee", "sans_unite")
    assert vues == attendu


def test_series_calculees(db_session: Session) -> None:
    """398 séries kuma_calculs par grandeur dérivée, sans granularité, aux bonnes périodes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, s.granularite, count(*) AS n
            FROM series_metadonnees s JOIN sources so ON so.id = s.source_id
            WHERE so.code = 'kuma_calculs'
            GROUP BY 1, 2, 3, 4, 5
            """
        )
    ).all()
    vues = {
        r.grandeur_code: (r.debut, r.fin, r.methode_collecte, r.granularite, r.n) for r in lignes
    }
    attendu = {
        e.grandeur_code: (
            f"{e.annee_debut}-01-01",
            f"{e.annee_fin}-12-31",
            "calcul_derive",
            None,
            398,
        )
        for e in ECARTS
    }
    attendu["fraction_diffuse"] = ("2001-01-01", "2025-12-31", "calcul_derive", None, 398)
    assert vues == attendu


def test_comptes_et_invariants(db_session: Session) -> None:
    """Une ligne par mois commun et par localité ; confiance B, statut brut, version 1."""
    lignes = db_session.execute(
        text(
            """
            SELECT grandeur_code, periode_type, count(*) AS n,
                   bool_and(niveau_confiance_derive = 'B' AND statut = 'brut'
                            AND version_formule = 1) AS invariants
            FROM grandeurs_metier GROUP BY 1, 2
            """
        )
    ).all()
    vues = {(r.grandeur_code, r.periode_type): r.n for r in lignes}
    attendu = {(e.grandeur_code, "mensuel"): 398 * e.nb_mois for e in ECARTS}
    attendu[("fraction_diffuse", "mensuel")] = 398 * 300
    attendu[("fraction_diffuse", "annuel")] = 398 * 25
    assert vues == attendu
    assert all(r.invariants for r in lignes)


def test_rattachement_aux_series(db_session: Session) -> None:
    """Chaque valeur pointe la série kuma_calculs de sa localité et de sa grandeur."""
    orphelines = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM grandeurs_metier gm
            JOIN series_metadonnees s ON s.id = gm.series_metadonnees_id
            JOIN localites l ON l.id = gm.localite_id
            WHERE s.localite_id <> gm.localite_id
               OR s.grandeur_code <> gm.grandeur_code
               OR s.source_id <> 10
               OR right(s.code, length(l.code) + 1) <> '_' || l.code
            """
        )
    ).scalar_one()
    assert orphelines == 0


@pytest.mark.parametrize("ecart", ECARTS, ids=lambda e: e.grandeur_code)
def test_ecarts_fideles_aux_mesures(db_session: Session, ecart: EcartInterSource) -> None:
    """Chaque écart vaut (x - nasa) / nasa * 100, recalculé depuis les mesures brutes."""
    resultat = db_session.execute(
        text(
            """
            SELECT count(*) AS n,
                   max(abs(gm.valeur - (mx.valeur - mn.valeur) / mn.valeur * 100)) AS ecart
            FROM grandeurs_metier gm
            JOIN series_metadonnees sx
              ON sx.localite_id = gm.localite_id AND sx.grandeur_code = :brute
             AND sx.granularite = 'mensuel'
             AND sx.source_id = (SELECT id FROM sources WHERE code = :source)
            JOIN mesures_ressource_mensuelles mx
              ON mx.serie_id = sx.id AND mx.annee = gm.annee_debut AND mx.mois = gm.mois
            JOIN series_metadonnees sn
              ON sn.localite_id = gm.localite_id AND sn.grandeur_code = :brute
             AND sn.granularite = 'mensuel' AND sn.source_id = 1
            JOIN mesures_ressource_mensuelles mn
              ON mn.serie_id = sn.id AND mn.annee = gm.annee_debut AND mn.mois = gm.mois
            WHERE gm.grandeur_code = :code
            """
        ),
        {"brute": ecart.grandeur_brute, "source": ecart.source_code, "code": ecart.grandeur_code},
    ).one()
    assert resultat.n == 398 * ecart.nb_mois
    assert resultat.ecart < 1e-9


def test_fraction_diffuse(db_session: Session) -> None:
    """Fraction diffuse dans [0, 1], mensuelle = DHI / GHI, annuelle pondérée par les jours."""
    resultat = db_session.execute(
        text(
            """
            WITH couples AS (
                SELECT d.localite_id, md.annee, md.mois, md.valeur AS dhi, mg.valeur AS ghi,
                       extract(day FROM make_date(md.annee, md.mois, 1)
                                        + interval '1 month - 1 day') AS n_jours
                FROM series_metadonnees d
                JOIN mesures_ressource_mensuelles md ON md.serie_id = d.id
                JOIN series_metadonnees g
                  ON g.localite_id = d.localite_id AND g.grandeur_code = 'ghi'
                 AND g.granularite = 'mensuel' AND g.source_id = 1
                JOIN mesures_ressource_mensuelles mg
                  ON mg.serie_id = g.id AND mg.annee = md.annee AND mg.mois = md.mois
                WHERE d.grandeur_code = 'dhi' AND d.granularite = 'mensuel' AND d.source_id = 1
            ),
            annuel AS (
                SELECT localite_id, annee, sum(dhi * n_jours) / sum(ghi * n_jours) AS fd
                FROM couples GROUP BY 1, 2
            )
            SELECT
                (SELECT max(abs(gm.valeur - c.dhi / c.ghi))
                 FROM grandeurs_metier gm JOIN couples c
                   ON c.localite_id = gm.localite_id AND c.annee = gm.annee_debut
                  AND c.mois = gm.mois
                 WHERE gm.grandeur_code = 'fraction_diffuse' AND gm.periode_type = 'mensuel')
                    AS ecart_mensuel,
                (SELECT max(abs(gm.valeur - a.fd))
                 FROM grandeurs_metier gm JOIN annuel a
                   ON a.localite_id = gm.localite_id AND a.annee = gm.annee_debut
                 WHERE gm.grandeur_code = 'fraction_diffuse' AND gm.periode_type = 'annuel')
                    AS ecart_annuel,
                (SELECT count(*) FROM grandeurs_metier
                 WHERE grandeur_code = 'fraction_diffuse' AND NOT valeur BETWEEN 0 AND 1)
                    AS hors_domaine
            """
        )
    ).one()
    assert resultat.ecart_mensuel < 1e-12
    assert resultat.ecart_annuel < 1e-9
    assert resultat.hors_domaine == 0
