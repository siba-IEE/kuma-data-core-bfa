"""Tests d'intégration de la dégénérescence de pixel (migration 0014, ADR-0016).

Une ligne par localité ; deux localités sont jumelles quand leurs séries
mensuelles GHI NASA POWER sont identiques (même maille CERES de 1°).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_une_ligne_par_localite(db_session: Session) -> None:
    """398 lignes statiques, confiance B, rattachées à la série GHI NASA POWER mensuelle."""
    lignes = db_session.execute(
        text(
            """
            SELECT count(*) AS n, count(DISTINCT gm.localite_id) AS localites,
                   bool_and(gm.periode_type = 'statique' AND gm.niveau_confiance_derive = 'B'
                            AND s.grandeur_code = 'ghi' AND s.granularite = 'mensuel'
                            AND so.code = 'nasa_power' AND s.localite_id = gm.localite_id)
                       AS rattachees
            FROM grandeurs_metier gm
            JOIN series_metadonnees s ON s.id = gm.series_metadonnees_id
            JOIN sources so ON so.id = s.source_id
            WHERE gm.grandeur_code = 'degenerescence_pixel'
            """
        )
    ).one()
    assert (lignes.n, lignes.localites) == (398, 398)
    assert lignes.rattachees


def test_jumeaux_de_meme_serie(db_session: Session) -> None:
    """Le compte de jumeaux est la taille du groupe de séries identiques, moins un.

    33 mailles ; deux localités seulement sont seules dans la leur ; le Kadiogo
    partage la sienne avec Ouagadougou.
    """
    lignes = db_session.execute(
        text(
            """
            WITH empreintes AS (
                SELECT s.localite_id,
                       md5(string_agg(m.valeur::text, ',' ORDER BY m.annee, m.mois)) AS e
                FROM series_metadonnees s
                JOIN sources so ON so.id = s.source_id
                JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
                WHERE so.code = 'nasa_power' AND s.grandeur_code = 'ghi'
                  AND s.granularite = 'mensuel' AND m.valide_au IS NULL
                GROUP BY s.localite_id
            ),
            tailles AS (SELECT e, count(*) AS taille FROM empreintes GROUP BY e)
            SELECT l.code, gm.valeur, t.taille, e.e
            FROM empreintes e
            JOIN tailles t USING (e)
            JOIN localites l ON l.id = e.localite_id
            JOIN grandeurs_metier gm
              ON gm.localite_id = e.localite_id AND gm.grandeur_code = 'degenerescence_pixel'
            """
        )
    ).all()
    assert len({r.e for r in lignes}) == 33
    assert all(r.valeur == r.taille - 1 for r in lignes)
    assert sum(1 for r in lignes if r.valeur == 0) == 2
    maille = {r.code: r.e for r in lignes}
    assert maille["bfa_prov_kadiogo"] == maille["bfa_com_ouagadougou"]


def test_commentaire_liste_les_jumeaux(db_session: Session) -> None:
    """Le commentaire nomme autant de jumeaux que le compte."""
    lignes = db_session.execute(
        text(
            """
            SELECT gm.valeur, gm.commentaire_editorial AS note
            FROM grandeurs_metier gm
            WHERE gm.grandeur_code = 'degenerescence_pixel'
            """
        )
    ).all()
    for r in lignes:
        if r.valeur == 0:
            assert r.note.startswith("Seule localité du référentiel")
        else:
            liste = r.note.split(" : ", 1)[1].split(". ", 1)[0]
            assert len(liste.split(", ")) == r.valeur
