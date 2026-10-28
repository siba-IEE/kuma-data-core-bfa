#!/usr/bin/env python3
"""Ingesteur reproductible : météo et rayonnement journaliers ERA5-Land, Burkina Faso.

Récupère, aux coordonnées des 398 localités (lot ``localites`` : 47 provinces
et 351 communes), les séries ponctuelles horaires d'ERA5-Land (jeu
``reanalysis-era5-land-timeseries`` du CDS Copernicus, maille de 0,1° la plus
proche) sur 2005-2025, et écrit un fichier Parquet dense par grandeur
(ADR-0017, ADR-0024) sous ``src/kuma_data_core/db/seeds/donnees/denses/``. Les
migrations relisent ces fichiers et n'accèdent jamais au réseau.

Agrégats du jour UTC :

- valeurs instantanées des heures 0 à 23 h : température à 2 m (moyenne,
  minimum et maximum, ``t2m``), point de rosée (moyenne, ``d2m``), pression de
  surface (moyenne, ``sp``, en kPa), vent à 10 m (moyenne des vitesses
  horaires, et direction du vent moyen vectoriel, ``u10`` et ``v10``) ;
- cumuls horaires, datés de la fin de leur heure, de 1 h au lendemain 0 h :
  pluie (``tp``, en mm) et rayonnement global (``ssrd``, en kWh/m²). Le
  dernier jour omet l'heure de 23 h à minuit, absente de la série demandée.

Les valeurs sont arrondies à 4 décimales ; un cumul horaire très faiblement
négatif, arrondi du modèle, compte zéro. Une archive aux heures irrégulières,
à plusieurs mailles ou à une maille à plus de 0,05° du point, une valeur
manquante ou hors des bornes du contrat arrête l'écriture.

Accès : clé lue dans la variable d'environnement ``ADS_API_KEY`` (le CDS et
l'ADS partagent le compte Copernicus) ; licence ERA5-Land acceptée une fois.
Les requêtes partent par deux (``--travailleurs``), le CDS limitant les
demandes en file, et toute erreur est reprise après une attente croissante,
jusqu'à 8 essais.

Usage : ``uv run python scripts/ingest_era5_land_journalier.py --cache
DOSSIER`` (le cache garde l'archive brute de chaque localité).
"""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]
import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_ERA5_LAND_JOURNALIERS,
    LOT_LOCALITES,
    points_lot,
)
from kuma_data_core.db.seeds.series_denses import ecrire_series_denses

CDS_URL = "https://cds.climate.copernicus.eu/api"
JEU = "reanalysis-era5-land-timeseries"
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "total_precipitation",
    "surface_solar_radiation_downwards",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
]
COLONNES = ("t2m", "d2m", "tp", "ssrd", "u10", "v10", "sp")
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_ERA5_LAND_JOURNALIERS.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_ERA5_LAND_JOURNALIERS.values())
NB_JOURS = (date(ANNEE_FIN, 12, 31) - date(ANNEE_DEBUT, 1, 1)).days + 1
# Écart toléré entre le point demandé et la maille servie (la moitié de 0,1°).
TOLERANCE_MAILLE = 0.05 + 1e-6
ESSAIS = 8
KELVIN = 273.15


def _fichier(cache: Path, code: str) -> Path:
    return cache / f"era5_land_horaire_{code}.zip"


def _horaire(chemin: Path, lat: float, lon: float) -> pd.DataFrame:
    """Valeurs horaires de l'archive, une colonne par variable ; ``ValueError`` si inattendues."""
    with zipfile.ZipFile(chemin) as archive:
        tables = [
            pd.read_csv(archive.open(nom)) for nom in archive.namelist() if nom.endswith(".csv")
        ]
    if not tables:
        raise ValueError(f"{chemin.name} : archive sans fichier CSV")
    horaire = pd.DataFrame({"instant": pd.to_datetime(tables[0]["valid_time"], utc=True)})
    mailles = set()
    pas = horaire["instant"].diff().dropna()
    if (
        horaire["instant"].iloc[0] != pd.Timestamp(f"{ANNEE_DEBUT}-01-01", tz="UTC")
        or not (pas == pd.Timedelta(hours=1)).all()
    ):
        raise ValueError(f"{chemin.name} : heures irrégulières ou début inattendu")
    for table in tables:
        instants = pd.to_datetime(table["valid_time"], utc=True)
        if not (instants.to_numpy() == horaire["instant"].to_numpy()).all():
            raise ValueError(f"{chemin.name} : instants différents d'un fichier à l'autre")
        if table["latitude"].nunique() != 1 or table["longitude"].nunique() != 1:
            raise ValueError(f"{chemin.name} : plusieurs mailles dans un même fichier")
        maille = (float(table["latitude"].iloc[0]), float(table["longitude"].iloc[0]))
        mailles.add(maille)
        if max(abs(maille[0] - lat), abs(maille[1] - lon)) > TOLERANCE_MAILLE:
            raise ValueError(f"{chemin.name} : maille {maille} loin de ({lat}, {lon})")
        for colonne in table.columns:
            if colonne in COLONNES:
                horaire[colonne] = table[colonne].to_numpy(dtype=float)
    if len(mailles) != 1:
        raise ValueError(f"{chemin.name} : fichiers de mailles différentes")
    manquantes = set(COLONNES) - set(horaire.columns)
    if manquantes:
        raise ValueError(f"{chemin.name} : variables absentes {sorted(manquantes)}")
    if len(horaire) != NB_JOURS * 24 or horaire[list(COLONNES)].isna().any().any():
        raise ValueError(f"{chemin.name} : série horaire incomplète")
    return horaire


def _lire_brut(chemin: Path, lat: float, lon: float) -> dict[str, list[tuple[date, float | None]]]:
    """Agrégats du jour UTC par grandeur."""
    h = _horaire(chemin, lat, lon)
    jour = h["instant"].dt.date
    # Un cumul daté de la fin de son heure appartient au jour de son début.
    jour_cumul = (h["instant"] - pd.Timedelta(hours=1)).dt.date
    vitesse = np.hypot(h["u10"], h["v10"])
    instantanes = pd.DataFrame(
        {
            "jour": jour,
            "t2m": h["t2m"] - KELVIN,
            "d2m": h["d2m"] - KELVIN,
            "sp": h["sp"] / 1000,
            "vitesse": vitesse,
            "u10": h["u10"],
            "v10": h["v10"],
        }
    ).groupby("jour")
    cumuls = (
        pd.DataFrame(
            {
                "jour": jour_cumul,
                "tp": h["tp"].clip(lower=0) * 1000,
                "ssrd": h["ssrd"].clip(lower=0) / 3.6e6,
            }
        )
        .groupby("jour")
        .sum()
    )
    moyennes = instantanes.mean()
    u, v = moyennes["u10"], moyennes["v10"]
    agregats = {
        "t2m": moyennes["t2m"],
        "t2m_min": instantanes["t2m"].min(),
        "t2m_max": instantanes["t2m"].max(),
        "point_rosee_2m": moyennes["d2m"],
        "pression_surface": moyennes["sp"],
        "vent_10m": moyennes["vitesse"],
        # Direction d'où souffle le vent moyen ; un arrondi à 360° revient à 0°.
        "direction_vent_10m": ((np.degrees(np.arctan2(-u, -v)) + 360) % 360).round(4) % 360,
        "precipitation": cumuls["tp"],
        "ghi": cumuls["ssrd"],
    }
    attendus = [date(ANNEE_DEBUT, 1, 1) + timedelta(days=i) for i in range(NB_JOURS)]
    mesures: dict[str, list[tuple[date, float | None]]] = {}
    for grandeur, serie in agregats.items():
        serie = serie.reindex(attendus)
        if serie.isna().any():
            raise ValueError(f"{chemin.name} : {grandeur} incomplet")
        mesures[grandeur] = [(j, round(float(x), 4)) for j, x in zip(attendus, serie, strict=True)]
    return mesures


def _telecharger(code: str, lat: float, lon: float, cache: Path, cle: str) -> None:
    client = cdsapi.Client(url=CDS_URL, key=cle, quiet=True, progress=False)
    cible = _fichier(cache, code)
    provisoire = cible.with_suffix(".part")
    for essai in range(1, ESSAIS + 1):
        try:
            client.retrieve(
                JEU,
                {
                    "variable": VARIABLES,
                    "location": {"longitude": lon, "latitude": lat},
                    "date": [f"{ANNEE_DEBUT}-01-01/{ANNEE_FIN}-12-31"],
                    "data_format": "csv",
                },
                str(provisoire),
            )
            if zipfile.is_zipfile(provisoire):
                break
        except Exception as erreur:  # refus de file CDS, coupure réseau
            if essai == ESSAIS:
                raise SystemExit(f"{code} : échec CDS après {ESSAIS} essais ({erreur})") from None
        time.sleep(30 * essai)
    else:
        raise SystemExit(f"{code} : aucune archive valide après {ESSAIS} essais")
    provisoire.replace(cible)


def main(cache: Path, travailleurs: int) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(LOT_LOCALITES)
    manquants = [p for p in points if not zipfile.is_zipfile(_fichier(cache, p[0]))]
    cle = os.environ.get("ADS_API_KEY", "")
    if manquants and not cle:
        raise SystemExit("Clé absente : définir la variable d'environnement ADS_API_KEY.")
    with ThreadPoolExecutor(travailleurs) as executeur:
        futurs = [
            executeur.submit(_telecharger, code, lat, lon, cache, cle)
            for code, _, lat, lon in manquants
        ]
        for i, futur in enumerate(as_completed(futurs), 1):
            futur.result()
            if i % 25 == 0 or i == len(futurs):
                print(f"{i}/{len(futurs)} réponses CDS")
    try:
        bruts = {code: _lire_brut(_fichier(cache, code), lat, lon) for code, _, lat, lon in points}
    except ValueError as erreur:
        raise SystemExit(str(erreur)) from None
    # Date de consultation : celle de l'archive la plus récente du cache.
    consultation = datetime.fromtimestamp(
        max(_fichier(cache, code).stat().st_mtime for code, *_ in points), UTC
    ).date()
    source = {
        "service": f"CDS Copernicus, jeu {JEU}",
        "version": "ERA5-Land",
        "consultation": consultation.isoformat(),
    }
    print(f"ERA5-Land, CDS Copernicus, consulté le {consultation.isoformat()}")
    for grandeur, contrat in CONTRATS_ERA5_LAND_JOURNALIERS.items():
        series = [(code, lat, lon, bruts[code][grandeur]) for code, _, lat, lon in points]
        cible = ecrire_series_denses(contrat, LOT_LOCALITES, series, source)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des archives brutes")
    parseur.add_argument("--travailleurs", type=int, default=2, help="requêtes simultanées")
    args = parseur.parse_args()
    main(args.cache, args.travailleurs)
