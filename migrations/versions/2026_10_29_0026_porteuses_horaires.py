"""porteuses_horaires

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-29

Séries horaires lues sur une porteuse (ADR-0026). Une source maillée sert la
même série horaire à toutes les localités d'une maille : comme une série dense
(ADR-0017), une série horaire peut lire les mesures d'une porteuse de la même
famille (même source, grandeur, période, granularité et stockage), sans en
porter.

- La contrainte ``ck_series_metadonnees_serie_porteuse_dense`` devient
  ``ck_series_metadonnees_serie_porteuse_valide`` : une série qui lit une
  porteuse est dense ou horaire, comme sa porteuse.
- La garde ``kuma_controle_serie_porteuse`` admet une porteuse horaire, exige
  le même stockage et refuse qu'une série qui porte des mesures horaires lise
  une porteuse.
- Garde ``kuma_refus_mesure_horaire_alias`` : aucune mesure horaire pour une
  série qui lit une porteuse.
- Vue ``v_mesures_horaires`` : mesures horaires courantes, rendues à chaque
  série, porteuse ou non, comme ``v_mesures_journalieres`` pour le journalier.

Aucune donnée ne change. ``downgrade`` rend la contrainte et la garde de 0015
et retire la vue et la nouvelle garde ; il échoue si une série horaire lit
encore une porteuse.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMENTAIRE_PORTEUSE: str = (
    "Serie dont celle-ci lit les mesures (meme maille de la source, valeurs identiques), "
    "dense (ADR-0017) ou horaire (ADR-0026) ; NULL si la serie porte ses propres mesures."
)
COMMENTAIRE_PORTEUSE_0015: str = (
    "Serie dense dont celle-ci lit les mesures (meme maille de la source, "
    "valeurs identiques) ; NULL si la serie porte ses propres mesures."
)

VUE: str = """
CREATE VIEW v_mesures_horaires AS
SELECT s.id AS serie_id, m.id, m.instant_mesure, m.valeur, m.statut,
       m.niveau_confiance_derive, m.niveau_confiance_override, m.commentaire_editorial
FROM series_metadonnees s
JOIN mesures_ressource_horaires m ON m.serie_id = COALESCE(s.serie_porteuse_id, s.id)
WHERE m.valide_au IS NULL
"""

CONTROLE_PORTEUSE: str = """
BEGIN
    IF NEW.serie_porteuse_id IS NOT NULL THEN
        PERFORM 1 FROM series_metadonnees p
        WHERE p.id = NEW.serie_porteuse_id
          AND p.serie_porteuse_id IS NULL AND p.stockage = NEW.stockage
          AND (p.stockage = 'dense' OR p.granularite = 'horaire')
          AND p.grandeur_code = NEW.grandeur_code AND p.source_id = NEW.source_id
          AND p.periode_debut = NEW.periode_debut
          AND p.periode_fin IS NOT DISTINCT FROM NEW.periode_fin
          AND p.granularite IS NOT DISTINCT FROM NEW.granularite;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'série % : la porteuse % doit être une série porteuse, dense ou '
                'horaire, de même grandeur, source, période, granularité et stockage', NEW.code,
                NEW.serie_porteuse_id;
        END IF;
        -- Une série insérée n'a pas encore de mesure : le contrôle vaut pour une
        -- série existante qui se met à lire une porteuse.
        IF TG_OP = 'UPDATE' AND OLD.serie_porteuse_id IS DISTINCT FROM NEW.serie_porteuse_id
           AND EXISTS (SELECT 1 FROM mesures_ressource_horaires WHERE serie_id = NEW.id)
        THEN
            RAISE EXCEPTION 'série % : porte des mesures horaires, pas de lecture d''une porteuse',
                NEW.code;
        END IF;
    END IF;
    IF NEW.stockage = 'dense' AND (TG_OP = 'INSERT' OR OLD.stockage <> 'dense')
       AND EXISTS (SELECT 1 FROM mesures_ressource WHERE serie_id = NEW.id)
    THEN
        RAISE EXCEPTION 'série % : des mesures versionnées, pas de passage en stockage dense',
            NEW.code;
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
        RAISE EXCEPTION 'série % : porteuse lue par d''autres séries ou de mesures denses, '
            'famille et stockage figés', NEW.code;
    END IF;
    RETURN NEW;
END
"""

# Corps de la garde dans la migration 0015, rendu par le downgrade.
CONTROLE_PORTEUSE_0015: str = """
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
    IF NEW.stockage = 'dense' AND (TG_OP = 'INSERT' OR OLD.stockage <> 'dense')
       AND EXISTS (SELECT 1 FROM mesures_ressource WHERE serie_id = NEW.id)
    THEN
        RAISE EXCEPTION 'série % : des mesures versionnées, pas de passage en stockage dense',
            NEW.code;
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
"""

REFUS_MESURE_ALIAS: str = """
BEGIN
    PERFORM 1 FROM series_metadonnees WHERE id = NEW.serie_id AND serie_porteuse_id IS NOT NULL;
    IF FOUND THEN
        RAISE EXCEPTION 'série % : lit les mesures de sa porteuse, pas de mesure horaire propre',
            NEW.serie_id;
    END IF;
    RETURN NEW;
END
"""


def _fonction(nom: str, corps: str) -> str:
    return f"CREATE OR REPLACE FUNCTION {nom}() RETURNS trigger LANGUAGE plpgsql AS $${corps}$$"


def upgrade() -> None:
    op.drop_constraint("ck_series_metadonnees_serie_porteuse_dense", "series_metadonnees")
    op.create_check_constraint(
        "ck_series_metadonnees_serie_porteuse_valide",
        "series_metadonnees",
        "serie_porteuse_id IS NULL OR (serie_porteuse_id <> id "
        "AND (stockage = 'dense' OR granularite = 'horaire'))",
    )
    op.alter_column(
        "series_metadonnees",
        "serie_porteuse_id",
        comment=COMMENTAIRE_PORTEUSE,
        existing_comment=COMMENTAIRE_PORTEUSE_0015,
        existing_nullable=True,
    )
    op.execute(_fonction("kuma_controle_serie_porteuse", CONTROLE_PORTEUSE))
    op.execute(_fonction("kuma_refus_mesure_horaire_alias", REFUS_MESURE_ALIAS))
    op.execute(
        "CREATE TRIGGER trg_refus_mesure_horaire_alias "
        "BEFORE INSERT OR UPDATE OF serie_id ON mesures_ressource_horaires "
        "FOR EACH ROW EXECUTE FUNCTION kuma_refus_mesure_horaire_alias()"
    )
    op.execute(VUE)


def downgrade() -> None:
    op.execute("DROP VIEW v_mesures_horaires")
    op.execute("DROP TRIGGER trg_refus_mesure_horaire_alias ON mesures_ressource_horaires")
    op.execute("DROP FUNCTION kuma_refus_mesure_horaire_alias()")
    op.execute(_fonction("kuma_controle_serie_porteuse", CONTROLE_PORTEUSE_0015))
    op.alter_column(
        "series_metadonnees",
        "serie_porteuse_id",
        comment=COMMENTAIRE_PORTEUSE_0015,
        existing_comment=COMMENTAIRE_PORTEUSE,
        existing_nullable=True,
    )
    op.drop_constraint("ck_series_metadonnees_serie_porteuse_valide", "series_metadonnees")
    op.create_check_constraint(
        "ck_series_metadonnees_serie_porteuse_dense",
        "series_metadonnees",
        "serie_porteuse_id IS NULL OR (stockage = 'dense' AND serie_porteuse_id <> id)",
    )
