"""era5_land_journalier

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-28

Météo et rayonnement journaliers ERA5-Land (ADR-0024) aux 398 localités
(47 provinces et 351 communes), 2005 à 2025, en stockage dense : température à
2 m (moyenne, minimum et maximum du jour), point de rosée, pression de surface,
vent à 10 m (vitesse moyenne et direction du vent moyen), pluie et rayonnement
global, agrégés du jour UTC à partir des valeurs horaires de la réanalyse
(maille de 0,1°). Méthode ``reanalyse``, confiance B.

3 582 séries (398 localités, 9 grandeurs) de 7 670 jours ; les localités d'une
même maille partagent la série de leur porteuse. La fiche de la source
``ecmwf_era5_land``, restée celle du dépôt d'origine, passe au Burkina Faso ;
le ``downgrade`` la rend.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_era5_land_journalier.py``) et validées par
``series_denses.lire_series_denses``, points interrogés comparés aux
coordonnées en base ; la migration n'accède jamais au réseau. Garde-fous :
identité de la source, couverture exacte des localités, nombre de séries, de
lignes et de valeurs.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_ERA5_LAND_JOURNALIERS,
    LOT_LOCALITES,
    points_lot,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 398
NB_SERIES_ATTENDU: int = 3_582
NB_LIGNES_ATTENDU: int = 70_119  # 9 × 371 porteuses × 21 années
NB_VALEURS_ATTENDU: int = 25_610_130  # 3 339 porteuses × 7 670 jours
ID_SOURCE: int = 12

# Grandeur : (nom, valeur du jour, unité).
GRANDEURS: dict[str, tuple[str, str, str]] = {
    "t2m": ("Température de l'air à 2 m", "moyenne des heures du jour", "°C"),
    "t2m_min": ("Température minimale de l'air à 2 m", "minimum horaire du jour", "°C"),
    "t2m_max": ("Température maximale de l'air à 2 m", "maximum horaire du jour", "°C"),
    "point_rosee_2m": ("Point de rosée à 2 m", "moyenne des heures du jour", "°C"),
    "pression_surface": ("Pression de surface", "moyenne des heures du jour", "kPa"),
    "vent_10m": ("Vent à 10 m", "moyenne des vitesses horaires du jour", "m/s"),
    "direction_vent_10m": (
        "Direction du vent à 10 m",
        "direction d'où souffle le vent moyen vectoriel du jour",
        "degrés depuis le nord",
    ),
    "precipitation": ("Pluie", "cumul des heures du jour", "mm/jour"),
    "ghi": (
        "Rayonnement global horizontal (GHI)",
        "cumul des heures du jour",
        "kWh/m²/jour",
    ),
}
# Origine des valeurs à la maille de 0,1° (Muñoz-Sabater et al. 2021).
ALTITUDE: str = " Ramenée par le modèle à l'altitude de la maille de 0,1°."
FORCAGE: str = (
    " Forçage d'ERA5 (maille de 31 km environ) interpolé sur la maille de 0,1°, sans "
    "correction d'altitude ni d'observation."
)
# Écarts à NASA POWER, 2005-2025, jours communs : aux communes pour la température
# moyenne, la pluie et le GHI, aux 398 localités pour les autres grandeurs.
MISES_EN_GARDE: dict[str, str] = {
    "t2m": ALTITUDE + " Plus chaude que NASA POWER de 0,8 °C en moyenne aux communes (corrélation "
    "journalière 0,90).",
    "t2m_min": ALTITUDE
    + " Plus chaude que NASA POWER de 1,2 °C en moyenne (corrélation journalière 0,90).",
    "t2m_max": ALTITUDE
    + " Égale à NASA POWER à 0,1 °C près en moyenne (corrélation journalière 0,90).",
    "point_rosee_2m": ALTITUDE
    + " Plus basse que NASA POWER de 1,4 °C en moyenne (corrélation journalière 0,96) : "
    "de 1,5 °C les jours où NASA POWER sert un point de rosée, de 0,7 °C ceux où il sert "
    "un point de givre.",
    "pression_surface": (
        " Pression à l'altitude de la maille de 0,1° ; égale à NASA POWER à 0,1 kPa près en "
        "moyenne (corrélation journalière 0,87)."
    ),
    "vent_10m": FORCAGE
    + " Plus faible que NASA POWER de 0,7 m/s en moyenne (corrélation journalière 0,78) ; "
    "seules les stations sol départageront.",
    "direction_vent_10m": FORCAGE
    + " Moyenne vectorielle : par vents tournants, la direction du vent moyen peut "
    "s'écarter de la direction la plus fréquente. Écart médian de 13° à la direction de "
    "NASA POWER.",
    "precipitation": FORCAGE
    + " Un tiers de pluie de moins que NASA POWER aux communes : 611 mm par an contre 912 "
    "(323 contre 614 au nord de 13,5 °N, 861 contre 1 168 au sud de 10,5 °N), et 87 jours "
    "à plus de 1 mm par an contre 139 ; le rapport va de 0,56 à 0,74 selon l'année, 0,42 "
    "en mai. Corrélation journalière 0,45. Seules les stations sol départageront les deux "
    "sources. Le 31 décembre 2025 omet l'heure de 23 h à minuit, hors de la période "
    "servie ; les 23 autres heures de ce jour n'apportent pas 0,01 mm.",
    "ghi": FORCAGE
    + " Le GHI dépasse en moyenne de 0,4 % celui d'ERA5 servi par PVGIS (ADR-0009), avec "
    "une corrélation mensuelle de 0,998. Proche en moyenne de CAMS (+0,7 %) et de SARAH-3 (-3,3 %), mais peu corrélé "
    "jour à jour (0,57 avec CAMS, 0,64 avec SARAH-3) : les nuages du modèle ne suivent "
    "qu'en partie ceux observés. Source de comparaison, pas de référence.",
}
# Jour UTC : valeurs instantanées ou cumuls datés de la fin de leur heure.
JOUR_INSTANTANE: str = " Jour compté en temps universel : valeurs horaires de 0 h à 23 h UTC."
JOUR_CUMUL: str = (
    " Jour compté en temps universel : cumul des heures de 0 h à 24 h UTC, chacune datée "
    "de la fin de son heure."
)
CUMULS: frozenset[str] = frozenset({"precipitation", "ghi"})

# Fiche de la source : état d'origine, rendu au ``downgrade``, et état du
# Burkina Faso. Seules les clés de métadonnées modifiées y figurent.
FICHE_ORIGINE: dict[str, Any] = {
    "date_consultation": date(2026, 6, 16),
    "annee_publication": 2019,
    "url": "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
    "doi": "10.24381/cds.68d2bb30",
    "notes": (
        "Réanalyse land-only haute résolution, replay de la composante terrestre d'ERA5 "
        "forcée par ERA5 (interpolation MIR depuis 2020). Référence : Muñoz-Sabater et al. "
        "(2021), « ERA5-Land: a state-of-the-art global reanalysis dataset for land "
        "applications », ESSD 13, 4349-4380, DOI 10.5194/essd-13-4349-2021. Distribution CDS "
        "Copernicus. Le DOI 10.24381/cds.68d2bb30 cible le produit monthly-means ; le produit "
        "hourly (agrégé en journalier côté Kuma) porte un DOI distinct. Attribution requise "
        "(CC-BY) : « Generated using Copernicus Climate Change Service Information [Year] ». "
        "Vague 4 Lot A : co-localisation (D-29) et altitude (D-24) sur les 6 villes pilotes. "
        "Consulté le 2026-06-16."
    ),
    "metadonnees": {"produits_utilises": ["monthly-means", "hourly (agrege en journalier)"]},
}
FICHE_0023: dict[str, Any] = {
    "date_consultation": date(2026, 10, 28),
    "annee_publication": 2025,
    "url": "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries",
    "doi": "10.24381/ee82e357",
    "notes": (
        "Réanalyse ERA5-Land du CEPMMT pour le Copernicus Climate Change Service (C3S) : "
        "composante terrestre d'ERA5, rejouée sur une maille de 0,1° (11 km environ) et forcée "
        "par l'atmosphère d'ERA5 (Muñoz-Sabater et al. 2021, « ERA5-Land: a state-of-the-art "
        "global reanalysis dataset for land applications », ESSD 13:4349-4380). Seules la "
        "température, l'humidité et la pression y sont ramenées à l'altitude de la maille ; "
        "la pluie, le rayonnement et le vent sont ceux d'ERA5 (31 km environ), interpolés. "
        "Jeu « ERA5-Land hourly time-series » du CDS Copernicus (DOI 10.24381/ee82e357), "
        "interrogé au point de chaque localité, qui reçoit la maille de 0,1° la plus proche. "
        "Au Burkina Faso, 2005-2025, aux 398 localités : température à 2 m (moyenne, minimum "
        "et maximum), point de rosée, pression de surface, vent à 10 m (vitesse et "
        "direction), pluie et rayonnement global journaliers, agrégés du jour UTC "
        "(ADR-0024), consultés les 27 et 28 octobre 2026. Confiance B (réanalyse). Licence "
        "CC BY 4.0 ; attribution : « Contains modified Copernicus Climate Change Service "
        "information 2005-2025 »."
    ),
    "metadonnees": {"produits_utilises": ["hourly time-series (agrégé en journalier)"]},
}


def _fiche(bind: sa.Connection, fiche: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Remplace la fiche ``depuis`` par ``fiche`` ; une fiche modifiée entre-temps reste."""
    return bind.execute(
        sa.text(
            "UPDATE sources SET date_consultation = :d, annee_publication = :annee, url = :url, "
            "doi = :doi, notes = :notes, metadonnees = metadonnees || CAST(:m AS jsonb), "
            "modifie_le = now() WHERE id = :id AND notes = :notes_depuis"
        ),
        {
            "d": fiche["date_consultation"],
            "annee": fiche["annee_publication"],
            "url": fiche["url"],
            "doi": fiche["doi"],
            "notes": fiche["notes"],
            "m": json.dumps(fiche["metadonnees"]),
            "id": ID_SOURCE,
            "notes_depuis": depuis["notes"],
        },
    ).rowcount


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    nom, valeur, unite = GRANDEURS[contrat.grandeur_code]
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
            f"{nom} : série journalière {contrat.source_libelle} ({valeur}, en {unite}), "
            f"{contrat.annee_debut}-{contrat.annee_fin}, réanalyse ERA5-Land du CEPMMT "
            "(maille de 0,1°) au point de la localité. Lot des 398 localités (provinces et "
            f"communes), stockage dense (ADR-0017). Confiance {contrat.niveau_confiance}. "
            f"Série {maille}.{MISES_EN_GARDE[contrat.grandeur_code]}"
            f"{JOUR_CUMUL if contrat.grandeur_code in CUMULS else JOUR_INSTANTANE}"
        )
    return notes


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_ERA5_LAND_JOURNALIERS.values()
        for code, *_ in points_lot(LOT_LOCALITES)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "ecmwf_era5_land":
        raise RuntimeError(
            f"Migration 0023 : source id {ID_SOURCE} = {code_source!r}, 'ecmwf_era5_land' attendue."
        )
    codes_loc = sorted(code for code, *_ in points_lot(LOT_LOCALITES))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0023 : {len(codes_loc)} localités, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0023 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_ERA5_LAND_JOURNALIERS.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT_LOCALITES))
        charges = charger_series_denses(
            bind,
            contrat,
            LOT_LOCALITES,
            loc,
            notes.__getitem__,
            GRANDEURS[contrat.grandeur_code][2],
        )
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0023 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    if _fiche(bind, FICHE_0023, FICHE_ORIGINE) != 1:
        raise RuntimeError("Migration 0023 : fiche de ecmwf_era5_land modifiée depuis l'origine.")
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    _fiche(bind, FICHE_ORIGINE, FICHE_0023)
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
