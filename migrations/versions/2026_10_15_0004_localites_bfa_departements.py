"""localites_bfa_departements

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15

Seed des communes du Burkina Faso, niveau ``commune`` (ADR-0007) : les
350 départements du décret n°2025-1012 (annexe II) et la commune de
Ouagadougou, rattachée à aucun département. Chaque entité est rattachée à sa
province (migration 0003).

Sourçage détaillé dans ``localites_bfa_departements_seed_data``. Même pattern
que la migration 0003 ; les provinces parentes sont résolues en base.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.localites_bfa_departements_seed_data import LOCALITES_SEED

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CODES_LOCALITES: tuple[str, ...] = tuple(entry["code"] for entry in LOCALITES_SEED)


def upgrade() -> None:
    bind = op.get_bind()

    hors_niveau = [e["code"] for e in LOCALITES_SEED if e["type_localite"] != "commune"]
    if hors_niveau:
        raise RuntimeError(f"Migration 0004 : niveau inattendu pour {hors_niveau!r}.")

    parents = sorted({e["parent_code"] for e in LOCALITES_SEED})
    lignes = bind.execute(
        sa.text(
            "SELECT code, id FROM localites "
            "WHERE code = ANY(:codes) AND type_localite = 'prefecture'"
        ),
        {"codes": parents},
    ).all()
    code_to_id = {row.code: row.id for row in lignes}
    manquants = [code for code in parents if code not in code_to_id]
    if manquants:
        raise RuntimeError(f"Migration 0004 : provinces parentes introuvables : {manquants!r}.")

    localites_table = sa.table(
        "localites",
        sa.column("code", sa.String),
        sa.column("nom", sa.Text),
        sa.column("type_localite", sa.String),
        sa.column("parent_id", sa.BigInteger),
        sa.column("code_administratif_national", sa.String),
        sa.column("pays_iso3", sa.String),
        sa.column("latitude", sa.Numeric(11, 8)),
        sa.column("longitude", sa.Numeric(12, 8)),
        sa.column("altitude_metres", sa.Integer),
        sa.column("population_estimee", sa.Integer),
        sa.column("annee_population", sa.Integer),
        sa.column("fuseau_horaire", sa.String),
        sa.column("notes", sa.Text),
    )
    payload: list[dict[str, Any]] = []
    for entry in LOCALITES_SEED:
        row = {k: v for k, v in entry.items() if k != "parent_code"}
        row["parent_id"] = code_to_id[entry["parent_code"]]
        payload.append(row)
    op.bulk_insert(localites_table, payload)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM localites WHERE code = ANY(:codes)").bindparams(
            sa.bindparam("codes", value=list(_CODES_LOCALITES))
        )
    )
