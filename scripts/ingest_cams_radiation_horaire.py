#!/usr/bin/env python3
"""Ingesteur reproductible : rayonnement horaire CAMS Radiation, Burkina Faso.

Récupère, aux coordonnées des cinq points pilotes (ADR-0014), l'irradiation
horaire de CAMS Radiation (Heliosat-4 et McClear, jeu
``cams-solar-radiation-timeseries`` de l'ADS Copernicus) sur 2021-2025, et
écrit un CSV gzip par grandeur sous ``src/kuma_data_core/db/seeds/donnees/``
(ADR-0023) : GHI, DNI et DHI tous temps, GHI par ciel clair. Les migrations
relisent ces fichiers et n'accèdent jamais au réseau.

Le CSV de l'ADS donne, pour chaque heure UTC, l'irradiation intégrée sur
l'heure en Wh/m², soit la moyenne de l'heure en W/m². La période
``AAAA-MM-JJTHH:00/…`` devient l'instant ``HH:00`` UTC, début de l'heure,
comme pour NASA POWER (``services.horaire``). Les colonnes ``GHI``, ``BNI``
(DNI), ``DHI`` et ``Clear sky GHI`` sont repérées par leur nom dans
l'en-tête et arrondies à 4 décimales. Une heure non servie (``nan``), une
référence de temps autre que le temps universel, une version du service autre
que celle que citent les notes publiques (v4.6) ou une valeur hors des bornes
du contrat arrête l'écriture.

Accès : clé ADS lue dans la variable d'environnement ``ADS_API_KEY``. L'ADS
limite le nombre de requêtes en file : elles partent une à une, et toute
erreur est reprise après une attente croissante, jusqu'à 8 essais.

Usage : ``uv run python scripts/ingest_cams_radiation_horaire.py --cache
DOSSIER`` (le cache garde la réponse brute de chaque point pour reprendre
après une interruption).
"""

from __future__ import annotations

import argparse
import math
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import cdsapi  # type: ignore[import-untyped]

from kuma_data_core.db.seeds.lots_bfa import (
    COLONNES_CAMS_HORAIRES,
    CONTRATS_CAMS_HORAIRES,
    LOT_HORAIRE,
    points_pilotes,
)
from kuma_data_core.db.seeds.series_csv import ecrire_series_horaires

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
JEU = "cams-solar-radiation-timeseries"
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_CAMS_HORAIRES.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_CAMS_HORAIRES.values())
NB_HEURES = next(iter(CONTRATS_CAMS_HORAIRES.values())).nb_heures
# Écart toléré entre le point demandé et celui que l'en-tête rappelle (4 décimales).
TOLERANCE_POINT = 1e-4
# Version du service citée par les notes publiques (migration 0022).
VERSION_SERVICE = "v4.6"
ESSAIS = 8


def _fichier(cache: Path, code: str) -> Path:
    return cache / f"cams_radiation_horaire_{code}.csv"


def _lire_brut(
    chemin: Path, lat: float, lon: float
) -> tuple[dict[str, list[tuple[datetime, float]]], str, str]:
    """Valeurs horaires par grandeur, version du service et date de génération.

    ``ValueError`` si la réponse est incomplète, porte sur un autre point ou
    contient une heure non servie.
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
    if meta.get("Summarization (integration) period") != "0 year 0 month 0 day 1 h 0 min 0 s":
        raise ValueError(f"{chemin.name} : pas de temps autre que l'heure")
    if not meta.get("Time reference", "").startswith("Universal time"):
        raise ValueError(f"{chemin.name} : référence de temps autre que le temps universel")
    point = (
        float(meta["Latitude (positive North, ISO 19115)"]),
        float(meta["Longitude (positive East, ISO 19115)"]),
    )
    if max(abs(point[0] - lat), abs(point[1] - lon)) > TOLERANCE_POINT:
        raise ValueError(f"{chemin.name} : réponse pour {point}, ({lat}, {lon}) demandé")
    index = {nom: i for i, nom in enumerate(entetes[0].lstrip("# ").split(";"))}
    mesures: dict[str, list[tuple[datetime, float]]] = {g: [] for g in COLONNES_CAMS_HORAIRES}
    for ligne in lignes:
        if not ligne or ligne.startswith("#"):
            continue
        champs = ligne.split(";")
        instant = datetime.fromisoformat(champs[0].split("/")[0]).replace(tzinfo=UTC)
        for grandeur, colonne in COLONNES_CAMS_HORAIRES.items():
            wh = float(champs[index[colonne]])
            if math.isnan(wh):
                raise ValueError(f"{chemin.name} : {colonne} non servi le {instant.isoformat()}")
            mesures[grandeur].append((instant, round(wh, 4)))
    if len(mesures["ghi"]) != NB_HEURES:
        raise ValueError(f"{chemin.name} : {len(mesures['ghi'])} heures, {NB_HEURES} attendues")
    return mesures, version.group(0), meta["File generated on"]


def _en_cache(chemin: Path, lat: float, lon: float) -> bool:
    """Vrai si le cache contient une réponse complète ; une réponse tronquée est redemandée."""
    if not chemin.exists():
        return False
    try:
        _lire_brut(chemin, lat, lon)
    except (ValueError, KeyError, IndexError):
        return False
    return True


def _telecharger(code: str, lat: float, lon: float, cache: Path, cle: str) -> None:
    client = cdsapi.Client(url=ADS_URL, key=cle, quiet=True, progress=False)
    requete = {
        "sky_type": "observed_cloud",
        "location": {"latitude": lat, "longitude": lon},
        "altitude": ["-999."],
        "date": [f"{ANNEE_DEBUT}-01-01/{ANNEE_FIN}-12-31"],
        "time_step": "1hour",
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


def main(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    points = points_pilotes()
    manquants = [p for p in points if not _en_cache(_fichier(cache, p[0]), p[2], p[3])]
    cle = os.environ.get("ADS_API_KEY", "")
    if manquants and not cle:
        raise SystemExit("Clé ADS absente : définir la variable d'environnement ADS_API_KEY.")
    for code, _, lat, lon in manquants:
        _telecharger(code, lat, lon, cache, cle)
        print(f"{code} : réponse ADS reçue")
    try:
        bruts = {code: _lire_brut(_fichier(cache, code), lat, lon) for code, _, lat, lon in points}
    except (ValueError, KeyError, IndexError) as erreur:
        raise SystemExit(f"Réponse ADS inattendue : {erreur}") from None
    versions = {version for _, version, _ in bruts.values()}
    if versions != {VERSION_SERVICE}:
        raise SystemExit(f"Version du service {sorted(versions)}, {VERSION_SERVICE} attendue")
    generations = sorted({generation for _, _, generation in bruts.values()})
    print(f"CAMS Radiation Service {VERSION_SERVICE}, réponses générées : {', '.join(generations)}")
    for grandeur, contrat in CONTRATS_CAMS_HORAIRES.items():
        series = [(code, lat, lon, bruts[code][0][grandeur]) for code, _, lat, lon in points]
        cible = ecrire_series_horaires(contrat, LOT_HORAIRE, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--cache", required=True, type=Path, help="dossier des réponses brutes")
    args = parseur.parse_args()
    main(args.cache)
