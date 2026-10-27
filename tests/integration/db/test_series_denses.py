"""Tests d'intégration du stockage dense (migrations 0015 et 0016, ADR-0017).

Vérifie les 2 106 séries journalières NASA POWER des 351 communes, le partage
des mesures entre communes d'une même maille (séries porteuses), les lignes
annuelles, la vue ``v_mesures_journalieres``, les garde-fous en base et
l'accord avec les séries mensuelles des communes et versionnées des provinces.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# Grandeur : (méthode, mailles distinctes, borne basse incluse ou None, borne haute).
_GRANDEURS = {
    "ghi": ("modele_satellitaire", 33, None, 9.0),
    "dni": ("modele_satellitaire", 33, None, 11.0),
    "dhi": ("modele_satellitaire", 33, None, 6.5),
    "t2m": ("reanalyse", 82, 0.0, 50.0),
    "rh2m": ("reanalyse", 82, 0.0, 100.0),
    "precipitation": ("reanalyse", 82, 0.0, 500.0),
}
_PLUIE_ECARTEE = {
    "nasa_power_precipitation_journalier_bfa_dep_sideradougou",
    "nasa_power_precipitation_journalier_bfa_dep_tiefora",
}


def _ids(session: Session, codes: list[str]) -> dict[str, int]:
    lignes = session.execute(
        text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"), {"c": codes}
    ).all()
    return {r.code: int(r.id) for r in lignes}


def test_series_des_communes(db_session: Session) -> None:
    """351 séries par grandeur, denses, 2005-2025, une porteuse par maille distincte."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.grandeur_code, s.periode_debut::text AS debut, s.periode_fin::text AS fin,
                   s.methode_collecte, l.type_localite, so.code AS source,
                   count(*) AS n, count(*) FILTER (WHERE s.serie_porteuse_id IS NULL) AS porteuses
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            WHERE s.stockage = 'dense'
            GROUP BY 1, 2, 3, 4, 5, 6
            """
        )
    ).all()
    assert {r.grandeur_code for r in lignes} == set(_GRANDEURS)
    for r in lignes:
        methode, mailles, _, _ = _GRANDEURS[r.grandeur_code]
        assert (r.debut, r.fin, r.n, r.porteuses) == ("2005-01-01", "2025-12-31", 351, mailles)
        assert (r.methode_collecte, r.type_localite, r.source) == (
            methode,
            "commune",
            "nasa_power",
        )


def test_porteuses_coherentes(db_session: Session) -> None:
    """Porteuse de même famille, sans relais ; seules les porteuses ont des lignes."""
    incoherentes = db_session.execute(
        text(
            """
            SELECT count(*) FROM series_metadonnees s
            JOIN series_metadonnees p ON p.id = s.serie_porteuse_id
            JOIN localites ls ON ls.id = s.localite_id
            JOIN localites lp ON lp.id = p.localite_id
            WHERE p.serie_porteuse_id IS NOT NULL OR p.stockage <> 'dense'
               OR (p.grandeur_code, p.source_id, p.periode_debut, p.periode_fin)
                  IS DISTINCT FROM (s.grandeur_code, s.source_id, s.periode_debut, s.periode_fin)
               OR lp.code >= ls.code
            """
        )
    ).scalar_one()
    assert incoherentes == 0
    sans_lignes = db_session.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE s.serie_porteuse_id IS NULL AND d.n IS NULL) AS vides,
                   count(*) FILTER (WHERE s.serie_porteuse_id IS NOT NULL AND d.n IS NOT NULL)
                       AS doublons
            FROM series_metadonnees s
            LEFT JOIN (
                SELECT serie_id, count(*) AS n FROM mesures_journalieres_denses GROUP BY serie_id
            ) d ON d.serie_id = s.id
            WHERE s.stockage = 'dense'
            """
        )
    ).one()
    assert (sans_lignes.vides, sans_lignes.doublons) == (0, 0)


def test_lignes_annuelles_completes_et_bornees(db_session: Session) -> None:
    """21 années par porteuse, tous les jours sauf la pluie écartée ; confiance B, bornes."""
    lignes = db_session.execute(
        text(
            """
            SELECT s.code, s.grandeur_code, count(DISTINCT d.annee) AS annees,
                   min(d.annee) AS premiere, max(d.annee) AS derniere,
                   count(j.e4) AS valeurs, count(*) - count(j.e4) AS absentes,
                   min(j.e4) / 10000.0 AS vmin, max(j.e4) / 10000.0 AS vmax,
                   bool_and(d.niveau_confiance_derive = 'B') AS confiance_b
            FROM mesures_journalieres_denses d
            JOIN series_metadonnees s ON s.id = d.serie_id
            CROSS JOIN LATERAL unnest(d.valeurs_e4) AS j(e4)
            GROUP BY s.code, s.grandeur_code
            """
        )
    ).all()
    assert len(lignes) == 345
    assert sum(r.valeurs for r in lignes) == 2_646_149
    for r in lignes:
        _, _, basse, haute = _GRANDEURS[r.grandeur_code]
        ecartee = int(r.code in _PLUIE_ECARTEE)
        assert (r.annees, r.premiere, r.derniere) == (21, 2005, 2025), r.code
        assert (r.valeurs, r.absentes) == (7_670 - ecartee, ecartee), r.code
        assert (r.vmin > 0.0 if basse is None else r.vmin >= basse) and r.vmax <= haute, r.code
        assert r.confiance_b, r.code


def test_vue_rend_ses_mesures_a_chaque_serie(db_session: Session) -> None:
    """Une série qui lit une porteuse reçoit exactement les mesures de celle-ci, en brut."""
    prefixe = "nasa_power_precipitation_journalier_bfa_dep_"
    ids = _ids(db_session, [prefixe + c for c in ("sideradougou", "tiefora", "banfora", "fo")])
    lignes = db_session.execute(
        text(
            """
            SELECT serie_id, count(*) AS n, sum(valeur) AS total,
                   min(instant_mesure) AS premier, max(instant_mesure) AS dernier,
                   bool_and(statut = 'brut' AND niveau_confiance_override IS NULL) AS brut,
                   bool_or(instant_mesure = DATE '2025-12-02') AS avec_2_decembre
            FROM v_mesures_journalieres
            WHERE serie_id = ANY(:ids)
            GROUP BY serie_id
            """
        ),
        {"ids": list(ids.values())},
    ).all()
    par_code = {code: next(r for r in lignes if r.serie_id == i) for code, i in ids.items()}
    tiefora = par_code[prefixe + "tiefora"]
    sideradougou = par_code[prefixe + "sideradougou"]
    assert (tiefora.n, tiefora.avec_2_decembre) == (7_669, False)
    assert (sideradougou.n, sideradougou.total) == (tiefora.n, tiefora.total)
    assert (par_code[prefixe + "banfora"].n, par_code[prefixe + "fo"].n) == (7_670, 7_670)
    assert all((r.premier, r.dernier) == (date(2005, 1, 1), date(2025, 12, 31)) for r in lignes)
    assert all(r.brut for r in lignes)


def test_bissextiles(db_session: Session) -> None:
    """Le 29 février des années bissextiles est rendu, et le 1er mars suit le 28 février sinon."""
    (serie,) = _ids(db_session, ["nasa_power_ghi_journalier_bfa_dep_fo"]).values()
    jours = db_session.execute(
        text(
            """
            SELECT array_agg(instant_mesure ORDER BY instant_mesure) FROM v_mesures_journalieres
            WHERE serie_id = :s AND extract(month FROM instant_mesure) = 2
              AND extract(day FROM instant_mesure) = 29
            """
        ),
        {"s": serie},
    ).scalar_one()
    assert jours == [date(a, 2, 29) for a in (2008, 2012, 2016, 2020, 2024)]


@pytest.mark.parametrize("grandeur", sorted(_GRANDEURS))
def test_accord_avec_la_province_au_meme_point(db_session: Session, grandeur: str) -> None:
    """Banfora et la province de la Comoé ont les mêmes coordonnées : mêmes valeurs depuis 2005."""
    ids = _ids(
        db_session,
        [
            f"nasa_power_{grandeur}_journalier_bfa_prov_comoe",
            f"nasa_power_{grandeur}_journalier_bfa_dep_banfora",
        ],
    )
    accord = db_session.execute(
        text(
            """
            WITH p AS (SELECT instant_mesure AS jour, valeur FROM v_mesures_journalieres
                       WHERE serie_id = :province AND instant_mesure >= DATE '2005-01-01'),
                 c AS (SELECT instant_mesure AS jour, valeur FROM v_mesures_journalieres
                       WHERE serie_id = :commune)
            SELECT count(*) AS n, count(*) FILTER (WHERE p.valeur = c.valeur) AS egales
            FROM p JOIN c USING (jour)
            """
        ),
        {
            "province": ids[f"nasa_power_{grandeur}_journalier_bfa_prov_comoe"],
            "commune": ids[f"nasa_power_{grandeur}_journalier_bfa_dep_banfora"],
        },
    ).one()
    assert (accord.n, accord.egales) == (7_670, 7_670)


@pytest.mark.parametrize("grandeur", ["ghi", "dni", "dhi"])
def test_accord_avec_le_mensuel_des_communes(db_session: Session, grandeur: str) -> None:
    """La moyenne des jours d'un mois redonne la série mensuelle NASA POWER de la porteuse."""
    ecart = db_session.execute(
        text(
            """
            WITH jours AS (
                SELECT p.localite_id, d.annee,
                       extract(month FROM make_date(d.annee, 1, 1) + (u.rang - 1)::int)::int
                           AS mois,
                       avg(u.e4 / 10000.0) AS moyenne
                FROM series_metadonnees p
                JOIN mesures_journalieres_denses d ON d.serie_id = p.id
                CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS u(e4, rang)
                WHERE p.grandeur_code = :g AND p.stockage = 'dense'
                GROUP BY 1, 2, 3
            )
            SELECT count(*) AS n, max(abs(jours.moyenne - mm.valeur)) AS ecart
            FROM jours
            JOIN series_metadonnees s
              ON s.localite_id = jours.localite_id AND s.grandeur_code = :g
             AND s.granularite = 'mensuel' AND s.source_id = 1
            JOIN mesures_ressource_mensuelles mm
              ON mm.serie_id = s.id AND mm.annee = jours.annee AND mm.mois = jours.mois
             AND mm.valide_au IS NULL
            """
        ),
        {"g": grandeur},
    ).one()
    assert ecart.n == 33 * 21 * 12
    assert ecart.ecart < 0.0005


def test_notes_publiques(db_session: Session) -> None:
    """La note dit le partage de maille, la valeur écartée, décembre 2025 et le record."""
    notes = dict(
        db_session.execute(
            text(
                """
                SELECT code, note_publique FROM series_metadonnees
                WHERE code IN (
                    'nasa_power_precipitation_journalier_bfa_dep_tiefora',
                    'nasa_power_precipitation_journalier_bfa_dep_banfora',
                    'nasa_power_precipitation_journalier_bfa_dep_kpuere',
                    'nasa_power_ghi_journalier_bfa_dep_fo'
                )
                """
            )
        ).all()
    )
    tiefora = notes["nasa_power_precipitation_journalier_bfa_dep_tiefora"]
    assert "identique pour les 2 communes de la même maille" in tiefora
    assert (
        "Le 2 décembre 2025, la source sert 514,64 mm, au-delà de la borne de plausibilité du "
        "contrat (500 mm) : valeur écartée, jour sans valeur." in tiefora
    )
    assert "275,2 mm le 15 juin 2025" in tiefora
    assert (
        "514,6 mm le 2 (écartée), 6,7 mm le 3, 13,3 mm le 14 ; autres valeurs suspectes, "
        "gardées telles que servies." in tiefora
    )
    banfora = notes["nasa_power_precipitation_journalier_bfa_dep_banfora"]
    assert "Décembre 2025 sort de l'enveloppe 2005-2024" in banfora
    assert "321,8 mm le 2" in banfora
    assert "345,4 mm le 12 août 2022" in notes["nasa_power_precipitation_journalier_bfa_dep_kpuere"]
    ghi = notes["nasa_power_ghi_journalier_bfa_dep_fo"]
    assert ghi.startswith("Rayonnement global horizontal (GHI) : série journalière NASA POWER")
    assert "stockage dense (ADR-0017)" in ghi and "ne ferment pas" in ghi
    assert all("partir de 2015" in n for c, n in notes.items() if "precipitation" in c)
    signalees = db_session.execute(
        text(
            """
            SELECT stockage, count(*) FROM series_metadonnees
            WHERE grandeur_code = 'precipitation' AND note_publique LIKE '%Décembre 2025 sort%'
            GROUP BY stockage
            """
        )
    ).all()
    assert dict(signalees) == {"dense": 125, "versionne": 13}


def test_garde_fous_en_base(db_session: Session) -> None:
    """Pas de mise à jour de ligne dense, ni de lignes ou de porteuse hors des règles."""
    ids = _ids(
        db_session,
        [
            "nasa_power_ghi_journalier_bfa_dep_banfora",
            "nasa_power_ghi_journalier_bfa_dep_tiefora",
            "nasa_power_ghi_journalier_bfa_dep_fo",
            "nasa_power_ghi_journalier_bfa_prov_comoe",
            "nasa_power_t2m_journalier_bfa_dep_banfora",
        ],
    )
    banfora = ids["nasa_power_ghi_journalier_bfa_dep_banfora"]
    tiefora = ids["nasa_power_ghi_journalier_bfa_dep_tiefora"]
    fo = ids["nasa_power_ghi_journalier_bfa_dep_fo"]
    porteuse_de_tiefora = "UPDATE series_metadonnees SET serie_porteuse_id = :b WHERE id = :a"
    requetes = [
        (
            "UPDATE mesures_journalieres_denses SET niveau_confiance_derive = 'C' "
            "WHERE serie_id = :a",
            banfora,
            0,
        ),
        # Tiéfora lit Banfora : elle ne peut pas porter de lignes.
        (
            "INSERT INTO mesures_journalieres_denses "
            "SELECT :a, annee, niveau_confiance_derive, valeurs_e4 "
            "FROM mesures_journalieres_denses WHERE serie_id = :b",
            tiefora,
            banfora,
        ),
        # Série dense : aucune mesure versionnée.
        (
            "INSERT INTO mesures_ressource "
            "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
            "VALUES (:a, DATE '2030-01-01', 5.0, 'brut', 'B')",
            banfora,
            0,
        ),
        # Porteuse d'une autre grandeur, porteuse versionnée, porteuse elle-même lectrice.
        (porteuse_de_tiefora, tiefora, ids["nasa_power_t2m_journalier_bfa_dep_banfora"]),
        (porteuse_de_tiefora, tiefora, ids["nasa_power_ghi_journalier_bfa_prov_comoe"]),
        (porteuse_de_tiefora, fo, tiefora),
        # Ligne hors de la période de la série ; mesure versionnée déplacée sur une
        # série dense ; série versionnée qui a des mesures passée en dense.
        (
            "INSERT INTO mesures_journalieres_denses "
            "SELECT serie_id, 2030, niveau_confiance_derive, valeurs_e4 "
            "FROM mesures_journalieres_denses WHERE serie_id = :a AND annee = 2025",
            banfora,
            0,
        ),
        (
            "UPDATE mesures_ressource SET serie_id = :a WHERE id = "
            "(SELECT min(id) FROM mesures_ressource WHERE serie_id = :b)",
            banfora,
            ids["nasa_power_ghi_journalier_bfa_prov_comoe"],
        ),
        (
            "UPDATE series_metadonnees SET stockage = 'dense' WHERE id = :a",
            ids["nasa_power_ghi_journalier_bfa_prov_comoe"],
            0,
        ),
        # Une porteuse lue par d'autres séries garde famille et stockage.
        (porteuse_de_tiefora, banfora, fo),
        (
            "UPDATE series_metadonnees SET periode_fin = DATE '2024-12-31' WHERE id = :a",
            banfora,
            0,
        ),
    ]
    for requete, a, b in requetes:
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(text(requete), {"a": a, "b": b})
