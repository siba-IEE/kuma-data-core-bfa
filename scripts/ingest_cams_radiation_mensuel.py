#!/usr/bin/env python3
"""Ingesteur reproductible : GHI, DNI et DHI mensuels CAMS Radiation, Burkina Faso.

Récupère, aux coordonnées des localités d'un lot (``provinces`` ou ``communes``,
ADR-0011), l'irradiation mensuelle tous temps de CAMS Radiation (Heliosat-4 et
McClear, jeu ``cams-solar-radiation-timeseries`` de l'ADS Copernicus) et écrit un
CSV gzip par grandeur sous ``src/kuma_data_core/db/seeds/donnees/``. Les
migrations relisent ces fichiers et n'accèdent jamais au réseau.

Accès : clé ADS lue dans la variable d'environnement ``ADS_API_KEY`` ; licence
CAMS acceptée une fois sur le compte Copernicus. L'ADS met chaque requête en file
(plusieurs minutes) et limite le nombre de requêtes en file par compte : les
requêtes partent en parallèle (``--travailleurs``) et toute erreur est reprise
après une attente croissante, jusqu'à 8 essais. Une clé invalide n'échoue donc
qu'au bout de ces essais.

Le CSV de l'ADS donne, par mois, l'irradiation intégrée en Wh/m². Les colonnes
``GHI``, ``BNI`` (DNI) et ``DHI`` sont repérées par leur nom dans l'en-tête et
ramenées en moyenne journalière du mois, en kWh/m²/jour (division par 1 000 et
par le nombre de jours du mois). Période : 2005-2025, années complètes servies
(CAMS commence en février 2004).

Usage : ``uv run --with cdsapi python scripts/ingest_cams_radiation_mensuel.py
--lot communes --cache DOSSIER`` (le cache garde la réponse brute de chaque
localité pour reprendre après une interruption ; une réponse incomplète y est
redemandée).
"""

from __future__ import annotations

import argparse
import calendar
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_CAMS, LOTS, points_lot
from kuma_data_core.db.seeds.series_csv import ecrire_series

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
JEU = "cams-solar-radiation-timeseries"
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_CAMS.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_CAMS.values())
NB_MOIS = (ANNEE_FIN - ANNEE_DEBUT + 1) * 12
COLONNES: dict[str, str] = {"ghi": "GHI", "dni": "BNI", "dhi": "DHI"}
ESSAIS = 8


def _fichier(cache: Path, code: str) -> Path:
    return cache / f"cams_radiation_{code}.csv"


def _lire_brut(chemin: Path) -> dict[str, list[tuple[int, int, float]]]:
    """Moyennes journalières du mois par grandeur ; ``ValueError`` si la réponse est incomplète."""
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    entetes = [ligne for ligne in lignes if ligne.startswith("# Observation period;")]
    if len(entetes) != 1:
        raise ValueError(f"{chemin.name} : en-tête CAMS introuvable")
    index = {nom: i for i, nom in enumerate(entetes[0].lstrip("# ").split(";"))}
    mesures: dict[str, list[tuple[int, int, float]]] = {g: [] for g in COLONNES}
    for ligne in lignes:
        if not ligne or ligne.startswith("#"):
            continue
        champs = ligne.split(";")
        annee, mois = int(champs[0][:4]), int(champs[0][5:7])
        jours = calendar.monthrange(annee, mois)[1]
        for grandeur, colonne in COLONNES.items():
            wh = float(champs[index[colonne]])
            if math.isnan(wh):
                raise ValueError(f"{chemin.name} : valeur absente {colonne} {annee}-{mois:02d}")
            mesures[grandeur].append((annee, mois, round(wh / 1000 / jours, 4)))
    if len(mesures["ghi"]) != NB_MOIS:
        raise ValueError(f"{chemin.name} : {len(mesures['ghi'])} mois, {NB_MOIS} attendus")
    return mesures


def _en_cache(chemin: Path) -> bool:
    """Vrai si le cache contient une réponse complète ; une réponse tronquée est redemandée."""
    if not chemin.exists():
        return False
    try:
        _lire_brut(chemin)
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
        "time_step": "1month",
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


def main(lot: str, cache: Path, travailleurs: int) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(lot)
    manquants = [p for p in points if not _en_cache(_fichier(cache, p[0]))]
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
    try:
        bruts = {code: _lire_brut(_fichier(cache, code)) for code, *_ in points}
    except ValueError as erreur:
        raise SystemExit(str(erreur)) from None
    for grandeur, contrat in CONTRATS_CAMS.items():
        series = [(code, lat, lon, bruts[code][grandeur]) for code, _, lat, lon in points]
        cible = ecrire_series(contrat, lot, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--lot", required=True, choices=LOTS)
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des réponses brutes")
    parseur.add_argument("--travailleurs", type=int, default=4, help="requêtes ADS simultanées")
    args = parseur.parse_args()
    main(args.lot, args.cache, args.travailleurs)
