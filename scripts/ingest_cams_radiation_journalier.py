#!/usr/bin/env python3
"""Ingesteur reproductible : rayonnement journalier CAMS Radiation, Burkina Faso.

Récupère, aux coordonnées des 398 localités (lot ``localites`` : 47 provinces
et 351 communes), l'irradiation journalière de CAMS Radiation (Heliosat-4 et
McClear, jeu ``cams-solar-radiation-timeseries`` de l'ADS Copernicus) sur
2005-2025 et écrit un fichier Parquet dense par grandeur (ADR-0017) sous
``src/kuma_data_core/db/seeds/donnees/denses/`` : GHI, DNI et DHI tous temps,
GHI et DNI par ciel clair. Les migrations relisent ces fichiers et n'accèdent
jamais au réseau.

Accès : clé ADS lue dans la variable d'environnement ``ADS_API_KEY`` ; licence
CAMS acceptée une fois sur le compte Copernicus. L'ADS traite les requêtes de
ce jeu à peu près une à la fois (deux à sept minutes chacune pour 21 ans au
pas journalier) : les requêtes partent en parallèle (``--travailleurs``) et
toute erreur est reprise après une attente croissante, jusqu'à 8 essais.

Le CSV de l'ADS donne, par jour UTC, l'irradiation intégrée en Wh/m². Les
colonnes ``GHI``, ``BNI`` (DNI), ``DHI``, ``Clear sky GHI`` et ``Clear sky
BNI`` sont repérées par leur nom dans l'en-tête et ramenées en kWh/m²/jour
(division par 1 000), arrondies à 4 décimales. Un jour que le service ne sert
pas (``nan``) reste sans valeur ; une valeur hors des bornes du contrat arrête
l'écriture.

Usage : ``uv run python scripts/ingest_cams_radiation_journalier.py --cache
DOSSIER`` (le cache garde la réponse brute de chaque localité pour reprendre
après une interruption ; une réponse incomplète y est redemandée).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import (
    COLONNES_CAMS_JOURNALIERES,
    CONTRATS_CAMS_JOURNALIERS,
    LOT_LOCALITES,
    points_lot,
)
from kuma_data_core.db.seeds.series_denses import ecrire_series_denses

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
JEU = "cams-solar-radiation-timeseries"
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_CAMS_JOURNALIERS.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_CAMS_JOURNALIERS.values())
NB_JOURS = (date(ANNEE_FIN, 12, 31) - date(ANNEE_DEBUT, 1, 1)).days + 1
# Écart toléré entre le point demandé et celui que l'en-tête rappelle (4 décimales).
TOLERANCE_POINT = 1e-4
ESSAIS = 8


def _fichier(cache: Path, code: str) -> Path:
    return cache / f"cams_radiation_journalier_{code}.csv"


def _lire_brut(
    chemin: Path, lat: float, lon: float
) -> tuple[dict[str, list[tuple[date, float | None]]], str, str]:
    """Valeurs journalières par grandeur, version du service et date de génération.

    ``ValueError`` si la réponse est incomplète ou porte sur un autre point.
    """
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    entetes = [ligne for ligne in lignes if ligne.startswith("# Observation period;")]
    if len(entetes) != 1:
        raise ValueError(f"{chemin.name} : en-tête CAMS introuvable")
    meta = {
        cle.strip(): valeur.strip()
        for ligne in lignes
        if ligne.startswith("# ") and ":" in ligne
        for cle, valeur in [ligne[2:].split(":", 1)]
    }
    version = re.search(r"v\d+(\.\d+)+", meta.get("Title", ""))
    if version is None or "File generated on" not in meta:
        raise ValueError(f"{chemin.name} : version du service ou date de génération absente")
    point = (
        float(meta["Latitude (positive North, ISO 19115)"]),
        float(meta["Longitude (positive East, ISO 19115)"]),
    )
    if max(abs(point[0] - lat), abs(point[1] - lon)) > TOLERANCE_POINT:
        raise ValueError(f"{chemin.name} : réponse pour {point}, ({lat}, {lon}) demandé")
    index = {nom: i for i, nom in enumerate(entetes[0].lstrip("# ").split(";"))}
    mesures: dict[str, list[tuple[date, float | None]]] = {
        g: [] for g in COLONNES_CAMS_JOURNALIERES
    }
    for ligne in lignes:
        if not ligne or ligne.startswith("#"):
            continue
        champs = ligne.split(";")
        jour = date.fromisoformat(champs[0][:10])
        for grandeur, colonne in COLONNES_CAMS_JOURNALIERES.items():
            wh = float(champs[index[colonne]])
            mesures[grandeur].append((jour, None if math.isnan(wh) else round(wh / 1000, 4)))
    if len(mesures["ghi"]) != NB_JOURS:
        raise ValueError(f"{chemin.name} : {len(mesures['ghi'])} jours, {NB_JOURS} attendus")
    return mesures, version.group(0), meta["File generated on"]


def _en_cache(chemin: Path, lat: float, lon: float) -> bool:
    """Vrai si le cache contient une réponse complète ; une réponse tronquée est redemandée."""
    if not chemin.exists():
        return False
    try:
        _lire_brut(chemin, lat, lon)
    except ValueError:
        return False
    return True


def _telecharger(code: str, lat: float, lon: float, cache: Path, cle: str) -> None:
    client = cdsapi.Client(url=ADS_URL, key=cle, quiet=True, progress=False)
    requete = {
        "sky_type": "observed_cloud",
        "location": {"latitude": lat, "longitude": lon},
        "altitude": ["-999."],
        "date": [f"{ANNEE_DEBUT}-01-01/{ANNEE_FIN}-12-31"],
        "time_step": "1day",
        "time_reference": "universal_time",
        "format": "csv",
    }
    cible = _fichier(cache, code)
    provisoire = cible.with_suffix(".part")
    for essai in range(1, ESSAIS + 1):
        try:
            client.retrieve(JEU, requete, str(provisoire))
            break
        except Exception as erreur:  # refus de file ADS, coupure réseau
            if essai == ESSAIS:
                raise SystemExit(f"{code} : échec ADS après {ESSAIS} essais ({erreur})") from None
            time.sleep(60 * essai)
    provisoire.replace(cible)


def main(cache: Path, travailleurs: int) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(LOT_LOCALITES)
    manquants = [p for p in points if not _en_cache(_fichier(cache, p[0]), p[2], p[3])]
    cle = os.environ.get("ADS_API_KEY", "")
    if manquants and not cle:
        raise SystemExit("Clé ADS absente : définir la variable d'environnement ADS_API_KEY.")
    with ThreadPoolExecutor(travailleurs) as executeur:
        futurs = [
            executeur.submit(_telecharger, code, lat, lon, cache, cle)
            for code, _, lat, lon in manquants
        ]
        for i, futur in enumerate(as_completed(futurs), 1):
            futur.result()
            if i % 25 == 0 or i == len(futurs):
                print(f"{i}/{len(futurs)} réponses ADS")
    bruts = {}
    try:
        for code, _, lat, lon in points:
            bruts[code] = _lire_brut(_fichier(cache, code), lat, lon)
    except ValueError as erreur:
        raise SystemExit(str(erreur)) from None
    versions = {version for _, version, _ in bruts.values()}
    if len(versions) != 1:
        raise SystemExit(f"Réponses servies par plusieurs versions du service : {sorted(versions)}")
    source = {
        "service": f"ADS Copernicus, jeu {JEU}, CAMS Radiation Service",
        "version": versions.pop(),
        "consultation": max(generation for _, _, generation in bruts.values()),
    }
    print(f"CAMS Radiation Service {source['version']}, consulté le {source['consultation']}")
    for grandeur, contrat in CONTRATS_CAMS_JOURNALIERS.items():
        series = [(code, lat, lon, bruts[code][0][grandeur]) for code, _, lat, lon in points]
        cible = ecrire_series_denses(contrat, LOT_LOCALITES, series, source)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des réponses brutes")
    parseur.add_argument("--travailleurs", type=int, default=6, help="requêtes ADS simultanées")
    args = parseur.parse_args()
    main(args.cache, args.travailleurs)
