"""Tests d'intégration de l'horaire NASA POWER aux 398 localités (ADR-0026).

Migrations 0026 (séries horaires lues sur une porteuse, vue
``v_mesures_horaires``) et 0027 (une série par maille, les autres localités
lisent la porteuse de leur maille).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_HORAIRES, PILOTES_HORAIRES
from kuma_data_core.db.seeds.mailles_horaires import lire_mailles
from kuma_data_core.services.capsule.acquisition import SourceCore
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import executer_qc_horaire

pytestmark = pytest.mark.integration

_SERIES_HORAIRES_NASA = """
    SELECT s.id, s.code, s.grandeur_code, l.code AS localite, l.type_localite,
           p.code AS porteuse
    FROM series_metadonnees s
    JOIN sources so ON so.id = s.source_id
    JOIN localites l ON l.id = s.localite_id
    LEFT JOIN series_metadonnees p ON p.id = s.serie_porteuse_id
    WHERE so.code = 'nasa_power' AND s.granularite = 'horaire'
"""


def _series(session: Session) -> list[dict[str, str | int | None]]:
    return [dict(r._mapping) for r in session.execute(text(_SERIES_HORAIRES_NASA))]


def test_quatre_series_par_localite(db_session: Session) -> None:
    """Les 47 provinces et les 351 communes ont leurs quatre séries horaires NASA POWER."""
    comptes = Counter((s["type_localite"], s["grandeur_code"]) for s in _series(db_session))
    assert comptes == {
        (niveau, g): n
        for niveau, n in (("prefecture", 47), ("commune", 351))
        for g in CONTRATS_HORAIRES
    }


def test_porteuses_du_fichier_des_mailles(db_session: Session) -> None:
    """Chaque série lit la porteuse que donne le fichier des mailles, ou porte elle-même."""
    mailles = {m.localite_code: m for m in lire_mailles()}
    for s in _series(db_session):
        porteuse = mailles[str(s["localite"])].porteuse(str(s["grandeur_code"]))
        attendue = (
            None
            if porteuse == s["localite"]
            else f"nasa_power_{s['grandeur_code']}_horaire_{porteuse}"
        )
        assert s["porteuse"] == attendue, s["code"]
    for pilote in PILOTES_HORAIRES:
        assert {mailles[pilote].porteuse(g) for g in CONTRATS_HORAIRES} == {pilote}


def test_mesures_des_porteuses_seulement(db_session: Session) -> None:
    """Une porteuse a ses 43 824 heures, une série alias aucune ; la vue rend les deux."""
    series = _series(db_session)
    lignes = dict(
        db_session.execute(
            text(
                "SELECT serie_id, count(*) FROM mesures_ressource_horaires "
                "WHERE valide_au IS NULL AND serie_id = ANY(:ids) GROUP BY serie_id"
            ),
            {"ids": [s["id"] for s in series]},
        ).all()
    )
    for s in series:
        assert lignes.get(s["id"], 0) == (43_824 if s["porteuse"] is None else 0), s["code"]
    vue = dict(
        db_session.execute(
            text(
                "SELECT serie_id, count(*) FROM v_mesures_horaires "
                "WHERE serie_id = ANY(:ids) GROUP BY serie_id"
            ),
            {"ids": [s["id"] for s in series]},
        ).all()
    )
    assert set(vue.values()) == {43_824}
    assert len(vue) == len(series)


def test_alias_rend_les_mesures_de_sa_porteuse(db_session: Session) -> None:
    """La province du Kadiogo lit les mesures et les statuts de sa porteuse."""

    def lire(code: str) -> list[tuple[object, ...]]:
        return [
            tuple(r)
            for r in db_session.execute(
                text(
                    "SELECT v.instant_mesure, v.valeur, v.statut, v.commentaire_editorial "
                    "FROM v_mesures_horaires v JOIN series_metadonnees s ON s.id = v.serie_id "
                    "WHERE s.code = :code ORDER BY v.instant_mesure"
                ),
                {"code": code},
            )
        ]

    serie = next(
        s for s in _series(db_session) if s["code"] == "nasa_power_ghi_horaire_bfa_prov_kadiogo"
    )
    assert serie["porteuse"] is not None
    assert lire(str(serie["code"])) == lire(str(serie["porteuse"]))


def test_mailles_du_journalier(db_session: Session) -> None:
    """Une localité et sa porteuse ont aussi le même GHI et la même température journaliers.

    NASA POWER agrège le journalier de l'horaire, sur les mêmes mailles : les
    mailles constatées sur l'horaire 2021-2025 se retrouvent jour par jour.
    """
    paires = [
        (str(s["localite"]), str(s["porteuse"]).rsplit("_horaire_", 1)[1], str(s["grandeur_code"]))
        for s in _series(db_session)
        if s["porteuse"] is not None and s["grandeur_code"] in ("ghi", "t2m")
    ]
    codes = {f"nasa_power_{g}_journalier_{loc}" for a, p, g in paires for loc in (a, p)}
    ids = dict(
        db_session.execute(
            text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": sorted(codes)},
        ).all()
    )
    assert set(ids) == codes
    valeurs: dict[int, dict[date, float]] = defaultdict(dict)
    for r in db_session.execute(
        text(
            "SELECT serie_id, instant_mesure, valeur FROM v_mesures_journalieres "
            "WHERE serie_id = ANY(:ids) AND instant_mesure BETWEEN '2021-01-01' AND '2025-12-31'"
        ),
        {"ids": list(ids.values())},
    ):
        valeurs[r.serie_id][r.instant_mesure] = r.valeur
    for alias, porteuse, g in paires:
        jours_alias = valeurs[ids[f"nasa_power_{g}_journalier_{alias}"]]
        assert len(jours_alias) > 1_800
        assert jours_alias == valeurs[ids[f"nasa_power_{g}_journalier_{porteuse}"]], (alias, g)


def test_controle_qualite_v1(db_session: Session) -> None:
    """Chaque mesure chargée porte le statut et le commentaire du contrôle qualité v1."""
    comptes = dict(
        db_session.execute(
            text(
                """
                SELECT m.statut || ' ' || split_part(m.commentaire_editorial, ' ', 3), count(*)
                FROM mesures_ressource_horaires m
                JOIN series_metadonnees s ON s.id = m.serie_id
                JOIN sources so ON so.id = s.source_id
                WHERE so.code = 'nasa_power' AND m.valide_au IS NULL
                  AND m.commentaire_editorial LIKE '[QC v1] %'
                GROUP BY 1
                """
            )
        ).all()
    )
    total = db_session.execute(
        text(
            "SELECT count(*) FROM mesures_ressource_horaires m "
            "JOIN series_metadonnees s ON s.id = m.serie_id "
            "JOIN sources so ON so.id = s.source_id "
            "WHERE so.code = 'nasa_power' AND m.valide_au IS NULL"
        )
    ).scalar_one()
    assert sum(comptes.values()) == total
    assert set(comptes) <= {"valide_auto valide_auto", "valide_auto valide_auto ;", "brut rejet"}


def test_note_des_pilotes_qui_portent_une_maille(db_session: Session) -> None:
    """La note d'une série pilote dit combien de localités la lisent."""
    lecteurs = Counter(str(s["porteuse"]) for s in _series(db_session) if s["porteuse"])
    notes = dict(
        db_session.execute(
            text("SELECT code, note_publique FROM series_metadonnees WHERE code = ANY(:c)"),
            {
                "c": [
                    f"nasa_power_{g}_horaire_{p}"
                    for g in CONTRATS_HORAIRES
                    for p in PILOTES_HORAIRES
                ]
            },
        ).all()
    )
    for code, note in notes.items():
        assert ("ADR-0026" in note) == (lecteurs[code] > 0), code
        if lecteurs[code]:
            assert f" {lecteurs[code]} autre" in note


def _refus(session: Session, motif: str, requete: str, **parametres: object) -> None:
    with pytest.raises(DBAPIError, match=motif), session.begin_nested():
        session.execute(text(requete), parametres)


def test_gardes(db_session: Session) -> None:
    """Pas de mesure propre pour une série alias, pas d'alias pour une série qui porte.

    Une série ne lit qu'une porteuse de même famille, qui ne lit elle-même aucune
    série ; une porteuse lue ne change pas de famille.
    """
    series = {str(s["code"]): s for s in _series(db_session)}
    alias = series["nasa_power_ghi_horaire_bfa_prov_kadiogo"]
    porteuse = series[str(alias["porteuse"])]
    autre_alias = next(
        s
        for s in series.values()
        if s["grandeur_code"] == "ghi" and s["porteuse"] not in (None, porteuse["code"])
    )
    lecteurs = Counter(str(s["porteuse"]) for s in series.values() if s["porteuse"])
    isolee = next(
        s
        for code, s in sorted(series.items())
        if s["grandeur_code"] == "ghi"
        and s["porteuse"] is None
        and not lecteurs[code]
        and s["localite"] not in PILOTES_HORAIRES
    )
    lier = "UPDATE series_metadonnees SET serie_porteuse_id = :p WHERE id = :id"

    _refus(
        db_session,
        "pas de mesure horaire propre",
        "INSERT INTO mesures_ressource_horaires "
        "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) "
        "VALUES (:id, '2021-01-01T00:00Z', 0, 'brut', 'B')",
        id=alias["id"],
    )
    _refus(
        db_session,
        "pas de mesure horaire propre",
        "UPDATE mesures_ressource_horaires SET serie_id = :alias WHERE id = "
        "(SELECT min(id) FROM mesures_ressource_horaires WHERE serie_id = :porteuse)",
        alias=alias["id"],
        porteuse=porteuse["id"],
    )
    _refus(db_session, "porte des mesures horaires", lier, p=porteuse["id"], id=isolee["id"])
    _refus(db_session, "doit être une série porteuse", lier, p=autre_alias["id"], id=alias["id"])
    autre_grandeur = series[str(porteuse["code"]).replace("_ghi_", "_dni_")]
    _refus(db_session, "même grandeur", lier, p=autre_grandeur["id"], id=alias["id"])
    _refus(
        db_session,
        "famille et stockage figés",
        "UPDATE series_metadonnees SET periode_fin = '2025-12-30' WHERE id = :id",
        id=porteuse["id"],
    )
    # Cas admis : une série alias passe à une autre porteuse de la même famille.
    with db_session.begin_nested() as permis:
        db_session.execute(text(lier), {"p": isolee["id"], "id": alias["id"]})
        permis.rollback()


def test_verdicts_des_porteuses_au_controle_par_ligne(db_session: Session) -> None:
    """Les verdicts chargés par la 0027 sont ceux du contrôle sur les lignes stockées.

    Falagountou porte une maille de rayonnement, avec l'heure rejetée ; la première
    porteuse de température hors des pilotes complète. Le contrôle se fait aux
    coordonnées de la porteuse.
    """
    temperature = next(
        m.localite_code
        for m in lire_mailles()
        if m.porteuse_temperature == m.localite_code and m.localite_code not in PILOTES_HORAIRES
    )
    for localite, grandeurs in (
        ("bfa_dep_falagountou", ("ghi", "dni", "dhi")),
        (temperature, ("t2m",)),
    ):
        ids = {
            g: int(s["id"])
            for s in _series(db_session)
            for g in grandeurs
            if s["code"] == f"nasa_power_{g}_horaire_{localite}" and s["porteuse"] is None
        }
        assert set(ids) == set(grandeurs), localite
        latitude, longitude = db_session.execute(
            text("SELECT latitude, longitude FROM localites WHERE code = :c"), {"c": localite}
        ).one()
        attendus = {
            v.row_id: (v.statut_cible, v.commentaire())
            for v in executer_qc_horaire(
                db_session, ids, float(latitude), float(longitude), DECALAGE_MILIEU_HEURE
            )
        }
        stockes = {
            r.id: (r.statut, r.commentaire_editorial)
            for r in db_session.execute(
                text(
                    "SELECT id, statut, commentaire_editorial FROM mesures_ressource_horaires "
                    "WHERE serie_id = ANY(:ids) AND valide_au IS NULL"
                ),
                {"ids": list(ids.values())},
            )
        }
        assert len(stockes) == 43_824 * len(grandeurs)
        assert stockes == attendus, localite


def test_capsule_lit_la_porteuse(db_session: Session) -> None:
    """La séquence horaire de la capsule d'étude, au Kadiogo, est celle de sa porteuse."""
    maille = next(m for m in lire_mailles() if m.localite_code == "bfa_prov_kadiogo")
    ids = dict(
        db_session.execute(
            text("SELECT code, id FROM localites WHERE code = ANY(:c)"),
            {"c": ["bfa_prov_kadiogo", maille.porteuse("ghi")]},
        ).all()
    )
    source = SourceCore(session=db_session, annee_min=2024, annee_max=2024)
    sequence, periode, provenance = source._sequence_horaire(ids["bfa_prov_kadiogo"])
    sequence_porteuse, _, _ = source._sequence_horaire(ids[maille.porteuse("ghi")])
    assert provenance["code"] == "nasa_power_ghi_horaire_bfa_prov_kadiogo"
    assert periode == {"debut": "2024-01", "fin": "2024-12"}
    assert len(sequence["ghi"]) == 8_784
    assert sequence == sequence_porteuse
