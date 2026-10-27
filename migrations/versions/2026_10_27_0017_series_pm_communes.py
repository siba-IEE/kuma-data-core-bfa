"""series_pm_communes

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-27

Séries journalières brutes de particules fines CAMS EAC4 aux 351 communes,
2005 à 2025, en stockage dense (ADR-0017) : PM2.5 (``pm2_5``) et PM10
(``pm10``), en µg/m³, moyenne du jour UTC des huit pas de 3 h de la réanalyse,
à la maille de 0,75° la plus proche, comme aux provinces (ADR-0015). Méthode
``reanalyse``, confiance B.

Soit 702 séries (351 communes, 2 grandeurs) de 7 670 jours, statut ``brut``.
51 mailles servent les 351 communes : fichier et base ne stockent chaque série
distincte qu'une fois (102 séries porteuses, 2 142 lignes annuelles et
782 340 valeurs dans ``mesures_journalieres_denses``), les 600 autres séries
lisent les mesures de leur porteuse, et la note publique dit combien de
communes partagent la série. Avec la pluie journalière NASA POWER des
communes (0016), elles rendent le proxy de salissure et le PR réaliste
corrigé de la salissure calculables aux communes.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_cams_eac4_journalier.py --lot communes``) et
validées par ``series_denses.lire_series_denses``, points interrogés comparés
aux coordonnées des communes en base ; la migration n'accède jamais au
réseau. Garde-fous : identité de la source, couverture exacte des communes,
nombre de séries, de lignes et de valeurs. ``downgrade`` supprime les mesures
puis les séries.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_PM, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT: str = "communes"
NB_POINTS: int = 351
NB_SERIES_ATTENDU: int = 702
NB_LIGNES_ATTENDU: int = 2_142  # 2 × 51 porteuses × 21 années
NB_VALEURS_ATTENDU: int = 782_340  # 2 × 51 porteuses × 7 670 jours
ID_SOURCE: int = 15

NOMS: dict[str, str] = {
    "pm2_5": "Particules fines PM2.5",
    "pm10": "Particules PM10",
}
MISES_EN_GARDE: str = (
    " Pics en février et mars (harmattan) ; au sud et à l'est, en novembre et décembre,"
    " saison des feux de brousse, jusqu'à 1 143 µg/m³ de PM2.5 et 1 567 µg/m³ de PM10"
    " le 13 novembre 2013 à Madjoari. Sur l'ensemble des communes, 1 % des pas de 3 h"
    " sont servis à zéro par la réanalyse et gardés tels quels : 5,7 % des jours en"
    " comptent au moins un, ce qui abaisse leur moyenne."
)


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    partage = Counter(denses.representantes.values())
    notes: dict[str, str] = {}
    for code in denses.codes:
        n = partage[denses.representantes[code]]
        maille = (
            "propre à la commune dans le lot"
            if n == 1
            else f"identique pour les {n} communes de la même maille"
        )
        notes[code] = (
            f"{NOMS[contrat.grandeur_code]} : série journalière {contrat.source_libelle} "
            f"(moyenne du jour UTC des huit pas de 3 h, en µg/m³), {contrat.annee_debut}-"
            f"{contrat.annee_fin}, réanalyse de composition atmosphérique de l'ECMWF. Lot "
            f"« {LOT} », stockage dense (ADR-0017). Confiance {contrat.niveau_confiance}. "
            f"Maille de 0,75° la plus proche, à 33 km du point en médiane, 56 km au plus ; "
            f"série {maille}.{MISES_EN_GARDE}"
        )
    return notes


def _codes_series() -> list[str]:
    return [c.code_serie(code) for c in CONTRATS_PM.values() for code, *_ in points_lot(LOT)]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "cams_eac4":
        raise RuntimeError(
            f"Migration 0017 : source id {ID_SOURCE} = {code_source!r}, 'cams_eac4' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_lot(LOT))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0017 : {len(codes_loc)} communes, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0017 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_PM.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT))
        charges = charger_series_denses(bind, contrat, LOT, loc, notes.__getitem__, "µg/m³")
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0017 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


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
        bind.execute(
            sa.text("DELETE FROM mesures_journalieres_denses WHERE serie_id = ANY(:ids)"),
            {"ids": ids},
        )
        # Les séries qui lisent une porteuse d'abord, puis les porteuses.
        bind.execute(
            sa.text(
                "DELETE FROM series_metadonnees "
                "WHERE id = ANY(:ids) AND serie_porteuse_id IS NOT NULL"
            ),
            {"ids": ids},
        )
        bind.execute(sa.text("DELETE FROM series_metadonnees WHERE id = ANY(:ids)"), {"ids": ids})
