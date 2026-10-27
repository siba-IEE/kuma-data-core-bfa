"""aerosols_eac4

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27

Épaisseur optique des aérosols à 550 nm de la réanalyse CAMS EAC4 (ADR-0019)
aux 398 localités (47 provinces et 351 communes), 2005 à 2025, en stockage
dense : totale (``aod550``), des poussières désertiques
(``aod550_poussiere``) et de la matière organique (``aod550_organique``),
sans unité, moyenne du jour UTC des huit pas de 3 h, à la maille de 0,75° la
plus proche. Méthode ``reanalyse``, confiance B.

Trois grandeurs ajoutées au référentiel (stockées, unité ``sans_unite``),
retirées au ``downgrade``. La fiche de la source ``cams_eac4`` prend
l'épaisseur optique, les particules fines des communes (0017) et la date de
consultation des aérosols ; le ``downgrade`` lui rend son état de la 0013. 1 194 séries (398 localités, 3 grandeurs) de
7 670 jours ; 51 mailles servent les 398 localités : 153 séries porteuses,
3 213 lignes annuelles et 1 173 510 valeurs dans
``mesures_journalieres_denses``, les autres séries lisent les mesures de leur
porteuse.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_cams_eac4_journalier.py --famille aod --lot
localites``) et validées par ``series_denses.lire_series_denses``, points
interrogés comparés aux coordonnées en base ; la migration n'accède jamais au
réseau. Garde-fous : identité de la source, couverture exacte des localités,
nombre de séries, de lignes et de valeurs. ``downgrade`` supprime les
mesures, les séries, puis les grandeurs, et rend sa fiche à la source.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_AOD, LOT_LOCALITES, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 398
NB_SERIES_ATTENDU: int = 1_194
NB_LIGNES_ATTENDU: int = 3_213  # 3 × 51 porteuses × 21 années
NB_VALEURS_ATTENDU: int = 1_173_510  # 3 × 51 porteuses × 7 670 jours
ID_SOURCE: int = 15

# Grandeur : (libellé du référentiel, nom dans la note, description).
GRANDEURS: dict[str, tuple[str, str, str]] = {
    "aod550": (
        "Épaisseur optique des aérosols à 550 nm",
        "Épaisseur optique des aérosols à 550 nm (AOD)",
        "Épaisseur optique totale des aérosols à 550 nm, sans dimension : atténuation "
        "du rayonnement par l'ensemble des aérosols de la colonne (poussières, matière "
        "organique, carbone suie, sulfates, sels marins). Moyenne journalière des pas "
        "de 3 h de la réanalyse CAMS EAC4 (ADR-0019).",
    ),
    "aod550_poussiere": (
        "Épaisseur optique des poussières à 550 nm",
        "Épaisseur optique des poussières à 550 nm",
        "Épaisseur optique à 550 nm due aux poussières désertiques, sans dimension. "
        "Moyenne journalière des pas de 3 h de la réanalyse CAMS EAC4, qui n'assimile "
        "que l'épaisseur optique totale : le partage entre espèces vient du modèle "
        "(ADR-0019).",
    ),
    "aod550_organique": (
        "Épaisseur optique de la matière organique à 550 nm",
        "Épaisseur optique de la matière organique à 550 nm",
        "Épaisseur optique à 550 nm due à la matière organique, sans dimension. "
        "Moyenne journalière des pas de 3 h de la réanalyse CAMS EAC4, qui n'assimile "
        "que l'épaisseur optique totale : le partage entre espèces vient du modèle. "
        "Indicateur de fumées au sud, de novembre à mars seulement (ADR-0019).",
    ),
}
MODELE: str = (
    " La réanalyse n'assimile que l'épaisseur optique totale : le partage entre "
    "espèces vient du modèle."
)
MISES_EN_GARDE: dict[str, str] = {
    "aod550": (
        " Plus forte de mars à juin (0,52 en moyenne en mars sur les 398 localités), "
        "plus faible de novembre à janvier (0,21 en décembre) ; jusqu'à 3,14 le "
        "19 mars 2022 au nord, épisode de poussières. Les poussières en font 55 % en "
        "moyenne, la matière organique 31 %." + MODELE
    ),
    "aod550_poussiere": (
        " Plus forte au nord (0,23 en moyenne au nord de 13,5 °N, 0,14 au sud de "
        "10,5 °N) et de mars à juin (0,32 en moyenne en mars), avec l'harmattan et les "
        "soulèvements sahariens ; jusqu'à 2,56 le 19 mars 2022." + MODELE
    ),
    "aod550_organique": (
        MODELE + " Au sud, de novembre à mars, la matière organique porte les fumées des feux de "
        "végétation (jusqu'à 0,94 le 9 novembre 2014). De mars à juin et au nord, elle "
        "monte surtout avec les épisodes de poussières : elle n'y est pas un indicateur "
        "de feux."
    ),
}
# Fiche de la source : état laissé par la 0013, rendu au ``downgrade``, et état
# du Burkina Faso après les aérosols.
FICHE_0013: dict[str, Any] = {
    "date_consultation": date(2026, 10, 16),
    "doi": "10.24381/d58bbf47",
    "notes": (
        "Réanalyse de composition atmosphérique EAC4 (ECMWF Atmospheric Composition "
        "Reanalysis 4, CAMS), servie par l'ADS Copernicus depuis 2003. Fournit les PM2.5 et "
        "PM10 de surface (kg/m³, convertis en µg/m³) au pas de 3 h, ramenés par Kuma à la "
        "moyenne du jour UTC. Entrée du proxy de salissure HSU (taux_salissure_proxy), qui "
        "consomme les PM, pas l'AOD. Confiance B (réanalyse, pas mesure directe). Maille de "
        "0,75°. Au Burkina Faso : 2005-01-01 à 2025-12-31, aux 47 provinces (ADR-0015). "
        "Licence CC BY 4.0 ; attribution : « Contains modified Copernicus Atmosphere "
        "Monitoring Service information 2005-2025 ». Référence méthodologique : Inness et "
        "al. (2019), doi:10.5194/acp-19-3515-2019."
    ),
    "metadonnees": {"variables_ingerees": ["pm2.5 (pm2p5)", "pm10"]},
}
FICHE_0018: dict[str, Any] = {
    "date_consultation": date(2026, 10, 27),
    "doi": "10.24381/d58bbf47",
    "notes": (
        "Réanalyse de composition atmosphérique EAC4 (ECMWF Atmospheric Composition "
        "Reanalysis 4, CAMS), servie par l'ADS Copernicus depuis 2003. Fournit les PM2.5 et "
        "PM10 de surface (kg/m³, convertis en µg/m³) et l'épaisseur optique des aérosols à "
        "550 nm (totale, poussières, matière organique), au pas de 3 h, ramenés par Kuma à "
        "la moyenne du jour UTC. Les PM entrent dans le proxy de salissure HSU "
        "(taux_salissure_proxy) ; l'épaisseur optique n'entre encore dans aucun calcul. "
        "Seule l'épaisseur optique totale est assimilée (MODIS, et AATSR jusqu'en 2012) : "
        "le partage entre espèces vient du modèle. Confiance B (réanalyse, pas mesure "
        "directe). Maille de 0,75°. Au Burkina Faso : 2005-01-01 à 2025-12-31 ; PM aux "
        "47 provinces (ADR-0015) et aux 351 communes (ADR-0018), épaisseur optique aux "
        "398 localités (ADR-0019) ; consultée les 16 et 27 octobre 2026. Licence CC BY "
        "4.0 ; attribution : « Contains modified Copernicus Atmosphere Monitoring Service "
        "information 2005-2025 ». Référence méthodologique : Inness et al. (2019), "
        "doi:10.5194/acp-19-3515-2019."
    ),
    "metadonnees": {
        "variables_ingerees": ["pm2.5 (pm2p5)", "pm10", "aod550", "duaod550", "omaod550"]
    },
}


def _fiche(bind: sa.Connection, fiche: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Remplace la fiche ``depuis`` par ``fiche`` ; une fiche modifiée entre-temps reste."""
    return bind.execute(
        sa.text(
            "UPDATE sources SET date_consultation = :d, doi = :doi, notes = :notes, "
            "metadonnees = metadonnees || CAST(:m AS jsonb), modifie_le = now() "
            "WHERE id = :id AND notes = :notes_depuis"
        ),
        {
            "d": fiche["date_consultation"],
            "doi": fiche["doi"],
            "notes": fiche["notes"],
            "m": json.dumps(fiche["metadonnees"]),
            "id": ID_SOURCE,
            "notes_depuis": depuis["notes"],
        },
    ).rowcount


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    _, nom, _ = GRANDEURS[contrat.grandeur_code]
    partage = Counter(denses.representantes.values())
    notes: dict[str, str] = {}
    for code in denses.codes:
        n = partage[denses.representantes[code]]
        maille = (
            "propre à la localité dans le lot"
            if n == 1
            else f"identique pour les {n} localités de la même maille"
        )
        notes[code] = (
            f"{nom} : série journalière {contrat.source_libelle} (moyenne du jour UTC des "
            f"huit pas de 3 h, sans unité), {contrat.annee_debut}-{contrat.annee_fin}, "
            "réanalyse de composition atmosphérique de l'ECMWF. Lot des 398 localités "
            "(provinces et communes), stockage dense (ADR-0017). Confiance "
            f"{contrat.niveau_confiance}. Maille de 0,75° la plus proche ; série {maille}."
            f"{MISES_EN_GARDE[contrat.grandeur_code]}"
        )
    return notes


def _codes_series() -> list[str]:
    return [
        c.code_serie(code) for c in CONTRATS_AOD.values() for code, *_ in points_lot(LOT_LOCALITES)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "cams_eac4":
        raise RuntimeError(
            f"Migration 0018 : source id {ID_SOURCE} = {code_source!r}, 'cams_eac4' attendue."
        )
    sans_unite = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = 'sans_unite'")
    ).scalar_one()
    op.bulk_insert(
        sa.table(
            "grandeurs_referentiel",
            sa.column("code", sa.String),
            sa.column("libelle", sa.Text),
            sa.column("unite_id", sa.BigInteger),
            sa.column("famille", sa.String),
            sa.column("strategie_calcul", sa.String),
            sa.column("version_formule_actuelle", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {
                "code": code,
                "libelle": libelle,
                "unite_id": sans_unite,
                "famille": "F1",
                "strategie_calcul": "stockee",
                "version_formule_actuelle": 1,
                "description": description,
            }
            for code, (libelle, _, description) in GRANDEURS.items()
        ],
    )

    codes_loc = sorted(code for code, *_ in points_lot(LOT_LOCALITES))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0018 : {len(codes_loc)} localités, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0018 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_AOD.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT_LOCALITES))
        charges = charger_series_denses(
            bind, contrat, LOT_LOCALITES, loc, notes.__getitem__, "(sans unité)"
        )
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0018 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    if _fiche(bind, FICHE_0018, FICHE_0013) != 1:
        raise RuntimeError("Migration 0018 : fiche de cams_eac4 modifiée depuis la 0013.")
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    _fiche(bind, FICHE_0013, FICHE_0018)
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
    bind.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:c)"), {"c": list(GRANDEURS)}
    )
