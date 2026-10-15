"""qc_horaire_pilotes

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15

Contrôle qualité horaire, doctrine v1 (``docs/methodologie/doctrine-qc-horaire.md``,
ADR-0014), appliqué aux 20 séries horaires des cinq points pilotes
(migration 0011) :

- plausibilité physique de chaque variable (seuils BSRN « physiquement
  possible », test dur, et « extrêmement rare », drapeau) ;
- fermeture ``GHI / (DHI + DNI·μ0)`` et ratio diffus ``DHI / GHI`` (drapeaux).

L'instant stocké désigne le début de l'heure moyennée (convention de
stockage, ``services.horaire.DECALAGE_MILIEU_HEURE``) : la géométrie solaire
est calculée au milieu de l'heure. Une ligne qui passe les
tests durs passe de ``brut`` à ``valide_auto``, avec ses drapeaux éventuels
dans ``commentaire_editorial`` ; une ligne rejetée reste ``brut`` avec le
motif. La confiance reste B. Le trigger d'audit des mesures est suspendu le
temps de cette requalification algorithmique de masse
(``docs/architecture/03-audit.md``). ``downgrade`` remet en ``brut``, sans
commentaire, les lignes que le contrôle a qualifiées et que personne n'a
reprises depuis.

La migration exécute le code du contrôle qualité : son garde-fou exige la
doctrine v1. Le passage à une v2 devra figer la v1 pour cette migration, sans
quoi une base neuve ne monterait plus.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_HORAIRES, points_pilotes
from kuma_data_core.editorial.statuts import transition_autorisee
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import VERSION_DOCTRINE_QC, executer_qc_horaire

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_LIGNES_ATTENDU: int = 876_480  # 5 points × 4 grandeurs × 43 824 heures
TABLE_MESURES: str = "mesures_ressource_horaires"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource_horaires"


def _codes_series() -> list[str]:
    return [c.code_serie(code) for c in CONTRATS_HORAIRES.values() for code, *_ in points_pilotes()]


def upgrade() -> None:
    bind = op.get_bind()
    if VERSION_DOCTRINE_QC != "v1" or not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 0012 : doctrine QC v1 et transition brut -> valide_auto.")

    verdicts = []
    with Session(bind=bind) as session:
        for code, _, latitude, longitude in points_pilotes():
            series = {
                row.grandeur_code: row.id
                for row in bind.execute(
                    sa.text(
                        "SELECT s.grandeur_code, s.id FROM series_metadonnees s "
                        "JOIN localites l ON l.id = s.localite_id "
                        "WHERE l.code = :c AND s.code = ANY(:codes)"
                    ),
                    {"c": code, "codes": _codes_series()},
                ).all()
            }
            if set(series) != set(CONTRATS_HORAIRES):
                raise RuntimeError(
                    f"Migration 0012 : séries horaires de {code} : {sorted(series)!r}."
                )
            verdicts += executer_qc_horaire(
                session, series, latitude, longitude, decalage=DECALAGE_MILIEU_HEURE
            )
    if len(verdicts) != NB_LIGNES_ATTENDU:
        raise RuntimeError(
            f"Migration 0012 : {len(verdicts)} verdicts, {NB_LIGNES_ATTENDU} attendus."
        )
    bilan = Counter(v.statut_cible for v in verdicts)
    logging.getLogger("alembic.runtime.migration").info(
        "QC horaire %s : %d lignes, %d valide_auto (dont %d avec drapeaux), %d rejetées",
        VERSION_DOCTRINE_QC,
        len(verdicts),
        bilan["valide_auto"],
        sum(1 for v in verdicts if v.statut_cible == "valide_auto" and v.flags),
        len(verdicts) - bilan["valide_auto"],
    )

    bind.execute(
        sa.text(
            "CREATE TEMPORARY TABLE qc_verdicts "
            "(id bigint PRIMARY KEY, statut varchar(16) NOT NULL, commentaire text NOT NULL)"
        )
    )
    pilote = bind.connection.driver_connection
    with (
        pilote.cursor() as curseur,  # type: ignore[union-attr]
        curseur.copy("COPY qc_verdicts (id, statut, commentaire) FROM STDIN") as flux,
    ):
        for verdict in verdicts:
            flux.write_row((verdict.row_id, verdict.statut_cible, verdict.commentaire()))

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    mises_a_jour = bind.execute(
        sa.text(
            f"UPDATE {TABLE_MESURES} m SET statut = v.statut, "
            "commentaire_editorial = v.commentaire, modifie_le = now() "
            "FROM qc_verdicts v WHERE m.id = v.id AND m.statut = 'brut'"
        )
    ).rowcount
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(sa.text("DROP TABLE qc_verdicts"))
    if mises_a_jour != NB_LIGNES_ATTENDU:
        raise RuntimeError(
            f"Migration 0012 : {mises_a_jour} lignes requalifiées, {NB_LIGNES_ATTENDU} attendues."
        )
    op.execute(f"ANALYZE {TABLE_MESURES}")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(
        sa.text(
            f"UPDATE {TABLE_MESURES} SET statut = 'brut', commentaire_editorial = NULL, "
            "modifie_le = now() "
            "WHERE serie_id IN (SELECT id FROM series_metadonnees WHERE code = ANY(:codes)) "
            "AND statut IN ('brut', 'valide_auto') AND commentaire_editorial LIKE :marque"
        ),
        {"codes": _codes_series(), "marque": f"[QC {VERSION_DOCTRINE_QC}]%"},
    )
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
