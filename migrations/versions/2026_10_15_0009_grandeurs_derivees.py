"""grandeurs_derivees

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-15

Grandeurs dérivées stockées (ADR-0012) aux 47 provinces et aux 351 communes,
calculées en SQL depuis les séries mensuelles brutes (migrations 0006 et 0008),
sans réseau :

| Grandeur | Formule | Fenêtre |
|---|---|---|
| 7 écarts ``ecart_relatif_<g>_<source>_nasa`` (ids 35 à 41) | (x - nasa) / nasa × 100 | commune aux deux sources |
| ``fraction_diffuse`` (id 3, déjà au référentiel) | DHI / GHI NASA POWER | 2001 à 2025 |

Écarts : GHI SARAH-3, ERA5 et CAMS ; DNI SARAH-3, ERA5 et CAMS ; DHI CAMS. Une
ligne par localité et par mois de la fenêtre commune, obtenue par jointure.
Fraction diffuse : une ligne par mois, et une ligne par année complète
(``Σ DHI_m·n_m / Σ GHI_m·n_m``, sommes en ``numeric`` pour un résultat
indépendant de l'ordre d'agrégation).

Séries ``kuma_calculs`` (``calcul_derive``, granularité nulle), confiance B,
statut ``brut``. Trigger d'audit de ``grandeurs_metier`` suspendu le temps du
calcul et de sa suppression (``docs/architecture/03-audit.md``, migrations de
masse). Garde-fous : identité des sources, comptes par grandeur, fraction
diffuse dans [0, 1]. ``downgrade`` supprime les lignes, les séries et les sept
grandeurs d'écart ; ``fraction_diffuse`` reste au référentiel.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.grandeurs_derivees_bfa import (
    ECARTS,
    FRACTION_DIFFUSE_CODE,
    FRACTION_DIFFUSE_DEBUT,
    FRACTION_DIFFUSE_FIN,
    EcartInterSource,
    code_serie_fraction_diffuse,
)
from kuma_data_core.db.seeds.lots_bfa import LOTS, points_lot

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_LOCALITES: int = 398
NB_ECARTS_ATTENDU: int = 663_864  # 398 × (4 × 228 + 3 × 252)
NB_FD_MENSUEL_ATTENDU: int = 119_400  # 398 × 300
NB_FD_ANNUEL_ATTENDU: int = 9_950  # 398 × 25
TRIGGER_AUDIT: str = "trg_audit_grandeurs_metier"

MISES_EN_GARDE: dict[str, str] = {
    "sarah3_monthly": (
        " Six mois SARAH-3 sont abaissés par des journées satellite manquantes "
        "(janvier, mars et mai 2008, janvier et avril 2009, octobre 2016) : l'écart y "
        "est tiré vers le bas."
    ),
    "era5_pvgis": (
        " ERA5 est une réanalyse, source de comparaison ; son niveau monte en 2021-2023 "
        "(changement probable du produit PVGIS-ERA5)."
    ),
    "cams_radiation": (
        " CAMS et SARAH-3 exploitent tous deux l'imagerie Meteosat : leur accord ne vaut "
        "pas deux confirmations indépendantes."
    ),
}
MAILLE_NASA: str = (
    " NASA POWER sert une maille de 1°, commune aux localités voisines de la même maille."
)

_SERIES = sa.table(
    "series_metadonnees",
    sa.column("code", sa.String),
    sa.column("libelle", sa.Text),
    sa.column("localite_id", sa.BigInteger),
    sa.column("grandeur_code", sa.String),
    sa.column("source_id", sa.BigInteger),
    sa.column("periode_debut", sa.Date),
    sa.column("periode_fin", sa.Date),
    sa.column("methode_collecte", sa.String),
    sa.column("granularite", sa.String),
    sa.column("note_publique", sa.Text),
)

# Mesures mensuelles brutes d'une source et d'une grandeur, par localité.
_MENSUELLES: str = """
    SELECT s.localite_id, m.annee, m.mois, m.valeur
    FROM series_metadonnees s
    JOIN sources so ON so.id = s.source_id
    JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
    WHERE so.code = :{source} AND s.grandeur_code = :{grandeur}
      AND s.granularite = 'mensuel' AND m.valide_au IS NULL
"""

_INSERT_ECART: str = f"""
    INSERT INTO grandeurs_metier (
        grandeur_code, localite_id, series_metadonnees_id, periode_type,
        annee_debut, annee_fin, mois, version_formule, valeur, niveau_confiance_derive
    )
    SELECT :code, x.localite_id, cible.id, 'mensuel', x.annee, x.annee, x.mois, 1,
           (x.valeur - n.valeur) / n.valeur * 100.0, 'B'
    FROM ({_MENSUELLES.format(source="source", grandeur="grandeur")}) x
    JOIN ({_MENSUELLES.format(source="nasa", grandeur="grandeur")}) n
      ON n.localite_id = x.localite_id AND n.annee = x.annee AND n.mois = x.mois
    JOIN series_metadonnees cible
      ON cible.localite_id = x.localite_id AND cible.grandeur_code = :code
    WHERE x.annee BETWEEN :debut AND :fin
"""

_COUPLES_FD: str = f"""
    WITH couples AS (
        SELECT cible.id AS serie_id, d.localite_id, d.annee, d.mois,
               d.valeur AS dhi, g.valeur AS ghi,
               extract(day FROM make_date(d.annee, d.mois, 1)
                                + interval '1 month - 1 day')::int AS n_jours
        FROM ({_MENSUELLES.format(source="nasa", grandeur="dhi")}) d
        JOIN ({_MENSUELLES.format(source="nasa", grandeur="ghi")}) g
          ON g.localite_id = d.localite_id AND g.annee = d.annee AND g.mois = d.mois
        JOIN series_metadonnees cible
          ON cible.localite_id = d.localite_id AND cible.grandeur_code = :code
        WHERE d.annee BETWEEN :debut AND :fin
    )
"""


def _points() -> list[tuple[str, str]]:
    return [(code, nom) for lot in LOTS for code, nom, *_ in points_lot(lot)]


def _note_ecart(ecart: EcartInterSource) -> str:
    g = ecart.grandeur_brute.upper()
    # SARAH-3 ne sert pas de DHI : la mise en garde Meteosat ne vaut que pour GHI et DNI.
    mise_en_garde = "" if ecart.grandeur_brute == "dhi" else MISES_EN_GARDE[ecart.source_code]
    return (
        f"Écart relatif mensuel du {g} {ecart.source_libelle} au {g} NASA POWER, "
        f"(x - NASA) / NASA × 100 en %, sur les mois communs {ecart.annee_debut}-"
        f"{ecart.annee_fin} (ADR-0012). Positif : la source est plus haute que NASA POWER, "
        "dénominateur commun de tous les écarts, référence de comparaison et non valeur "
        f"vraie. Confiance B.{mise_en_garde}{MAILLE_NASA}"
    )


def upgrade() -> None:
    bind = op.get_bind()

    sources: dict[str, int] = {
        r.code: r.id for r in bind.execute(sa.text("SELECT code, id FROM sources")).all()
    }
    for code in ("nasa_power", "kuma_calculs", *(e.source_code for e in ECARTS)):
        if code not in sources:
            raise RuntimeError(f"Migration 0009 : source {code!r} absente.")
    unites: dict[str, int] = {
        r.code: r.id for r in bind.execute(sa.text("SELECT code, id FROM unites")).all()
    }
    fd = bind.execute(
        sa.text("SELECT id, strategie_calcul FROM grandeurs_referentiel WHERE code = :c"),
        {"c": FRACTION_DIFFUSE_CODE},
    ).one()
    if tuple(fd) != (3, "stockee"):
        raise RuntimeError(f"Migration 0009 : fraction_diffuse = {tuple(fd)!r}, (3, 'stockee').")

    op.bulk_insert(
        sa.table(
            "grandeurs_referentiel",
            sa.column("id", sa.BigInteger),
            sa.column("code", sa.String),
            sa.column("libelle", sa.Text),
            sa.column("unite_id", sa.BigInteger),
            sa.column("famille", sa.String),
            sa.column("strategie_calcul", sa.String),
            sa.column("version_formule_actuelle", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {
                "id": e.grandeur_id,
                "code": e.grandeur_code,
                "libelle": (
                    f"Écart relatif {e.grandeur_brute.upper()} {e.source_libelle} "
                    "par rapport à NASA POWER"
                ),
                "unite_id": unites["pourcent"],
                "famille": "F1",
                "strategie_calcul": "stockee",
                "version_formule_actuelle": 1,
                "description": (
                    f"Écart relatif mensuel du {e.grandeur_brute.upper()} entre "
                    f"{e.source_libelle} (comparée) et NASA POWER (dénominateur), "
                    "(x - nasa) / nasa × 100, en pourcent signé, sur les mois communs aux "
                    "deux séries. Matérialisé dans grandeurs_metier (ADR-0012)."
                ),
            }
            for e in ECARTS
        ],
    )
    op.execute(
        "SELECT setval(pg_get_serial_sequence('grandeurs_referentiel', 'id'), "
        "(SELECT max(id) FROM grandeurs_referentiel))"
    )

    points = _points()
    if len(points) != NB_LOCALITES:
        raise RuntimeError(f"Migration 0009 : {len(points)} localités, {NB_LOCALITES} attendues.")
    loc: dict[str, int] = {
        r.code: r.id
        for r in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"),
            {"c": [code for code, _ in points]},
        ).all()
    }
    manquantes = [code for code, _ in points if code not in loc]
    if manquantes:
        raise RuntimeError(f"Migration 0009 : localité(s) introuvable(s) : {manquantes!r}.")
    nuls = bind.execute(
        sa.text(
            "SELECT count(*) FROM mesures_ressource_mensuelles m "
            "JOIN series_metadonnees s ON s.id = m.serie_id "
            "WHERE s.source_id = :nasa AND s.granularite = 'mensuel' AND m.valeur <= 0"
        ),
        {"nasa": sources["nasa_power"]},
    ).scalar_one()
    if nuls:
        raise RuntimeError(f"Migration 0009 : {nuls} mesure(s) NASA POWER nulle(s), dénominateur.")
    calcul = sources["kuma_calculs"]
    lignes_series = [
        {
            "code": e.code_serie(code),
            "libelle": (
                f"Écart {e.grandeur_brute.upper()} {e.source_libelle} / NASA POWER, {nom} "
                f"({e.annee_debut}-{e.annee_fin})"
            ),
            "localite_id": loc[code],
            "grandeur_code": e.grandeur_code,
            "source_id": calcul,
            "periode_debut": f"{e.annee_debut}-01-01",
            "periode_fin": f"{e.annee_fin}-12-31",
            "methode_collecte": "calcul_derive",
            "granularite": None,
            "note_publique": _note_ecart(e),
        }
        for e in ECARTS
        for code, nom in points
    ]
    lignes_series += [
        {
            "code": code_serie_fraction_diffuse(code),
            "libelle": (
                f"Fraction diffuse NASA POWER, {nom} "
                f"({FRACTION_DIFFUSE_DEBUT}-{FRACTION_DIFFUSE_FIN})"
            ),
            "localite_id": loc[code],
            "grandeur_code": FRACTION_DIFFUSE_CODE,
            "source_id": calcul,
            "periode_debut": f"{FRACTION_DIFFUSE_DEBUT}-01-01",
            "periode_fin": f"{FRACTION_DIFFUSE_FIN}-12-31",
            "methode_collecte": "calcul_derive",
            "granularite": None,
            "note_publique": (
                "Fraction diffuse DHI / GHI NASA POWER, sans dimension, par mois et par "
                f"année complète, {FRACTION_DIFFUSE_DEBUT}-{FRACTION_DIFFUSE_FIN} (ADR-0012). "
                "Calculée depuis le mensuel NASA POWER, dont le DHI ne ferme pas toujours "
                f"avec le GHI et le DNI. Confiance B.{MAILLE_NASA}"
            ),
        }
        for code, nom in points
    ]
    op.bulk_insert(_SERIES, lignes_series)

    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_ressource_mensuelles")
    op.execute(f"ALTER TABLE grandeurs_metier DISABLE TRIGGER {TRIGGER_AUDIT}")
    comptes: dict[str, int] = {}
    for e in ECARTS:
        resultat = bind.execute(
            sa.text(_INSERT_ECART),
            {
                "code": e.grandeur_code,
                "source": e.source_code,
                "nasa": "nasa_power",
                "grandeur": e.grandeur_brute,
                "debut": e.annee_debut,
                "fin": e.annee_fin,
            },
        )
        comptes[e.grandeur_code] = resultat.rowcount
        if resultat.rowcount != NB_LOCALITES * e.nb_mois:
            raise RuntimeError(
                f"Migration 0009 : {e.grandeur_code} : {resultat.rowcount} lignes, "
                f"{NB_LOCALITES * e.nb_mois} attendues."
            )

    params_fd = {
        "code": FRACTION_DIFFUSE_CODE,
        "nasa": "nasa_power",
        "dhi": "dhi",
        "ghi": "ghi",
        "debut": FRACTION_DIFFUSE_DEBUT,
        "fin": FRACTION_DIFFUSE_FIN,
    }
    mensuel = bind.execute(
        sa.text(
            _COUPLES_FD
            + """
            INSERT INTO grandeurs_metier (
                grandeur_code, localite_id, series_metadonnees_id, periode_type,
                annee_debut, annee_fin, mois, version_formule, valeur,
                niveau_confiance_derive
            )
            SELECT :code, localite_id, serie_id, 'mensuel', annee, annee, mois, 1,
                   dhi / ghi, 'B'
            FROM couples
            """
        ),
        params_fd,
    ).rowcount
    annuel = bind.execute(
        sa.text(
            _COUPLES_FD
            + """
            INSERT INTO grandeurs_metier (
                grandeur_code, localite_id, series_metadonnees_id, periode_type,
                annee_debut, annee_fin, mois, version_formule, valeur,
                niveau_confiance_derive
            )
            SELECT :code, localite_id, serie_id, 'annuel', annee, annee, NULL, 1,
                   (sum(dhi::numeric * n_jours) / sum(ghi::numeric * n_jours))::float8, 'B'
            FROM couples
            GROUP BY localite_id, serie_id, annee
            HAVING count(*) = 12
            """
        ),
        params_fd,
    ).rowcount
    op.execute(f"ALTER TABLE grandeurs_metier ENABLE TRIGGER {TRIGGER_AUDIT}")

    if (sum(comptes.values()), mensuel, annuel) != (
        NB_ECARTS_ATTENDU,
        NB_FD_MENSUEL_ATTENDU,
        NB_FD_ANNUEL_ATTENDU,
    ):
        raise RuntimeError(
            f"Migration 0009 : {sum(comptes.values())} écarts, {mensuel} et {annuel} "
            f"fractions diffuses ; {NB_ECARTS_ATTENDU}, {NB_FD_MENSUEL_ATTENDU} et "
            f"{NB_FD_ANNUEL_ATTENDU} attendus."
        )
    hors_domaine = bind.execute(
        sa.text(
            "SELECT count(*) FROM grandeurs_metier WHERE grandeur_code = :c "
            "AND NOT (valeur BETWEEN 0 AND 1)"
        ),
        {"c": FRACTION_DIFFUSE_CODE},
    ).scalar_one()
    if hors_domaine:
        raise RuntimeError(f"Migration 0009 : {hors_domaine} fraction(s) diffuse(s) hors [0, 1].")
    op.execute("ANALYZE grandeurs_metier")


def downgrade() -> None:
    bind = op.get_bind()
    codes = [e.code_serie(code) for e in ECARTS for code, _ in _points()]
    codes += [code_serie_fraction_diffuse(code) for code, _ in _points()]
    op.execute(f"ALTER TABLE grandeurs_metier DISABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(
        sa.text(
            "DELETE FROM grandeurs_metier WHERE series_metadonnees_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:c))"
        ),
        {"c": codes},
    )
    op.execute(f"ALTER TABLE grandeurs_metier ENABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:c)"), {"c": codes})
    bind.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE id = ANY(:ids)"),
        {"ids": [e.grandeur_id for e in ECARTS]},
    )
    op.execute(
        "SELECT setval(pg_get_serial_sequence('grandeurs_referentiel', 'id'), "
        "(SELECT max(id) FROM grandeurs_referentiel))"
    )
