"""mesures_journalieres_denses

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-27

Stockage dense des mesures journalières (ADR-0017) :

- colonne ``series_metadonnees.stockage`` (``versionne`` par défaut,
  ``dense`` pour une série journalière dont les mesures vont dans la table
  dense) ;
- colonne ``series_metadonnees.serie_porteuse_id`` : une série dense
  identique à une autre (même maille de la source) lit les mesures de
  celle-ci au lieu d'en porter une copie ;
- table ``mesures_journalieres_denses`` : une ligne par série porteuse et par
  année, valeurs du jour en dix-millièmes dans un tableau, clé primaire
  ``(serie_id, annee)``, sans versionnement, sans statut ni audit ligne à
  ligne ;
- vue ``v_mesures_journalieres`` : mesures journalières courantes de
  ``mesures_ressource`` et mesures denses dépliées, rendues à chaque série,
  porteuse ou non (statut ``brut``), lue par l'API et les grandeurs calculées ;
- triggers de garde : aucune mise à jour de ligne dense, lignes denses
  réservées aux séries porteuses, aucune mesure versionnée pour une série
  dense, porteuse de même famille et sur un seul niveau.

Aucune donnée : les séries denses arrivent par les migrations suivantes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VUE: str = """
CREATE VIEW v_mesures_journalieres AS
SELECT serie_id, instant_mesure, valeur, niveau_confiance_derive,
       niveau_confiance_override, statut
FROM mesures_ressource
WHERE valide_au IS NULL
UNION ALL
SELECT s.id, make_date(d.annee, 1, 1) + (j.rang - 1)::integer, j.e4::float8 / 10000,
       d.niveau_confiance_derive, NULL::varchar(1), 'brut'::varchar(16)
FROM series_metadonnees s
JOIN mesures_journalieres_denses d ON d.serie_id = COALESCE(s.serie_porteuse_id, s.id)
CROSS JOIN LATERAL unnest(d.valeurs_e4) WITH ORDINALITY AS j(e4, rang)
WHERE s.stockage = 'dense' AND j.e4 IS NOT NULL
"""

# Fonction de garde : table, moment et portée de son trigger, corps PL/pgSQL.
GARDES: dict[str, tuple[str, str, str, str]] = {
    "kuma_refus_mise_a_jour_dense": (
        "mesures_journalieres_denses",
        "BEFORE UPDATE",
        "FOR EACH STATEMENT",
        """
BEGIN
    RAISE EXCEPTION 'mesures_journalieres_denses : aucune mise à jour de ligne, '
        'une correction réédite la série (ADR-0017)';
END
""",
    ),
    "kuma_controle_ligne_dense": (
        "mesures_journalieres_denses",
        "BEFORE INSERT",
        "FOR EACH ROW",
        """
BEGIN
    PERFORM 1 FROM series_metadonnees
    WHERE id = NEW.serie_id AND stockage = 'dense' AND serie_porteuse_id IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'série % : lignes denses réservées aux séries denses porteuses',
            NEW.serie_id;
    END IF;
    RETURN NEW;
END
""",
    ),
    "kuma_refus_mesure_versionnee_dense": (
        "mesures_ressource",
        "BEFORE INSERT",
        "FOR EACH ROW",
        """
BEGIN
    PERFORM 1 FROM series_metadonnees WHERE id = NEW.serie_id AND stockage = 'dense';
    IF FOUND THEN
        RAISE EXCEPTION 'série % : stockage dense, pas de mesure dans mesures_ressource',
            NEW.serie_id;
    END IF;
    RETURN NEW;
END
""",
    ),
    "kuma_controle_serie_porteuse": (
        "series_metadonnees",
        "BEFORE INSERT OR UPDATE",
        "FOR EACH ROW",
        """
BEGIN
    IF NEW.serie_porteuse_id IS NOT NULL THEN
        PERFORM 1 FROM series_metadonnees p
        WHERE p.id = NEW.serie_porteuse_id
          AND p.serie_porteuse_id IS NULL AND p.stockage = 'dense'
          AND p.grandeur_code = NEW.grandeur_code AND p.source_id = NEW.source_id
          AND p.periode_debut = NEW.periode_debut
          AND p.periode_fin IS NOT DISTINCT FROM NEW.periode_fin
          AND p.granularite IS NOT DISTINCT FROM NEW.granularite;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'série % : la porteuse % doit être une série dense porteuse '
                'de même grandeur, source, période et granularité', NEW.code,
                NEW.serie_porteuse_id;
        END IF;
    END IF;
    IF TG_OP = 'UPDATE'
       AND (NEW.serie_porteuse_id, NEW.stockage, NEW.grandeur_code, NEW.source_id,
            NEW.periode_debut, NEW.periode_fin, NEW.granularite)
           IS DISTINCT FROM
           (OLD.serie_porteuse_id, OLD.stockage, OLD.grandeur_code, OLD.source_id,
            OLD.periode_debut, OLD.periode_fin, OLD.granularite)
       AND (EXISTS (SELECT 1 FROM series_metadonnees WHERE serie_porteuse_id = NEW.id)
            OR EXISTS (SELECT 1 FROM mesures_journalieres_denses WHERE serie_id = NEW.id))
    THEN
        RAISE EXCEPTION 'série % : porteuse de mesures denses, famille et stockage figés',
            NEW.code;
    END IF;
    RETURN NEW;
END
""",
    ),
}


def _trigger(fonction: str) -> str:
    return "trg_" + fonction.removeprefix("kuma_")


def upgrade() -> None:
    op.add_column(
        "series_metadonnees",
        sa.Column(
            "stockage",
            sa.String(9),
            nullable=False,
            server_default=sa.text("'versionne'"),
            comment=(
                "Table des mesures journalieres : 'versionne' (mesures_ressource, "
                "versionnement temporel et audit) ou 'dense' "
                "(mesures_journalieres_denses, valeurs brutes en masse, ADR-0017)."
            ),
        ),
    )
    op.create_check_constraint(
        "ck_series_metadonnees_stockage_valide",
        "series_metadonnees",
        "stockage = 'versionne' OR (stockage = 'dense' AND granularite = 'journalier')",
    )
    op.add_column(
        "series_metadonnees",
        sa.Column(
            "serie_porteuse_id",
            sa.BigInteger(),
            nullable=True,
            comment=(
                "Serie dense dont celle-ci lit les mesures (meme maille de la source, "
                "valeurs identiques) ; NULL si la serie porte ses propres mesures."
            ),
        ),
    )
    op.create_foreign_key(
        "fk_series_metadonnees_serie_porteuse_id__series_metadonnees",
        "series_metadonnees",
        "series_metadonnees",
        ["serie_porteuse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_series_metadonnees_serie_porteuse_dense",
        "series_metadonnees",
        "serie_porteuse_id IS NULL OR (stockage = 'dense' AND serie_porteuse_id <> id)",
    )
    op.create_index(
        "idx_series_metadonnees_serie_porteuse_id",
        "series_metadonnees",
        ["serie_porteuse_id"],
        postgresql_where=sa.text("serie_porteuse_id IS NOT NULL"),
    )
    op.create_table(
        "mesures_journalieres_denses",
        sa.Column("serie_id", sa.BigInteger(), nullable=False),
        sa.Column("annee", sa.SmallInteger(), nullable=False),
        sa.Column("niveau_confiance_derive", sa.String(1), nullable=False),
        sa.Column(
            "valeurs_e4",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            comment=(
                "Valeur de chaque jour de l'annee, du 1er janvier au 31 decembre, en "
                "dix-milliemes de l'unite de la grandeur ; NULL pour un jour sans valeur."
            ),
        ),
        sa.ForeignKeyConstraint(
            ["serie_id"],
            ["series_metadonnees.id"],
            name="fk_mesures_journalieres_denses_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("serie_id", "annee", name="pk_mesures_journalieres_denses"),
        sa.CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_journalieres_denses_niveau_confiance_derive_valide",
        ),
        sa.CheckConstraint(
            "annee BETWEEN 1900 AND 2100",
            name="ck_mesures_journalieres_denses_annee_plausible",
        ),
        sa.CheckConstraint(
            "array_ndims(valeurs_e4) = 1 AND array_lower(valeurs_e4, 1) = 1 "
            "AND array_length(valeurs_e4, 1) = make_date(annee + 1, 1, 1) - make_date(annee, 1, 1)",
            name="ck_mesures_journalieres_denses_un_jour_par_jour",
        ),
    )
    op.execute(VUE)
    for fonction, (table, moment, portee, corps) in GARDES.items():
        op.execute(f"CREATE FUNCTION {fonction}() RETURNS trigger LANGUAGE plpgsql AS $${corps}$$")
        op.execute(
            f"CREATE TRIGGER {_trigger(fonction)} {moment} ON {table} "
            f"{portee} EXECUTE FUNCTION {fonction}()"
        )


def downgrade() -> None:
    for fonction, (table, _, _, _) in GARDES.items():
        op.execute(f"DROP TRIGGER {_trigger(fonction)} ON {table}")
        op.execute(f"DROP FUNCTION {fonction}()")
    op.execute("DROP VIEW v_mesures_journalieres")
    op.drop_table("mesures_journalieres_denses")
    op.drop_index("idx_series_metadonnees_serie_porteuse_id", "series_metadonnees")
    op.drop_constraint("ck_series_metadonnees_serie_porteuse_dense", "series_metadonnees")
    op.drop_constraint(
        "fk_series_metadonnees_serie_porteuse_id__series_metadonnees", "series_metadonnees"
    )
    op.drop_column("series_metadonnees", "serie_porteuse_id")
    op.drop_constraint("ck_series_metadonnees_stockage_valide", "series_metadonnees")
    op.drop_column("series_metadonnees", "stockage")
