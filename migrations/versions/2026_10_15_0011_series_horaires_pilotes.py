"""series_horaires_pilotes

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-15

Séries horaires brutes NASA POWER (ADR-0014) aux cinq points pilotes :
Ouagadougou et les villes des stations sol ESMAP/WAPP (Dédougou, Dori, Kaya,
Koupéla), 2021 à 2025 : GHI, DNI et DHI (moyenne de l'heure en W/m²) et
température à 2 m (°C). Chaque valeur est datée du début de l'heure qu'elle
moyenne, en UTC.

Soit 20 séries (5 points, 4 grandeurs) de 43 824 heures, confiance B, statut
``brut``, dans ``mesures_ressource_horaires``. Valeurs lues dans les CSV gzip
de ``seeds/donnees/`` (produits hors ligne par
``scripts/ingest_nasa_power_horaire.py``) et validées par
``series_csv.lire_series_horaires`` ; la migration n'accède jamais au réseau.
Mesures chargées par ``COPY``, trigger d'audit des mesures suspendu le temps du
déversement et de sa suppression (``docs/architecture/03-audit.md``,
migrations de masse). Garde-fous : identité de la source, couverture exacte des
points, nombre de mesures par grandeur et total. Le contrôle qualité est
l'objet de la migration 0012. ``downgrade`` supprime les mesures puis les
séries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_HORAIRES, LOT_HORAIRE, points_pilotes
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series_horaires

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 5
NB_SERIES_ATTENDU: int = 20
NB_MESURES_ATTENDU: int = 876_480  # 5 × 4 × 43 824
TABLE_MESURES: str = "mesures_ressource_horaires"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource_horaires"

RAYONNEMENT: str = "Wh/m² sur l'heure, soit sa moyenne en W/m²"
VALEURS: dict[str, str] = {
    "ghi": RAYONNEMENT,
    "dni": RAYONNEMENT,
    "dhi": RAYONNEMENT,
    "t2m": "moyenne de l'heure en °C",
}
MISES_EN_GARDE: dict[str, str] = {
    "ghi": "",
    "dni": (
        " Ce DNI ne referme pas le GHI : sur 2021-2025, DHI + DNI·cos z reste de 5,9 à 6,9 %"
        " sous le GHI selon le point pilote. Le POA horaire calculé par l'API reconstruit le"
        " direct à partir du GHI et du DHI."
    ),
    "dhi": "",
    "t2m": "",
}


def _note(contrat: ContratSerie) -> str:
    origine = "réanalyse MERRA-2" if contrat.methode_collecte == "reanalyse" else "CERES SYN1deg"
    return (
        f"{contrat.grandeur_code.upper()} horaire {contrat.source_libelle} "
        f"({VALEURS[contrat.grandeur_code]} ; heure commençant à l'instant indiqué, UTC), "
        f"{contrat.annee_debut}-{contrat.annee_fin}, {origine}. Points pilotes (ADR-0014). "
        f"Confiance {contrat.niveau_confiance}.{MISES_EN_GARDE[contrat.grandeur_code]}"
    )


def _codes_series() -> list[str]:
    return [c.code_serie(code) for c in CONTRATS_HORAIRES.values() for code, *_ in points_pilotes()]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = 1")
    ).scalar_one_or_none()
    if code_source != "nasa_power":
        raise RuntimeError(
            f"Migration 0011 : source id 1 = {code_source!r}, 'nasa_power' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_pilotes())
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(
            f"Migration 0011 : {len(codes_loc)} points pilotes, {NB_POINTS} attendus."
        )
    loc = {
        row.code: row.id
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0011 : localité(s) introuvable(s) : {manquants!r}.")

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
    for contrat in CONTRATS_HORAIRES.values():
        series = lire_series_horaires(contrat, LOT_HORAIRE)
        if [s["localite_code"] for s in series] != codes_loc:
            raise RuntimeError(
                f"Migration 0011 : {contrat.nom_fichier(LOT_HORAIRE)} ne couvre pas exactement le lot."
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
            (serie_id[s["code"]], instant, valeur, "brut", contrat.niveau_confiance)
            for s in series
            for instant, valeur in s["mesures"]
        ]
        if len(lignes) != NB_POINTS * contrat.nb_heures:
            raise RuntimeError(
                f"Migration 0011 : {contrat.prefixe_code} : {len(lignes)} mesures, "
                f"{NB_POINTS * contrat.nb_heures} attendues."
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
            f"Migration 0011 : {nb_series} séries et {nb_mesures} mesures, "
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
