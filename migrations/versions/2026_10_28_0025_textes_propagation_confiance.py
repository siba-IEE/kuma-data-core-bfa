"""textes_propagation_confiance

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-28

Textes publics alignés sur la règle de propagation P (ADR-0025). Les
descriptions de ``pr_realiste`` et de ``taux_salissure_proxy`` disaient
« confiance B » : leur niveau est celui de leurs entrées, au plus B. Le
commentaire de ``grandeurs_metier.niveau_confiance_derive`` ne citait que R1 à
R4 ; il cite aussi la règle P.

Chaque texte n'est réécrit que s'il est resté celui de 0024, et le
``downgrade`` les rend. Aucune valeur ni aucun niveau ne change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANDEURS: tuple[str, ...] = ("pr_realiste", "taux_salissure_proxy")
CONFIANCE_AVANT: str = "Calculé à la volée, confiance B."
CONFIANCE_APRES: str = (
    "Calculé à la volée, confiance au plus B : le plus bas des niveaux de ses entrées "
    "(règle de propagation P)."
)

COLONNE: str = "grandeurs_metier.niveau_confiance_derive"
COMMENTAIRE_AVANT: str = (
    "Niveau de confiance dérivé par la couche de service à partir des règles R1 à R4 "
    "(docs/contribution/confiance-et-statuts.md), selon la méthode de collecte et la "
    "source de la série. A = haute, B = moyenne, C = basse."
)
COMMENTAIRE_APRES: str = (
    "Niveau de confiance dérivé à partir des règles R1 à R4, selon la méthode de collecte "
    "et la source de la série, et de la règle de propagation P pour une grandeur calculée : "
    "le plus bas des niveaux de ses entrées, au plus le plafond de sa méthode "
    "(docs/contribution/confiance-et-statuts.md). A = haute, B = moyenne, C = basse."
)


def _description(bind: sa.Connection, code: str, depuis: str, cible: str) -> int:
    """Remplace ``depuis`` par ``cible`` dans la description de ``code``, s'il y figure."""
    return bind.execute(
        sa.text(
            "UPDATE grandeurs_referentiel "
            "SET description = replace(description, :a, :n), modifie_le = now() "
            "WHERE code = :code AND strpos(description, :a) > 0"
        ),
        {"a": depuis, "n": cible, "code": code},
    ).rowcount


def _commenter(bind: sa.Connection, depuis: str, cible: str) -> bool:
    """Passe le commentaire de ``COLONNE`` de ``depuis`` à ``cible`` ; un autre reste."""
    table, _, colonne = COLONNE.partition(".")
    actuel = bind.execute(
        sa.text(
            "SELECT col_description(attrelid, attnum) FROM pg_attribute "
            "WHERE attrelid = CAST(:t AS regclass) AND attname = :c"
        ),
        {"t": f"public.{table}", "c": colonne},
    ).scalar_one_or_none()
    if actuel != depuis:
        return False
    litteral = bind.execute(sa.text("SELECT quote_literal(:t)"), {"t": cible}).scalar_one()
    # COMMENT ON n'accepte pas de paramètre lié : le texte, échappé par quote_literal, est
    # inséré tel quel, sans que le pilote lise ses deux-points comme des paramètres.
    bind.exec_driver_sql(
        f"COMMENT ON COLUMN public.{COLONNE} IS {litteral}",
        execution_options={"no_parameters": True},
    )
    return True


def upgrade() -> None:
    bind = op.get_bind()
    for code in GRANDEURS:
        if _description(bind, code, CONFIANCE_AVANT, CONFIANCE_APRES) != 1:
            raise RuntimeError(f"Migration 0025 : grandeur {code!r} absente ou déjà modifiée.")
    if not _commenter(bind, COMMENTAIRE_AVANT, COMMENTAIRE_APRES):
        raise RuntimeError(f"Migration 0025 : commentaire {COLONNE!r} absent ou déjà modifié.")


def downgrade() -> None:
    bind = op.get_bind()
    _commenter(bind, COMMENTAIRE_APRES, COMMENTAIRE_AVANT)
    for code in GRANDEURS:
        _description(bind, code, CONFIANCE_APRES, CONFIANCE_AVANT)
