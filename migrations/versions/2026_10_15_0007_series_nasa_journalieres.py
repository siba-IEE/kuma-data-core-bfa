"""series_nasa_journalieres

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15

Séries journalières brutes NASA POWER (ADR-0010) aux 47 provinces :

| Grandeur | Période | Jours par série |
|---|---|---|
| GHI | 1991 à 2025 | 12 784 |
| DNI | 2001 à 2025 | 9 131 |
| DHI | 2001 à 2025 | 9 131 |

Soit 141 séries (47 provinces, 3 grandeurs), confiance B, statut ``brut``, dans
la table journalière ``mesures_ressource``. Valeurs lues dans les CSV gzip de
``seeds/donnees/`` (produits hors ligne par
``scripts/ingest_nasa_power_journalier.py``) et validées par
``series_csv.lire_series_journalieres`` ; la migration n'accède jamais au réseau.
Mesures chargées par ``COPY``, trigger d'audit des mesures suspendu le temps du
déversement et de sa suppression (``docs/architecture/03-audit.md``,
migrations de masse). Garde-fous : identité de la source, couverture exacte des
provinces, nombre de mesures par grandeur et total. ``downgrade`` supprime les
mesures puis les séries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_NASA_JOURNALIERS, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series_journalieres

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT: str = "provinces"
NB_POINTS: int = 47
NB_SERIES_ATTENDU: int = 141
NB_MESURES_ATTENDU: int = 1_459_162  # 47 × (12 784 + 2 × 9 131)
TABLE_MESURES: str = "mesures_ressource"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource"

MISE_EN_GARDE: str = (
    " Valeur de la maille de 1° de NASA POWER (CERES SYN1deg, produit SRB avant 2001), "
    "commune aux localités voisines de la même maille ; la moyenne des jours d'un mois "
    "redonne la série mensuelle. GHI, DNI et DHI ne ferment pas : GHI - DHI dépasse le "
    "DNI un jour sur quatre, surtout par ciel couvert ou chargé en poussières."
)


def _note(contrat: ContratSerie) -> str:
    return (
        f"{contrat.grandeur_code.upper()} journalier {contrat.source_libelle}, total du jour "
        f"(kWh/m²/jour), {contrat.annee_debut}-{contrat.annee_fin}. Lot « {LOT} » "
        f"(ADR-0010). Confiance {contrat.niveau_confiance}.{MISE_EN_GARDE}"
    )


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_NASA_JOURNALIERS.values()
        for code, *_ in points_lot(LOT)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = 1")
    ).scalar_one_or_none()
    if code_source != "nasa_power":
        raise RuntimeError(
            f"Migration 0007 : source id 1 = {code_source!r}, 'nasa_power' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_lot(LOT))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0007 : {len(codes_loc)} provinces, {NB_POINTS} attendues.")
    loc = {
        row.code: row.id
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0007 : localité(s) introuvable(s) : {manquants!r}.")

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
    for contrat in CONTRATS_NASA_JOURNALIERS.values():
        series = lire_series_journalieres(contrat, LOT)
        if [s["localite_code"] for s in series] != codes_loc:
            raise RuntimeError(
                f"Migration 0007 : {contrat.nom_fichier(LOT)} ne couvre pas exactement le lot."
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
                    "note_publique": _note(contrat),
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
                f"Migration 0007 : {contrat.prefixe_code} : {len(lignes)} mesures, "
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
            f"Migration 0007 : {nb_series} séries et {nb_mesures} mesures, "
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
