"""series_meteo_journalieres

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15

Séries journalières brutes de météo NASA POWER (ADR-0013) aux 47 provinces,
1991 à 2025 : température moyenne à 2 m (``t2m``, °C), humidité relative à 2 m
(``rh2m``, %) et précipitations corrigées (``precipitation``, mm/jour). NASA
POWER les tire de la réanalyse MERRA-2 : méthode ``reanalyse``.

Soit 141 séries (47 provinces, 3 grandeurs) de 12 784 jours, confiance B,
statut ``brut``, dans la table journalière ``mesures_ressource``. Elles
commencent le 1991-01-01 comme le GHI journalier (0007), dont les calculs du
moteur en font des séries compagnes. Valeurs lues dans les CSV gzip de
``seeds/donnees/`` (produits hors ligne par
``scripts/ingest_nasa_power_journalier.py --famille meteo``) et validées par
``series_csv.lire_series_journalieres`` ; la migration n'accède jamais au
réseau. Mesures chargées par ``COPY``, trigger d'audit des mesures suspendu le
temps du déversement et de sa suppression (``docs/architecture/03-audit.md``,
migrations de masse). Garde-fous : identité de la source, couverture exacte des
provinces, nombre de mesures par grandeur et total. ``downgrade`` supprime les
mesures puis les séries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_METEO_JOURNALIERS, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series_journalieres

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT: str = "provinces"
NB_POINTS: int = 47
NB_SERIES_ATTENDU: int = 141
NB_MESURES_ATTENDU: int = 1_802_544  # 47 × 3 × 12 784
TABLE_MESURES: str = "mesures_ressource"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource"

MISES_EN_GARDE: dict[str, str] = {
    "t2m": "",
    "rh2m": "",
    "precipitation": (
        " Série non homogène pour les extrêmes et les tendances : les fortes pluies "
        "sont bien plus fréquentes à partir de 2015 (52 jours au-dessus de 50 mm par an "
        "sur l'ensemble des provinces, contre 3 avant) ; avant 2015, les extrêmes sont "
        "lissés et les petites pluies trop fréquentes."
    ),
}
# Valeur suspecte servie par la source, signalée aux deux provinces concernées.
PLUIE_SUSPECTE: tuple[str, ...] = ("bfa_prov_comoe", "bfa_prov_leraba")
NOTE_PLUIE_SUSPECTE: str = (
    " Valeur suspecte servie par la source : 321,8 mm le 2 décembre 2025, en saison "
    "sèche ; non corrigée."
)
VALEURS: dict[str, str] = {
    "t2m": "moyenne du jour en °C",
    "rh2m": "moyenne du jour en %",
    "precipitation": "cumul du jour en mm",
}


def _note(contrat: ContratSerie, localite_code: str) -> str:
    suspecte = (
        NOTE_PLUIE_SUSPECTE
        if contrat.grandeur_code == "precipitation" and localite_code in PLUIE_SUSPECTE
        else ""
    )
    return (
        f"{contrat.grandeur_code.upper()} journalier {contrat.source_libelle} "
        f"({VALEURS[contrat.grandeur_code]}), {contrat.annee_debut}-{contrat.annee_fin}, "
        f"réanalyse MERRA-2. Lot « {LOT} » (ADR-0013). Confiance "
        f"{contrat.niveau_confiance}. Maille MERRA-2 de 0,5° × 0,625°, commune aux "
        f"provinces voisines.{MISES_EN_GARDE[contrat.grandeur_code]}{suspecte}"
    )


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_METEO_JOURNALIERS.values()
        for code, *_ in points_lot(LOT)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = 1")
    ).scalar_one_or_none()
    if code_source != "nasa_power":
        raise RuntimeError(
            f"Migration 0010 : source id 1 = {code_source!r}, 'nasa_power' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_lot(LOT))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0010 : {len(codes_loc)} provinces, {NB_POINTS} attendues.")
    loc = {
        row.code: row.id
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0010 : localité(s) introuvable(s) : {manquants!r}.")

    series_table = sa.table(
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
    copie = (
        f"COPY {TABLE_MESURES} "
        "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) FROM STDIN"
    )

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    nb_series = 0
    nb_mesures = 0
    for contrat in CONTRATS_METEO_JOURNALIERS.values():
        series = lire_series_journalieres(contrat, LOT)
        if [s["localite_code"] for s in series] != codes_loc:
            raise RuntimeError(
                f"Migration 0010 : {contrat.nom_fichier(LOT)} ne couvre pas exactement le lot."
            )
        op.bulk_insert(
            series_table,
            [
                {
                    "code": s["code"],
                    "libelle": s["libelle"],
                    "localite_id": loc[s["localite_code"]],
                    "grandeur_code": contrat.grandeur_code,
                    "source_id": contrat.source_id,
                    "periode_debut": contrat.periode_debut,
                    "periode_fin": contrat.periode_fin,
                    "methode_collecte": contrat.methode_collecte,
                    "granularite": contrat.granularite,
                    "note_publique": _note(contrat, s["localite_code"]),
                }
                for s in series
            ],
        )
        serie_id = {
            row.code: row.id
            for row in bind.execute(
                sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"),
                {"c": [s["code"] for s in series]},
            ).all()
        }
        lignes = [
            (serie_id[s["code"]], jour, valeur, "brut", contrat.niveau_confiance)
            for s in series
            for jour, valeur in s["mesures"]
        ]
        if len(lignes) != NB_POINTS * contrat.nb_jours:
            raise RuntimeError(
                f"Migration 0010 : {contrat.prefixe_code} : {len(lignes)} mesures, "
                f"{NB_POINTS * contrat.nb_jours} attendues."
            )
        pilote = bind.connection.driver_connection
        with pilote.cursor() as curseur, curseur.copy(copie) as flux:  # type: ignore[union-attr]
            for ligne in lignes:
                flux.write_row(ligne)
        nb_series += len(series)
        nb_mesures += len(lignes)
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")

    if (nb_series, nb_mesures) != (NB_SERIES_ATTENDU, NB_MESURES_ATTENDU):
        raise RuntimeError(
            f"Migration 0010 : {nb_series} séries et {nb_mesures} mesures, "
            f"{NB_SERIES_ATTENDU} et {NB_MESURES_ATTENDU} attendues."
        )
    op.execute("ANALYZE series_metadonnees")
    op.execute(f"ANALYZE {TABLE_MESURES}")


def downgrade() -> None:
    bind = op.get_bind()
    ids = [
        row.id
        for row in bind.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": _codes_series()},
        ).all()
    ]
    if ids:
        op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
        bind.execute(
            sa.text(f"DELETE FROM {TABLE_MESURES} WHERE serie_id = ANY(:ids)"), {"ids": ids}
        )
        op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
        bind.execute(sa.text("DELETE FROM series_metadonnees WHERE id = ANY(:ids)"), {"ids": ids})
