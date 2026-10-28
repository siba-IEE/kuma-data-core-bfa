#!/usr/bin/env python3
"""Ingesteur reproductible : rayonnement journalier SARAH-3 (PVGIS), Burkina Faso.

Récupère, aux coordonnées des 398 localités (lot ``localites`` : 47 provinces
et 351 communes), les séries horaires de PVGIS (JRC, API v5_3 ``seriescalc``,
base ``PVGIS-SARAH3``) sur 2005-2023, plan horizontal, composantes séparées, et
écrit un fichier Parquet dense par grandeur (ADR-0017, ADR-0022) sous
``src/kuma_data_core/db/seeds/donnees/denses/`` : GHI, DNI et DHI, total du
jour UTC en kWh/m²/jour. Les migrations relisent ces fichiers et n'accèdent
jamais au réseau.

PVGIS sert, pour chaque heure UTC, la valeur instantanée datée de hh:07 du
direct (``Gb(i)``) et du diffus (``Gd(i)``) sur le plan horizontal, qu'il tient
pour la moyenne de l'heure, et la hauteur du soleil (``H_sun``). Une valeur
reconstruite par PVGIS (``Int`` non nul) arrête la lecture. Le GHI du jour est
la somme du direct et du diffus, le DHI celle du diffus ; le DNI est la somme
du direct horizontal divisé par le sinus de la hauteur du soleil, ce que fait
PVGIS pour son DNI mensuel (``Hb(n)_m``).

Une heure que SARAH-3 ne sert pas, PVGIS la rend nulle, hauteur du soleil
comprise, sans la signaler : est manquante toute heure où ``H_sun`` vaut zéro
alors que le soleil, calculé par pvlib à l'instant servi, est à plus de 3°.
Comme le CM SAF pour ses moyennes journalières (formule de Diekmann et al.,
1988), les totaux du jour sont alors complétés au prorata du GHI par ciel clair
(modèle Solis simplifié de pvlib) : total servi × ciel clair du jour / ciel
clair des heures servies. Le même facteur vaut pour les trois grandeurs, ce qui
garde le direct horizontal sous le DNI. Un jour reste sans valeur quand des
heures manquantes d'affilée couvrent plus de la moitié de son ciel clair : rien
ne dit alors ce qu'a fait le ciel. Il reste aussi sans valeur quand moins du
quart de son ciel clair est servi, seuil inspiré de celui du CM SAF, qui compte
des créneaux. Les totaux en Wh/m² sont ramenés en kWh/m²/jour et arrondis à 4
décimales. Une valeur hors des bornes du contrat arrête l'écriture.

Usage : ``uv run python scripts/ingest_pvgis_sarah3_journalier.py --cache
DOSSIER`` (le cache garde la réponse brute de chaque localité, compressée,
pour reprendre après une interruption).
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_SARAH3_JOURNALIERS, LOT_LOCALITES, points_lot
from kuma_data_core.db.seeds.series_denses import ecrire_series_denses
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
BASE = "PVGIS-SARAH3"
DELAI = 600.0
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_SARAH3_JOURNALIERS.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_SARAH3_JOURNALIERS.values())
NB_JOURS = (date(ANNEE_FIN, 12, 31) - date(ANNEE_DEBUT, 1, 1)).days + 1
# Écart toléré entre le point demandé et celui que la réponse rappelle.
TOLERANCE_POINT = 1e-4
# Hauteur du soleil (degrés) au-delà de laquelle une heure servie nulle manque.
HAUTEUR_MANQUE = 3.0
# Part du ciel clair du jour au-delà de laquelle des heures manquantes
# d'affilée laissent le jour sans valeur.
SUITE_MAX = 0.5
# Part du ciel clair servie en deçà de laquelle le jour reste sans valeur (seuil
# inspiré de celui du CM SAF).
SERVI_MIN = 0.25


def _fichier(cache: Path, code: str) -> Path:
    return cache / f"pvgis_sarah3_horaire_{code}.json.gz"


def _telecharger(code: str, lat: float, lon: float, cache: Path) -> None:
    with httpx.Client(timeout=DELAI) as client:
        reponse = executer_get_avec_retry(
            client=client,
            url=URL,
            query_params={
                "lat": str(lat),
                "lon": str(lon),
                "raddatabase": BASE,
                "startyear": str(ANNEE_DEBUT),
                "endyear": str(ANNEE_FIN),
                "components": "1",
                "angle": "0",
                "aspect": "0",
                "outputformat": "json",
            },
            timeout=DELAI,
        )
    reponse.raise_for_status()
    cible = _fichier(cache, code)
    provisoire = cible.with_suffix(".part")
    provisoire.write_bytes(gzip.compress(reponse.content, 6))
    provisoire.replace(cible)


def _heures(chemin: Path, lat: float, lon: float) -> Iterator[dict[str, Any]]:
    """Heures de la réponse brute, après contrôle de la base, de la période et du point."""
    brut: dict[str, Any] = json.loads(gzip.decompress(chemin.read_bytes()))
    entrees = brut["inputs"]
    meteo, point = entrees["meteo_data"], entrees["location"]
    if (meteo["radiation_db"], meteo["year_min"], meteo["year_max"]) != (
        BASE,
        ANNEE_DEBUT,
        ANNEE_FIN,
    ):
        raise ValueError(f"{chemin.name} : base ou période inattendue ({meteo})")
    if max(abs(point["latitude"] - lat), abs(point["longitude"] - lon)) > TOLERANCE_POINT:
        raise ValueError(f"{chemin.name} : réponse pour {point}, ({lat}, {lon}) demandé")
    fixe = entrees.get("mounting_system", {}).get("fixed", {})
    if (fixe.get("slope", {}).get("value"), fixe.get("azimuth", {}).get("value")) != (0, 0):
        raise ValueError(f"{chemin.name} : plan autre que l'horizontale ({fixe})")
    heures: list[dict[str, Any]] = brut["outputs"]["hourly"]
    if not heures or not {"time", "Gb(i)", "Gd(i)", "H_sun", "Int"} <= heures[0].keys():
        raise ValueError(f"{chemin.name} : colonnes horaires inattendues")
    if len(heures) != NB_JOURS * 24:
        raise ValueError(f"{chemin.name} : {len(heures)} heures, {NB_JOURS * 24} attendues")
    yield from heures


def _lire_brut(
    chemin: Path, lat: float, lon: float
) -> tuple[dict[str, list[tuple[date, float | None]]], dict[date, float]]:
    """Totaux du jour UTC par grandeur, et part perdue des jours incomplets.

    Un jour sans valeur a une part perdue de 1. ``ValueError`` si la réponse est
    inattendue.
    """
    heures = pd.DataFrame(list(_heures(chemin, lat, lon)))
    if (heures["Int"] != 0).any():
        raise ValueError(f"{chemin.name} : valeurs reconstruites par PVGIS")
    instants = pd.to_datetime(heures["time"], format="%Y%m%d:%H%M", utc=True)
    direct = heures["Gb(i)"].to_numpy(dtype=float)
    diffus = heures["Gd(i)"].to_numpy(dtype=float)
    hauteur = heures["H_sun"].to_numpy(dtype=float)
    if ((direct > 0) & (hauteur <= 0)).any():
        raise ValueError(f"{chemin.name} : direct servi soleil couché")
    soleil = pvlib.solarposition.get_solarposition(instants, lat, lon)
    elevation = soleil["apparent_elevation"].to_numpy()
    manque = (hauteur == 0) & (elevation > HAUTEUR_MANQUE)
    clair = pvlib.clearsky.simplified_solis(np.clip(elevation, 0, 90))
    poids = np.nan_to_num(np.asarray(clair["ghi"], dtype=float))
    with np.errstate(divide="ignore", invalid="ignore"):
        normal = np.where(hauteur > 0, direct / np.sin(np.radians(hauteur)), 0.0)
    table = (
        pd.DataFrame(
            {
                "jour": instants.dt.date,
                "ghi": direct + diffus,
                "dni": normal,
                "dhi": diffus,
                "clair": poids,
                "clair_servi": np.where(manque, 0.0, poids),
            }
        )
        .groupby("jour")
        .sum()
    )
    attendus = [date(ANNEE_DEBUT, 1, 1) + timedelta(days=i) for i in range(NB_JOURS)]
    if list(table.index) != attendus:
        raise ValueError(f"{chemin.name} : jours manquants ou en trop")
    # Suites d'heures manquantes : une heure servie ou de nuit en ouvre une autre.
    suites = (
        pd.DataFrame({"jour": instants.dt.date, "suite": np.cumsum(~manque), "perdu": poids})[
            manque
        ]
        .groupby(["jour", "suite"])["perdu"]
        .sum()
        .groupby(level="jour")
        .max()
        .reindex(table.index, fill_value=0.0)
    )
    sans_valeur = (suites > SUITE_MAX * table["clair"]) | (
        table["clair_servi"] < SERVI_MIN * table["clair"]
    )
    perte = (1 - table["clair_servi"] / table["clair"]).where(~sans_valeur, 1.0)
    complement = table["clair"] / table["clair_servi"]
    mesures: dict[str, list[tuple[date, float | None]]] = {"ghi": [], "dni": [], "dhi": []}
    for grandeur, valeurs in mesures.items():
        for jour, total, facteur, part in zip(
            attendus, table[grandeur], complement, perte, strict=True
        ):
            if part == 1.0:
                valeurs.append((jour, None))
            else:
                valeur = total * facteur if part > 0 else total
                valeurs.append((jour, round(valeur / 1000, 4)))
    return mesures, {j: float(p) for j, p in zip(attendus, perte, strict=True) if p > 0}


def main(cache: Path, travailleurs: int) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(LOT_LOCALITES)
    manquants = [p for p in points if not _fichier(cache, p[0]).exists()]
    with ThreadPoolExecutor(travailleurs) as executeur:
        futurs = [
            executeur.submit(_telecharger, code, lat, lon, cache) for code, _, lat, lon in manquants
        ]
        for i, futur in enumerate(as_completed(futurs), 1):
            futur.result()
            if i % 25 == 0 or i == len(futurs):
                print(f"{i}/{len(futurs)} réponses PVGIS")
    try:
        lus = {code: _lire_brut(_fichier(cache, code), lat, lon) for code, _, lat, lon in points}
    except ValueError as erreur:
        raise SystemExit(str(erreur)) from None
    bruts = {code: mesures for code, (mesures, _) in lus.items()}
    pertes = [p for _, parts in lus.values() for p in parts.values()]
    completes = [p for p in pertes if p < 1.0]
    print(
        f"Jours-localités complétés : {len(completes)}, dont "
        f"{sum(p > 0.1 for p in completes)} de plus de 10 % ; "
        f"{len(pertes) - len(completes)} laissés sans valeur"
    )
    # Date de consultation : celle de la réponse la plus récente du cache.
    consultation = datetime.fromtimestamp(
        max(_fichier(cache, code).stat().st_mtime for code, *_ in points), UTC
    ).date()
    source = {
        "service": f"PVGIS (JRC) API v5_3 seriescalc, base {BASE}",
        "version": "v5_3",
        "consultation": consultation.isoformat(),
    }
    print(f"PVGIS {BASE}, API v5_3, consultée le {consultation.isoformat()}")
    for grandeur, contrat in CONTRATS_SARAH3_JOURNALIERS.items():
        series = [(code, lat, lon, bruts[code][grandeur]) for code, _, lat, lon in points]
        cible = ecrire_series_denses(contrat, LOT_LOCALITES, series, source)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des réponses brutes")
    parseur.add_argument("--travailleurs", type=int, default=4, help="requêtes simultanées")
    args = parseur.parse_args()
    main(args.cache, args.travailleurs)
