"""Lots de séries : points et contrats (ADR-0009 à ADR-0011, ADR-0013 à ADR-0023).

Un **lot** est un ensemble de localités du référentiel dont les séries sont
demandées aux sources sous le même contrat :

- ``provinces`` : les 47 provinces (niveau ``prefecture``, migration 0003) ;
- ``communes`` : les 350 départements et la commune de Ouagadougou (niveau
  ``commune``, migration 0004) ;
- ``localites`` : les 398 localités des deux lots (ADR-0017).

Les séries mensuelles portent sur les provinces et les communes. Les séries
journalières portent sur les provinces, sur les communes ou sur les
398 localités, en stockage dense hors des provinces. Les séries horaires
portent sur cinq points pilotes du lot ``communes`` (la commune de
Ouagadougou et quatre départements). Chaque contrat fixe sa période ; les
migrations qui chargent ses fichiers le figent : une autre source ou une
autre période passera par de nouveaux contrats et de nouveaux fichiers.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from kuma_data_core.db.seeds.localites_bfa_departements_seed_data import (
    LOCALITES_SEED as _COMMUNES,
)
from kuma_data_core.db.seeds.localites_bfa_seed_data import LOCALITES_SEED as _LOCALITES
from kuma_data_core.db.seeds.series_csv import ContratSerie

LOTS: tuple[str, ...] = ("provinces", "communes")
LOTS_JOURNALIERS: tuple[str, ...] = ("provinces", "communes", "localites")
# Lot dense des 398 localités : les 47 provinces et les 351 communes (ADR-0017).
LOT_LOCALITES: str = "localites"
_NIVEAUX: dict[str, tuple[str, ...]] = {
    "provinces": ("prefecture",),
    "communes": ("commune",),
    LOT_LOCALITES: ("prefecture", "commune"),
}


def points_lot(lot: str) -> list[tuple[str, str, float, float]]:
    """Localités d'un lot : ``(code, nom, latitude, longitude)``, triées par code."""
    niveaux = _NIVEAUX[lot]
    entrees = [e for e in (*_LOCALITES, *_COMMUNES) if e["type_localite"] in niveaux]
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

# CAMS Radiation journalier aux 398 localités (lot ``localites``, ADR-0020) : total
# du jour UTC en kWh/m²/jour, tous temps et par ciel clair. Colonne du CSV de
# l'ADS, borne basse et borne haute, au-dessus des maxima servis (GHI 8,34, DNI
# 10,14, DHI 4,61, ciel clair 8,36 et 10,17). Le DNI d'un jour couvert peut
# être nul ; les autres grandeurs restent strictement positives.
CAMS_JOURNALIER: dict[str, tuple[str, float | None, float]] = {
    "ghi": ("GHI", None, 9.0),
    "dni": ("BNI", 0.0, 11.0),
    "dhi": ("DHI", None, 6.5),
    "ghi_ciel_clair": ("Clear sky GHI", None, 9.0),
    "dni_ciel_clair": ("Clear sky BNI", None, 11.0),
}
COLONNES_CAMS_JOURNALIERES: dict[str, str] = {g: c for g, (c, _, _) in CAMS_JOURNALIER.items()}
CONTRATS_CAMS_JOURNALIERS: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="cams_radiation",
        source_id=13,
        source_libelle="CAMS Radiation",
        prefixe_code=f"cams_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire",
        annee_debut=2005,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="journalier",
        borne_min=borne_min,
    )
    for grandeur, (_, borne_min, borne_max) in CAMS_JOURNALIER.items()
}

# SARAH-3 journalier (ADR-0022), aux 398 localités, 2005-2023 : total du jour
# UTC des valeurs horaires de PVGIS (instantanées datées de hh:07, seriescalc,
# base PVGIS-SARAH3), en kWh/m²/jour. Bornes journalières communes ; le DNI
# d'un jour couvert peut être nul, le GHI et le DHI restent strictement
# positifs (maxima servis : GHI 8,31, DNI 9,06, DHI 3,95).
CONTRATS_SARAH3_JOURNALIERS: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="sarah3_monthly",
        source_id=11,
        source_libelle="SARAH-3 (PVGIS)",
        prefixe_code=f"sarah3_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire",
        annee_debut=2005,
        annee_fin=2023,
        borne_max=BORNES_JOURNALIERES[grandeur],
        granularite="journalier",
        borne_min=0.0 if grandeur == "dni" else None,
    )
    for grandeur in ("ghi", "dni", "dhi")
}

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
# Séries horaires CAMS Radiation (ADR-0023) aux mêmes points pilotes, 2021-2025 :
# irradiation intégrée sur l'heure UTC qui commence à l'instant, en Wh/m², soit
# la moyenne de l'heure en W/m². Colonne du CSV de l'ADS et bornes, celles du
# rayonnement horaire NASA POWER.
CAMS_HORAIRE: dict[str, tuple[str, float, float]] = {
    "ghi": ("GHI", 0.0, 1400.0),
    "dni": ("BNI", 0.0, 1400.0),
    "dhi": ("DHI", 0.0, 900.0),
    "ghi_ciel_clair": ("Clear sky GHI", 0.0, 1400.0),
}
COLONNES_CAMS_HORAIRES: dict[str, str] = {g: c for g, (c, _, _) in CAMS_HORAIRE.items()}
CONTRATS_CAMS_HORAIRES: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="cams_radiation",
        source_id=13,
        source_libelle="CAMS Radiation",
        prefixe_code=f"cams_{grandeur}_horaire",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire",
        annee_debut=2021,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="horaire",
        borne_min=borne_min,
    )
    for grandeur, (_, borne_min, borne_max) in CAMS_HORAIRE.items()
}


# Particules fines CAMS EAC4 (ADR-0015) : moyenne journalière (jour UTC) des huit
# pas de 3 h de la réanalyse, à la maille de 0,75° la plus proche, en µg/m³.
# 2005-2025, période de CAMS Radiation. Variable NetCDF et borne haute, au-dessus
# des maxima servis aux 398 localités : PM2.5 1 143 et PM10 1 567 le 13 novembre
# 2013 à Madjoari, panache de feux de brousse (744 et 1 017 le même jour dans la
# Gobnangou, maximum des provinces). Valeurs strictement positives.
PM_EAC4: dict[str, tuple[str, float]] = {
    "pm2_5": ("pm2p5", 2000.0),
    "pm10": ("pm10", 3000.0),
}
CONTRATS_PM: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="cams_eac4",
        source_id=15,
        source_libelle="CAMS EAC4",
        prefixe_code=f"cams_eac4_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="reanalyse",
        annee_debut=2005,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="journalier",
    )
    for grandeur, (_, borne_max) in PM_EAC4.items()
}

# Épaisseur optique des aérosols à 550 nm, CAMS EAC4 (ADR-0019) : totale, des
# poussières désertiques et de la matière organique (feux surtout), sans unité ;
# même recette que les particules fines, aux 398 localités (lot ``localites``),
# 2005-2025. Variable NetCDF et borne haute, au-dessus des maxima servis
# (3,14, 2,56 et 0,94 en moyenne du jour) ; borne basse 0 incluse.
AOD_EAC4: dict[str, tuple[str, float]] = {
    "aod550": ("aod550", 5.0),
    "aod550_poussiere": ("duaod550", 5.0),
    "aod550_organique": ("omaod550", 2.0),
}
CONTRATS_AOD: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="cams_eac4",
        source_id=15,
        source_libelle="CAMS EAC4",
        prefixe_code=f"cams_eac4_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="reanalyse",
        annee_debut=2005,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="journalier",
        borne_min=0.0,
    )
    for grandeur, (_, borne_max) in AOD_EAC4.items()
}


# Journalier dense aux 351 communes (ADR-0017) : NASA POWER sur 2005-2025, mêmes
# paramètres et bornes que les provinces, mesures dans la table dense.
CONTRATS_NASA_JOURNALIERS_COMMUNES: dict[str, ContratSerie] = {
    g: _nasa(g, 2005, "journalier") for g in ("ghi", "dni", "dhi")
}
# Seuls écarts admis : 514,64 mm servis le 2 décembre 2025, en saison sèche, à
# Sidéradougou et Tiéfora (même maille), au-delà de la borne de 500 mm.
ECARTS_PLUIE_COMMUNES: frozenset[tuple[str, str]] = frozenset(
    {("bfa_dep_sideradougou", "2025-12-02"), ("bfa_dep_tiefora", "2025-12-02")}
)
CONTRATS_METEO_JOURNALIERS_COMMUNES: dict[str, ContratSerie] = {
    g: replace(
        c,
        annee_debut=2005,
        ecarts_admis=ECARTS_PLUIE_COMMUNES if g == "precipitation" else frozenset(),
    )
    for g, c in CONTRATS_METEO_JOURNALIERS.items()
}


# Météo complémentaire NASA POWER (ADR-0021), journalière aux 398 localités,
# 2005-2025, en stockage dense : paramètre, bornes basse et haute (°C, m/s,
# degrés depuis le nord, kPa, %). La nébulosité vient de CERES (satellite),
# le reste de la réanalyse MERRA-2. Les bornes du vent, de 1,6 à 1,8 fois les
# maxima servis (9,21, 12,81 et 11,14 m/s), arrêtent une erreur d'unité.
METEO_NASA_COMPLEMENTAIRE: dict[str, tuple[str, float, float]] = {
    "t2m_min": ("T2M_MIN", 0.0, 45.0),
    "t2m_max": ("T2M_MAX", 5.0, 55.0),
    "point_rosee_2m": ("T2MDEW", -30.0, 35.0),
    "vent_10m": ("WS10M", 0.0, 15.0),
    "vent_10m_max": ("WS10M_MAX", 0.0, 20.0),
    "direction_vent_10m": ("WD10M", 0.0, 360.0),
    "vent_50m": ("WS50M", 0.0, 20.0),
    "pression_surface": ("PS", 85.0, 105.0),
    "nebulosite": ("CLOUD_AMT", 0.0, 100.0),
}
CONTRATS_METEO_COMPLEMENTAIRE: dict[str, ContratSerie] = {
    grandeur: ContratSerie(
        source_code="nasa_power",
        source_id=1,
        source_libelle="NASA POWER",
        prefixe_code=f"nasa_power_{grandeur}_journalier",
        grandeur_code=grandeur,
        methode_collecte="modele_satellitaire" if grandeur == "nebulosite" else "reanalyse",
        annee_debut=2005,
        annee_fin=2025,
        borne_max=borne_max,
        granularite="journalier",
        borne_min=borne_min,
    )
    for grandeur, (_, borne_min, borne_max) in METEO_NASA_COMPLEMENTAIRE.items()
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
