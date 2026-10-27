"""degenerescence_pixel

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-27

Dégénérescence de pixel (ADR-0016) aux 398 localités : pour chaque localité,
nombre d'autres localités du référentiel dont la série mensuelle GHI NASA POWER
(migration 0006, 1991-2025) est identique, c'est-à-dire qui lisent la même
maille CERES SYN1deg de 1°. GHI, DNI et DHI partagent cette grille : une ligne
par localité suffit.

Une ligne ``statique`` par localité dans ``grandeurs_metier`` (grandeur
``degenerescence_pixel``, déjà au référentiel), rattachée à la série GHI NASA
POWER mensuelle de la localité, confiance B, la liste des jumeaux dans
``commentaire_editorial``. L'endpoint ``/v1/grandeurs/incertitude_inter_source``
la lit avec les écarts de l'ADR-0012. Calcul depuis les mesures gravées, sans
réseau. 398 lignes seulement : le trigger d'audit reste actif et chaque ligne
est journalisée (la suspension de ``docs/architecture/03-audit.md`` vise les
migrations de masse). ``downgrade`` supprime ces lignes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANDEUR: str = "degenerescence_pixel"
NB_LOCALITES_ATTENDU: int = 398
NB_MAILLES_ATTENDU: int = 33
GRILLE: str = "maille CERES SYN1deg de 1° de NASA POWER"
CAVEAT: str = " Indicateur exact, tenu en confiance B : A est réservée aux mesures sol (ADR-0016)."


def _commentaire(jumeaux: list[str]) -> str:
    if not jumeaux:
        return f"Seule localité du référentiel dans sa {GRILLE}.{CAVEAT}"
    return (
        f"Partage sa {GRILLE} avec {len(jumeaux)} autre(s) localité(s) du référentiel : "
        f"{', '.join(jumeaux)}. Séries GHI, DNI et DHI identiques : ne pas les présenter "
        f"comme des mesures indépendantes.{CAVEAT}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    if (
        bind.execute(
            sa.text("SELECT 1 FROM grandeurs_referentiel WHERE code = :g"), {"g": GRANDEUR}
        ).first()
        is None
    ):
        raise RuntimeError(f"Migration 0014 : grandeur {GRANDEUR!r} absente du référentiel.")

    lignes = bind.execute(
        sa.text(
            """
            SELECT l.id AS localite_id, l.code, s.id AS serie_id,
                   extract(year FROM s.periode_debut)::int AS debut,
                   extract(year FROM s.periode_fin)::int AS fin,
                   md5(string_agg(m.valeur::text, ',' ORDER BY m.annee, m.mois)) AS empreinte,
                   count(*) AS n
            FROM series_metadonnees s
            JOIN sources so ON so.id = s.source_id
            JOIN localites l ON l.id = s.localite_id
            JOIN mesures_ressource_mensuelles m ON m.serie_id = s.id
            WHERE so.code = 'nasa_power' AND s.grandeur_code = 'ghi'
              AND s.granularite = 'mensuel' AND m.valide_au IS NULL
              AND m.statut <> 'deprecie'
            GROUP BY l.id, l.code, s.id, s.periode_debut, s.periode_fin
            ORDER BY l.code
            """
        )
    ).all()
    if len(lignes) != NB_LOCALITES_ATTENDU or {r.n for r in lignes} != {420}:
        raise RuntimeError(
            f"Migration 0014 : {len(lignes)} séries GHI NASA POWER mensuelles de "
            f"{sorted({r.n for r in lignes})} mois, {NB_LOCALITES_ATTENDU} de 420 attendues."
        )

    groupes: dict[str, list[str]] = defaultdict(list)
    for r in lignes:
        groupes[r.empreinte].append(r.code)
    if len(groupes) != NB_MAILLES_ATTENDU:
        raise RuntimeError(
            f"Migration 0014 : {len(groupes)} mailles, {NB_MAILLES_ATTENDU} attendues."
        )

    table = sa.table(
        "grandeurs_metier",
        sa.column("grandeur_code", sa.String),
        sa.column("localite_id", sa.BigInteger),
        sa.column("series_metadonnees_id", sa.BigInteger),
        sa.column("periode_type", sa.String),
        sa.column("annee_debut", sa.Integer),
        sa.column("annee_fin", sa.Integer),
        sa.column("mois", sa.Integer),
        sa.column("version_formule", sa.Integer),
        sa.column("valeur", sa.Numeric),
        sa.column("niveau_confiance_derive", sa.String),
        sa.column("commentaire_editorial", sa.Text),
    )
    lignes_metier = []
    for r in lignes:
        jumeaux = [c for c in groupes[r.empreinte] if c != r.code]
        lignes_metier.append(
            {
                "grandeur_code": GRANDEUR,
                "localite_id": r.localite_id,
                "series_metadonnees_id": r.serie_id,
                "periode_type": "statique",
                "annee_debut": r.debut,
                "annee_fin": r.fin,
                "mois": None,
                "version_formule": 1,
                "valeur": len(jumeaux),
                "niveau_confiance_derive": "B",
                "commentaire_editorial": _commentaire(jumeaux),
            }
        )
    op.bulk_insert(table, lignes_metier)


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM grandeurs_metier WHERE grandeur_code = :g").bindparams(g=GRANDEUR)
    )
