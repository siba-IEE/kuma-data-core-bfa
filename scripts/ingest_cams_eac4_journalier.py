#!/usr/bin/env python3
"""Ingesteur reproductible : particules fines et aérosols journaliers CAMS EAC4, Burkina Faso.

Récupère, année par année, des champs de la réanalyse CAMS EAC4 (jeu
``cams-global-reanalysis-eac4`` de l'ADS Copernicus, maille de 0,75°, pas de
3 h) sur une zone couvrant le Burkina Faso, puis écrit un fichier par grandeur
sous ``src/kuma_data_core/db/seeds/donnees/``. Deux familles :

- ``pm`` : concentrations massiques de surface PM2.5 et PM10, en µg/m³ ; CSV
  gzip pour les 47 provinces (lot ``provinces``, ADR-0015), Parquet dense pour
  les 351 communes (lot ``communes``, ADR-0018) ;
- ``aod`` : épaisseur optique des aérosols à 550 nm, totale, des poussières et
  de la matière organique, sans unité ; Parquet dense pour les 398 localités
  (lot ``localites``, ADR-0019).

Les migrations relisent ces fichiers et n'accèdent jamais au réseau.

Accès : clé ADS lue dans la variable d'environnement ``ADS_API_KEY`` ; licence
du jeu acceptée une fois sur le compte Copernicus. Les requêtes EAC4 passent par
la file de l'archive MARS, qui peut les retenir plusieurs heures, et l'ADS
limite à cinq les requêtes en file par compte et par jeu : une requête par
année, ou par bloc d'années consécutives (``--annees-par-requete``, 17 au plus
pour ``pm``, 11 pour ``aod``) découpé en fichiers annuels à réception ; au plus
``--travailleurs`` requêtes à la fois, toute erreur reprise après une attente
croissante, jusqu'à 8 essais.

Recette : maille la plus proche de chaque localité, sans interpolation ;
moyenne des huit pas du jour civil UTC (00 à 21 h) ; conversion de kg/m³ en
µg/m³ (× 10⁹) pour les particules fines ; arrondi à 4 décimales. Les pas
servis à zéro par la réanalyse sont gardés tels quels (ADR-0015).

Usage : ``uv run python scripts/ingest_cams_eac4_journalier.py --famille aod
--lot localites --cache DOSSIER`` (le cache garde le zip NetCDF de chaque
année pour reprendre après une interruption ; un fichier incomplet y est
redemandé).
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import xarray as xr  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import (
    AOD_EAC4,
    CONTRATS_AOD,
    CONTRATS_PM,
    LOT_LOCALITES,
    PM_EAC4,
    points_lot,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie, ecrire_series_journalieres
from kuma_data_core.db.seeds.series_denses import ecrire_series_denses

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
JEU = "cams-global-reanalysis-eac4"
HEURES = [f"{h:02d}:00" for h in range(0, 24, 3)]
# Nord, ouest, sud, est : les localités (9,4 à 14,9 °N, -5,4 à 2,1 °E) et une
# maille de marge.
ZONE = [15.5, -6.0, 9.0, 3.0]
DEMI_MAILLE = 0.375 + 1e-6  # degrés, maille EAC4 de 0,75°
# L'ADS refuse une requête de plus de 100 000 champs (variables × 8 pas par jour).
CHAMPS_PAR_REQUETE_MAX = 100_000
ESSAIS = 8


@dataclass(frozen=True)
class Famille:
    variables_ads: dict[str, str]  # grandeur -> variable de la requête ADS
    variables_nc: dict[str, str]  # grandeur -> variable NetCDF
    unite: str  # attribut ``units`` attendu, sans espace
    facteur: float  # conversion vers l'unité de la grandeur
    cache: str  # préfixe des zip annuels du cache
    contrats: dict[str, ContratSerie]
    lots: tuple[str, ...]  # lots servis : provinces en CSV, les autres en Parquet dense

    @property
    def annees_par_requete_max(self) -> int:
        return CHAMPS_PAR_REQUETE_MAX // (len(self.variables_ads) * len(HEURES) * 366)

    def dense(self, lot: str) -> bool:
        return lot != "provinces"


FAMILLES: dict[str, Famille] = {
    "pm": Famille(
        variables_ads={
            "pm2_5": "particulate_matter_2.5um",
            "pm10": "particulate_matter_10um",
        },
        variables_nc={g: v for g, (v, _) in PM_EAC4.items()},
        unite="kgm**-3",
        facteur=1e9,  # kg/m³ -> µg/m³
        cache="cams_eac4_pm",
        contrats=CONTRATS_PM,
        lots=("provinces", "communes"),
    ),
    "aod": Famille(
        variables_ads={
            "aod550": "total_aerosol_optical_depth_550nm",
            "aod550_poussiere": "dust_aerosol_optical_depth_550nm",
            "aod550_organique": "organic_matter_aerosol_optical_depth_550nm",
        },
        variables_nc={g: v for g, (v, _) in AOD_EAC4.items()},
        unite="~",
        facteur=1.0,
        cache="cams_eac4_aod",
        contrats=CONTRATS_AOD,
        lots=(LOT_LOCALITES,),
    ),
}


def _annees(famille: Famille) -> list[int]:
    contrats = famille.contrats.values()
    return list(range(min(c.annee_debut for c in contrats), max(c.annee_fin for c in contrats) + 1))


def _fichier(famille: Famille, cache: Path, debut: int, fin: int | None = None) -> Path:
    """Zip d'une année, ou d'un bloc d'années tel que l'ADS le sert."""
    if fin is None or fin == debut:
        return cache / f"{famille.cache}_{debut}.zip"
    return cache / f"{famille.cache}_{debut}_{fin}.zip"


def _lire(famille: Famille, chemin: Path, debut: int, fin: int) -> xr.Dataset:
    """Champs des années ``debut`` à ``fin`` ; ``ValueError`` si le fichier est incomplet."""
    if not zipfile.is_zipfile(chemin):
        raise ValueError(f"{chemin.name} : zip illisible")
    jeux = []
    with zipfile.ZipFile(chemin) as archive, tempfile.TemporaryDirectory() as dossier:
        noms = [n for n in archive.namelist() if n.endswith(".nc") and "/" not in n]
        if not noms:
            raise ValueError(f"{chemin.name} : aucun fichier NetCDF")
        for nom in noms:
            archive.extract(nom, dossier)
            with xr.open_dataset(Path(dossier) / nom, engine="netcdf4") as jeu:
                jeux.append(jeu.load())
    ds = xr.merge(jeux, compat="override").squeeze(drop=True)
    if "valid_time" in ds.dims:
        ds = ds.rename({"valid_time": "time"})
    instants = pd.DatetimeIndex(ds["time"].values)
    attendus = pd.date_range(f"{debut}-01-01", f"{fin}-12-31 21:00", freq="3h")
    if not instants.equals(attendus):
        raise ValueError(f"{chemin.name} : {len(instants)} pas, {len(attendus)} attendus")
    for grandeur, variable in famille.variables_nc.items():
        if variable not in ds.data_vars:
            raise ValueError(f"{chemin.name} : variable {variable} absente")
        if ds[variable].attrs.get("units", "").replace(" ", "") != famille.unite:
            raise ValueError(f"{chemin.name} : unité de {variable} inattendue")
        if bool(np.isnan(ds[variable].values).any()):
            raise ValueError(f"{chemin.name} : valeur absente pour {grandeur}")
    return ds


def _en_cache(famille: Famille, cache: Path, annee: int) -> bool:
    """Vrai si le cache contient l'année complète ; un fichier tronqué est redemandé."""
    try:
        _lire(famille, _fichier(famille, cache, annee), annee, annee)
    except (ValueError, OSError):
        return False
    return True


def _decouper(famille: Famille, cache: Path, debut: int, fin: int) -> None:
    """Range chaque année d'une réponse pluriannuelle dans son propre zip du cache."""
    with (
        zipfile.ZipFile(_fichier(famille, cache, debut, fin)) as archive,
        tempfile.TemporaryDirectory() as d,
    ):
        noms = [n for n in archive.namelist() if n.endswith(".nc") and "/" not in n]
        for nom in noms:
            archive.extract(nom, d)
        for annee in range(debut, fin + 1):
            cible = _fichier(famille, cache, annee)
            provisoire = cible.with_suffix(".part")
            with zipfile.ZipFile(provisoire, "w", zipfile.ZIP_DEFLATED) as sortie:
                for nom in noms:
                    annuel = Path(d) / f"{annee}_{nom}"
                    with xr.open_dataset(Path(d) / nom, engine="netcdf4") as jeu:
                        temps = "valid_time" if "valid_time" in jeu.dims else "time"
                        tranche = slice(f"{annee}-01-01", f"{annee}-12-31T21:00")
                        jeu.sel({temps: tranche}).to_netcdf(annuel, engine="netcdf4")
                    sortie.write(annuel, nom)
            provisoire.replace(cible)


def _telecharger(famille: Famille, debut: int, fin: int, cache: Path, cle: str) -> None:
    client = cdsapi.Client(url=ADS_URL, key=cle, quiet=True, progress=False)
    requete = {
        "variable": list(famille.variables_ads.values()),
        "date": [f"{debut}-01-01/{fin}-12-31"],
        "time": HEURES,
        "area": ZONE,
        "data_format": "netcdf_zip",
    }
    cible = _fichier(famille, cache, debut, fin)
    provisoire = cible.with_suffix(".part")
    for essai in range(1, ESSAIS + 1):
        try:
            client.retrieve(JEU, requete, str(provisoire))
            break
        except Exception as erreur:  # refus de file ADS, coupure réseau
            if essai == ESSAIS:
                raise SystemExit(
                    f"{debut}-{fin} : échec ADS après {ESSAIS} essais ({erreur})"
                ) from None
            time.sleep(60 * essai)
    provisoire.replace(cible)
    if fin != debut:
        _decouper(famille, cache, debut, fin)


def _blocs(annees: list[int], taille: int) -> list[tuple[int, int]]:
    """Années manquantes regroupées en blocs consécutifs d'au plus ``taille`` années."""
    blocs: list[tuple[int, int]] = []
    for annee in annees:
        if blocs and annee == blocs[-1][1] + 1 and annee - blocs[-1][0] < taille:
            blocs[-1] = (blocs[-1][0], annee)
        else:
            blocs.append((annee, annee))
    return blocs


def _journalier(
    ds: xr.Dataset, lat: float, lon: float, variable: str, facteur: float
) -> list[tuple[date, float]]:
    """Moyenne des huit pas de chaque jour UTC à la maille la plus proche."""
    maille = ds[variable].sel(latitude=lat, longitude=lon, method="nearest")
    if max(abs(float(maille.latitude) - lat), abs(float(maille.longitude) - lon)) > DEMI_MAILLE:
        raise ValueError(f"point ({lat}, {lon}) hors de la zone servie")
    valeurs = maille.to_series().astype("float64")  # champs servis en float32
    moyennes = valeurs.groupby(valeurs.index.normalize()).mean() * facteur
    return [(jour.date(), round(float(v), 4)) for jour, v in moyennes.items()]


def main(
    nom_famille: str, lot: str, cache: Path, travailleurs: int, annees_par_requete: int
) -> None:
    famille = FAMILLES[nom_famille]
    if lot not in famille.lots:
        raise SystemExit(f"--lot {lot} : la famille {nom_famille} sert {famille.lots}.")
    if not 1 <= annees_par_requete <= famille.annees_par_requete_max:
        raise SystemExit(f"--annees-par-requete : de 1 à {famille.annees_par_requete_max}.")
    cache.mkdir(parents=True, exist_ok=True)
    annees = _annees(famille)
    manquantes = [a for a in annees if not _en_cache(famille, cache, a)]
    cle = os.environ.get("ADS_API_KEY", "")
    if manquantes and not cle:
        raise SystemExit("Clé ADS absente : définir la variable d'environnement ADS_API_KEY.")
    blocs = _blocs(manquantes, annees_par_requete)
    with ThreadPoolExecutor(travailleurs) as executeur:
        futurs = [executeur.submit(_telecharger, famille, d, f, cache, cle) for d, f in blocs]
        for i, futur in enumerate(as_completed(futurs), 1):
            futur.result()
            print(f"{i}/{len(futurs)} requêtes reçues")
    points = points_lot(lot)
    # Date de consultation : celle du fichier annuel le plus récent du cache.
    recu = max(_fichier(famille, cache, a).stat().st_mtime for a in annees)
    source = {
        "service": f"ADS Copernicus, jeu {JEU}",
        "version": "EAC4",
        "consultation": datetime.fromtimestamp(recu, UTC).date().isoformat(),
    }
    mesures: dict[str, dict[str, list[tuple[date, float]]]] = {
        g: {code: [] for code, *_ in points} for g in famille.variables_nc
    }
    for annee in annees:
        try:
            ds = _lire(famille, _fichier(famille, cache, annee), annee, annee)
            for grandeur, variable in famille.variables_nc.items():
                for code, _, lat, lon in points:
                    mesures[grandeur][code] += _journalier(ds, lat, lon, variable, famille.facteur)
        except (ValueError, OSError) as erreur:
            raise SystemExit(f"{annee} : {erreur}") from None
    for grandeur, contrat in famille.contrats.items():
        series = [(code, lat, lon, mesures[grandeur][code]) for code, _, lat, lon in points]
        if famille.dense(lot):
            # Aucun écart admis par ces contrats : une valeur hors bornes arrête
            # l'écriture (ADR-0017).
            cible = ecrire_series_denses(contrat, lot, list(series), source)
        else:
            cible = ecrire_series_journalieres(contrat, lot, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--famille", required=True, choices=sorted(FAMILLES))
    parseur.add_argument(
        "--lot", required=True, choices=sorted({lot for f in FAMILLES.values() for lot in f.lots})
    )
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des zip NetCDF")
    parseur.add_argument("--travailleurs", type=int, default=5, help="requêtes ADS simultanées")
    parseur.add_argument(
        "--annees-par-requete",
        type=int,
        default=1,
        help="années consécutives par requête ADS (17 au plus pour pm, 11 pour aod)",
    )
    args = parseur.parse_args()
    main(args.famille, args.lot, args.cache, args.travailleurs, args.annees_par_requete)
