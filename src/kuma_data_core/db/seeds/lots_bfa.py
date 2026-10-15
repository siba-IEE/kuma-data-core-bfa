"""Lots de séries : points et contrats (ADR-0009 à ADR-0011, ADR-0013, ADR-0014).

Un **lot** est un ensemble de localités du référentiel dont les séries sont
demandées aux sources solaires sous le même contrat :

- ``provinces`` : les 47 provinces (niveau ``prefecture``, migration 0003) ;
- ``communes`` : les 350 départements et la commune de Ouagadougou (niveau
  ``commune``, migration 0004).

Les séries mensuelles portent sur les deux lots, les séries journalières NASA
POWER sur le seul lot ``provinces``, les séries horaires sur cinq points
pilotes du lot ``communes`` (la commune de Ouagadougou et quatre
départements). Chaque série couvre toute la période servie par sa source à
la date de l'ingestion (octobre 2026). Ces contrats sont figés
par les migrations 0006 (mensuel), 0007 et 0010 (journalier), 0008 (CAMS) et
0011 (horaire) : une autre source ou une autre période passera par de nouveaux
contrats et de nouveaux fichiers.
"""

from __future__ import annotations

from typing import Literal

from kuma_data_core.db.seeds.localites_bfa_departements_seed_data import (
    LOCALITES_SEED as _COMMUNES,
)
from kuma_data_core.db.seeds.localites_bfa_seed_data import LOCALITES_SEED as _LOCALITES
from kuma_data_core.db.seeds.series_csv import ContratSerie

LOTS: tuple[str, ...] = ("provinces", "communes")
LOTS_JOURNALIERS: tuple[str, ...] = ("provinces",)
_NIVEAUX: dict[str, str] = {"provinces": "prefecture", "communes": "commune"}


def points_lot(lot: str) -> list[tuple[str, str, float, float]]:
    """Localités d'un lot : ``(code, nom, latitude, longitude)``, triées par code."""
    niveau = _NIVEAUX[lot]
    entrees = [e for e in (*_LOCALITES, *_COMMUNES) if e["type_localite"] == niveau]
    sans_coord = [e["code"] for e in entrees if e["latitude"] is None or e["longitude"] is None]
    if sans_coord:
        raise ValueError(f"Lot {lot!r} : localité(s) sans coordonnées : {sans_coord!r}.")
    return sorted(
        (e["code"], e["nom"], float(e["latitude"]), float(e["longitude"])) for e in entrees
    )


def _nasa(
    grandeur: str, debut: int, granularite: Literal["mensuel", "journalier"] = "mensuel"
) -> ContratSerie:
    bornes = {"mensuel": BORNES, "journalier": BORNES_JOURNALIERES}[granularite]
    return ContratSerie(
        source_code="nasa_power",
        source_id=1,
        source_libelle="NASA POWER",
        prefixe_code=f"nasa_power_{grandeur}_{granularite}",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire",
        annee_debut=debut,
        annee_fin=2025,
        borne_max=bornes[grandeur],
        granularite=granularite,
    )


def _pvgis(
    source: str, sid: int, libelle: str, prefixe: str, methode: str, grandeur: str
) -> ContratSerie:
    return ContratSerie(
        source_code=source,
        source_id=sid,
        source_libelle=libelle,
        prefixe_code=f"{prefixe}_{grandeur}_mensuel",
        grandeur_code=grandeur,
        methode_collecte=methode,
        annee_debut=2005,
        annee_fin=2023,
        borne_max=BORNES[grandeur],
    )


def _cams(grandeur: str) -> ContratSerie:
    return ContratSerie(
        source_code="cams_radiation",
        source_id=13,
        source_libelle="CAMS Radiation",
        prefixe_code=f"cams_{grandeur}_mensuel",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire",
        annee_debut=2005,
        annee_fin=2025,
        borne_max=BORNES[grandeur],
    )


# Paramètre NASA POWER de chaque grandeur.
PARAMETRES_NASA: dict[str, str] = {
    "ghi": "ALLSKY_SFC_SW_DWN",
    "dni": "ALLSKY_SFC_SW_DNI",
    "dhi": "ALLSKY_SFC_SW_DIFF",
}

# Bornes de plausibilité (kWh/m²/jour, moyenne journalière du mois) : au-dessus
# des maxima servis par les sources sur le Burkina Faso (GHI 7,83, DNI 8,23,
# DHI 3,89) et sous le plafond physique par ciel clair à ces latitudes.
BORNES: dict[str, float] = {"ghi": 8.5, "dni": 10.0, "dhi": 6.0}
# Bornes journalières (kWh/m²/jour, total du jour) : au-dessus des maxima servis
# par NASA POWER aux provinces (GHI 8,39, DNI 9,29, DHI 5,14) et sous le plafond
# physique d'une journée claire à ces latitudes.
BORNES_JOURNALIERES: dict[str, float] = {"ghi": 9.0, "dni": 11.0, "dhi": 6.5}

# NASA POWER : GHI depuis 1991 (normale 1991-2020) ; DNI servi depuis 2001 ;
# DHI en rupture avant 2001. Fin : 2025, dernière année complète servie.
CONTRATS_NASA: dict[str, ContratSerie] = {
    "ghi": _nasa("ghi", 1991),
    "dni": _nasa("dni", 2001),
    "dhi": _nasa("dhi", 2001),
}
# PVGIS (MRcalc v5_3) : 2005 à 2023, dernière année servie.
CONTRATS_SARAH3: dict[str, ContratSerie] = {
    g: _pvgis("sarah3_monthly", 11, "SARAH-3 (PVGIS)", "sarah3", "modele_satellitaire", g)
    for g in ("ghi", "dni")
}
CONTRATS_ERA5: dict[str, ContratSerie] = {
    g: _pvgis("era5_pvgis", 16, "ERA5 (PVGIS)", "era5", "reanalyse", g) for g in ("ghi", "dni")
}

# CAMS Radiation (ADS) : servi depuis février 2004 ; 2005 à 2025, années
# complètes. Lot distinct des contrats mensuels de la migration 0006.
CONTRATS_CAMS: dict[str, ContratSerie] = {g: _cams(g) for g in ("ghi", "dni", "dhi")}

# NASA POWER journalier : mêmes périodes que le mensuel.
CONTRATS_NASA_JOURNALIERS: dict[str, ContratSerie] = {
    "ghi": _nasa("ghi", 1991, "journalier"),
    "dni": _nasa("dni", 2001, "journalier"),
    "dhi": _nasa("dhi", 2001, "journalier"),
}

# Météo journalière NASA POWER (réanalyse MERRA-2, ADR-0013) : paramètre,
# bornes basse et haute (°C, %, mm/jour). Période 1991-2025, celle du GHI
# journalier, dont les calculs du moteur font des séries compagnes.
METEO_NASA: dict[str, tuple[str, float, float]] = {
    "t2m": ("T2M", 0.0, 50.0),
    "rh2m": ("RH2M", 0.0, 100.0),
    "precipitation": ("PRECTOTCORR", 0.0, 500.0),
}
CONTRATS_METEO_JOURNALIERS: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="nasa_power",
        source_id=1,
        source_libelle="NASA POWER",
        prefixe_code=f"nasa_power_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="reanalyse",
        annee_debut=1991,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="journalier",
        borne_min=borne_min,
    )
    for grandeur, (_, borne_min, borne_max) in METEO_NASA.items()
}

# Séries horaires NASA POWER (ADR-0014) aux cinq points pilotes : Ouagadougou et
# les quatre villes des stations sol ESMAP/WAPP. 2021-2025, valeur moyenne de
# l'heure qui commence à l'instant (UTC). Paramètre, méthode, bornes basse et
# haute (W/m² pour le rayonnement, °C pour la température).
LOT_HORAIRE: str = "pilotes"
PILOTES_HORAIRES: tuple[str, ...] = (
    "bfa_com_ouagadougou",
    "bfa_dep_dedougou",
    "bfa_dep_dori",
    "bfa_dep_kaya",
    "bfa_dep_koupela",
)
HORAIRE_NASA: dict[str, tuple[str, str, float, float]] = {
    "ghi": ("ALLSKY_SFC_SW_DWN", "modele_satellitaire", 0.0, 1400.0),
    "dni": ("ALLSKY_SFC_SW_DNI", "modele_satellitaire", 0.0, 1400.0),
    "dhi": ("ALLSKY_SFC_SW_DIFF", "modele_satellitaire", 0.0, 900.0),
    "t2m": ("T2M", "reanalyse", -5.0, 55.0),
}
CONTRATS_HORAIRES: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="nasa_power",
        source_id=1,
        source_libelle="NASA POWER",
        prefixe_code=f"nasa_power_{grandeur}_horaire",
        grandeur_code=grandeur,
        methode_collecte=methode,
        annee_debut=2021,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="horaire",
        borne_min=borne_min,
    )
    for grandeur, (_, methode, borne_min, borne_max) in HORAIRE_NASA.items()
}


def points_pilotes() -> list[tuple[str, str, float, float]]:
    """Points pilotes de l'horaire : ``(code, nom, latitude, longitude)``, triés par code."""
    return [p for p in points_lot("communes") if p[0] in PILOTES_HORAIRES]


# Contrats mensuels de la migration 0006, dans son ordre d'insertion.
CONTRATS_MENSUELS: tuple[ContratSerie, ...] = (
    *CONTRATS_NASA.values(),
    *CONTRATS_SARAH3.values(),
    *CONTRATS_ERA5.values(),
)
