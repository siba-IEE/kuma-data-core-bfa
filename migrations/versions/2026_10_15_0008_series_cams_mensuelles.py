"""series_cams_mensuelles

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15

Séries mensuelles brutes CAMS Radiation (ADR-0011) aux 47 provinces et aux
351 communes : GHI, DNI et DHI, 2005 à 2025, source ``cams_radiation`` (id 13).

Soit 1 194 séries (398 localités, 3 grandeurs) de 252 mois, confiance B,
statut ``brut``. Valeurs lues dans les CSV gzip de ``seeds/donnees/`` (produits
hors ligne par ``scripts/ingest_cams_radiation_mensuel.py``) et validées par
``series_csv.lire_series`` ; la migration n'accède jamais au réseau. Mesures
chargées par ``COPY``, trigger d'audit des mesures suspendu le temps du
déversement et de sa suppression (``docs/architecture/03-audit.md``,
migrations de masse). Garde-fous : identité de la source, couverture exacte des
localités de chaque lot, nombre de mesures par grandeur et total.
``downgrade`` supprime les mesures puis les séries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_CAMS, LOTS, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: dict[str, int] = {"provinces": 47, "communes": 351}
NB_SERIES_ATTENDU: int = 1_194
NB_MESURES_ATTENDU: int = 300_888  # 398 × 3 × 252
TABLE_MESURES: str = "mesures_ressource_mensuelles"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource_mensuelles"

# SARAH-3 ne sert pas de DHI : la mise en garde ne concerne que GHI et DNI.
MISE_EN_GARDE: str = (
    " CAMS et SARAH-3 exploitent tous deux l'imagerie Meteosat : leur accord ne vaut "
    "pas deux confirmations indépendantes."
)


def _note(contrat: ContratSerie, lot: str) -> str:
    return (
        f"{contrat.grandeur_code.upper()} mensuel {contrat.source_libelle}, moyenne "
        f"journalière du mois (kWh/m²/jour), {contrat.annee_debut}-{contrat.annee_fin}. "
        f"Lot « {lot} » (ADR-0011). Confiance {contrat.niveau_confiance}."
        f"{MISE_EN_GARDE if contrat.grandeur_code != 'dhi' else ''}"
    )


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for lot in LOTS
        for c in CONTRATS_CAMS.values()
        for code, *_ in points_lot(lot)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = 13")
    ).scalar_one_or_none()
    if code_source != "cams_radiation":
        raise RuntimeError(
            f"Migration 0008 : source id 13 = {code_source!r}, 'cams_radiation' attendue."
        )

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
        "(serie_id, annee, mois, valeur, statut, niveau_confiance_derive) FROM STDIN"
    )

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    nb_series = 0
    nb_mesures = 0
    for lot in LOTS:
        codes_loc = sorted(code for code, *_ in points_lot(lot))
        if len(codes_loc) != NB_POINTS[lot]:
            raise RuntimeError(
                f"Migration 0008 : lot {lot} : {len(codes_loc)} localités, "
                f"{NB_POINTS[lot]} attendues."
            )
        loc = {
            row.code: row.id
            for row in bind.execute(
                sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
            ).all()
        }
        manquants = [c for c in codes_loc if c not in loc]
        if manquants:
            raise RuntimeError(f"Migration 0008 : localité(s) introuvable(s) : {manquants!r}.")

        for contrat in CONTRATS_CAMS.values():
            series = lire_series(contrat, lot)
            if [s["localite_code"] for s in series] != codes_loc:
                raise RuntimeError(
                    f"Migration 0008 : {contrat.nom_fichier(lot)} ne couvre pas exactement le lot."
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
                        "note_publique": _note(contrat, lot),
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
                (serie_id[s["code"]], annee, mois, valeur, "brut", contrat.niveau_confiance)
                for s in series
                for annee, mois, valeur in s["mesures"]
            ]
            if len(lignes) != NB_POINTS[lot] * contrat.nb_mois:
                raise RuntimeError(
                    f"Migration 0008 : {contrat.prefixe_code} ({lot}) : {len(lignes)} mesures, "
                    f"{NB_POINTS[lot] * contrat.nb_mois} attendues."
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
            f"Migration 0008 : {nb_series} séries et {nb_mesures} mesures, "
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
